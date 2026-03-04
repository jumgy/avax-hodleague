"""
Job to compare on-chain card ownership with user_cards inventory.

For each UserCard that has an nft_token_id, this job compares:
- on-chain ownerOf(nft_token_id) from HodleagueCards
- wallet_address of the user in the database

Differences are logged as warnings using the 'card_health' logger.
"""

import asyncio
import logging
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from config import Config
from models.database import AsyncSessionLocal
from models.user_models import User
from models.user_card_models import UserCard

logger = logging.getLogger("card_health")


CARDS_OWNER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
        ],
        "name": "ownerOf",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


async def _load_user_cards(db: AsyncSession) -> List[Tuple[int, int, int, str]]:
    """
    Load user_cards that have on-chain nft_token_id with associated user wallet addresses.

    Returns:
        List of tuples (user_card_id, nft_token_id, user_id, wallet_address).
    """
    result = await db.execute(
        select(
            UserCard.id,
            UserCard.nft_token_id,
            UserCard.user_id,
            User.wallet_address,
        )
        .join(User, UserCard.user_id == User.id)
        .where(UserCard.nft_token_id.isnot(None))
    )
    rows = result.all()
    data: List[Tuple[int, int, int, str]] = []
    for row in rows:
        user_card_id, nft_token_id, user_id, wallet = row
        wallet_str = (wallet or "").strip()
        if not wallet_str:
            continue
        data.append((int(user_card_id), int(nft_token_id), int(user_id), wallet_str))
    return data


async def run_card_inventory_health_check() -> None:
    """
    Compare on-chain ownerOf with user_cards for all cards that have nft_token_id.

    Logs warnings when the owners differ. Does not mutate database or contracts.
    """
    cards_address = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    if not cards_address:
        return

    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 15}))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(cards_address),
        abi=CARDS_OWNER_ABI,
    )

    async with AsyncSessionLocal() as db:
        try:
            items = await _load_user_cards(db)
            if not items:
                return

            for user_card_id, nft_token_id, user_id, wallet in items:
                def _owner_of() -> str:
                    return contract.functions.ownerOf(nft_token_id).call()

                try:
                    on_chain_owner = await asyncio.to_thread(_owner_of)
                except Exception as e:  # ownerOf can revert for burned/non-existent tokens
                    logger.warning(
                        "Card ownerOf call failed: user_card_id=%s user_id=%s nft_token_id=%s wallet=%s error=%s",
                        user_card_id,
                        user_id,
                        nft_token_id,
                        wallet[:10],
                        e,
                    )
                    continue

                on_chain_owner_str = str(on_chain_owner).strip().lower()
                wallet_lower = wallet.strip().lower()
                if on_chain_owner_str != wallet_lower:
                    logger.warning(
                        "Card inventory mismatch: user_card_id=%s user_id=%s wallet=%s nft_token_id=%s owner_on_chain=%s",
                        user_card_id,
                        user_id,
                        wallet[:10],
                        nft_token_id,
                        on_chain_owner_str,
                    )
        except Exception as e:
            logger.exception("Card inventory health check failed: %s", e)

