"""
Listener and helpers for on-chain card mints.

In the current architecture packs are off-chain only. This module focuses on:
  - Confirming HodleagueCards.mintWithSignature transactions by tx hash (client sends tx_hash).
  - Background job: poll PackOpened events from HodleagueCards so even if the client never
    sends tx_hash, we still create UserCard records when we see the mint on-chain.
"""

import asyncio
import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from config import Config
from models.user_models import User
from models.user_pack_models import PackOpening, UserPack
from models.user_card_models import UserCard
from models.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# HodleagueCards emits PackOpened(address indexed user, uint256 indexed openingId, uint256[] cardIds)
PACK_OPENED_TOPIC = "0x" + Web3.keccak(text="PackOpened(address,uint256,uint256[])").hex()


def _log_data_to_bytes(data) -> bytes:
    """Convert log 'data' (str 0x... or HexBytes) to raw bytes for eth_abi.decode."""
    if data is None:
        return b""
    if hasattr(data, "hex"):
        return bytes(data)
    if isinstance(data, str):
        return bytes.fromhex(data[2:] if data.startswith("0x") else data)
    return bytes(data)


def _parse_pack_opened_from_receipt(tx_hash: str):
    """
    Fetch transaction receipt and decode first PackOpened event from HodleagueCards.
    Returns event args dict (user, openingId, cardIds) or None.
    """
    tx_hash = tx_hash.strip()
    if not tx_hash:
        return None
    if not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash

    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 15}))
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    if not receipt or not receipt.get("logs"):
        return None

    cards_address = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    if not cards_address:
        return None

    cards_address_cs = Web3.to_checksum_address(cards_address)

    # keccak256("PackOpened(address,uint256,uint256[])")
    topic = Web3.keccak(text="PackOpened(address,uint256,uint256[])")
    topic_hex = ("0x" + topic.hex()) if hasattr(topic, "hex") else str(topic)

    for log in receipt["logs"]:
        if not log.get("topics") or len(log["topics"]) < 3:
            continue
        log_address = log.get("address")
        if not isinstance(log_address, str):
            continue
        if log_address.lower() != cards_address_cs.lower():
            continue
        topic0 = log["topics"][0]
        if hasattr(topic0, "hex"):
            topic0_str = "0x" + topic0.hex()
        else:
            topic0_str = str(topic0)
        if topic0_str.lower() != topic_hex.lower():
            continue
        # Decode manually: indexed user, indexed openingId, non-indexed cardIds
        user_topic = log["topics"][1]
        opening_id_topic = log["topics"][2]
        user_hex = user_topic.hex() if hasattr(user_topic, "hex") else (user_topic[2:] if isinstance(user_topic, str) and user_topic.startswith("0x") else user_topic)
        opening_hex = opening_id_topic.hex() if hasattr(opening_id_topic, "hex") else (opening_id_topic[2:] if isinstance(opening_id_topic, str) and str(opening_id_topic).startswith("0x") else opening_id_topic)
        user_address = Web3.to_checksum_address("0x" + user_hex[-40:])
        opening_id = int(opening_hex, 16)
        # cardIds are ABI-encoded in data as uint256[]
        try:
            from eth_abi import decode

            raw_data = _log_data_to_bytes(log.get("data"))
            card_ids = list(decode(["uint256[]"], raw_data)[0]) if raw_data else []
        except Exception:
            card_ids = []
        return {
            "user": user_address,
            "openingId": opening_id,
            "cardIds": card_ids,
        }
    return None


async def _apply_pack_opened_event(
    user_address: str,
    opening_id: int,
    card_ids: list[int],
    db: AsyncSession,
) -> bool:
    """
    Apply PackOpened(user, openingId, cardIds) to the database:
      - find PackOpening by id and user,
      - create UserCard rows,
      - set status=completed and fill nft_token_ids deterministically.
    """
    wallet_lower = user_address.lower()
    user_result = await db.execute(select(User).where(User.wallet_address == wallet_lower))
    user = user_result.scalar_one_or_none()
    if not user:
        logger.warning("PackOpened event for unknown wallet: %s", wallet_lower[:10])
        return False

    opening_result = await db.execute(
        select(PackOpening).where(
            PackOpening.id == opening_id,
            PackOpening.user_id == user.id,
            PackOpening.status == "prepared",
        )
    )
    pack_opening = opening_result.scalar_one_or_none()
    if not pack_opening:
        logger.warning(
            "No matching PackOpening for user=%s opening_id=%s",
            user.id,
            opening_id,
        )
        return False

    if pack_opening.card_ids != card_ids:
        logger.error(
            "PackOpened card_ids mismatch for opening_id=%s (on-chain %s, DB %s)",
            opening_id,
            card_ids,
            pack_opening.card_ids,
        )
        return False

    cards_contract = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    chain_id = Config.CHAIN_ID

    nft_token_ids: list[int] = []
    from eth_abi import encode  # local import to avoid global dependency issues
    for idx, card_id in enumerate(card_ids):
        # Must mirror HodleagueCards.mintWithSignature tokenId formula:
        # keccak256(abi.encodePacked(openingId, index)).
        encoded = encode(["uint256", "uint256"], [opening_id, idx])
        token_id = int(Web3.keccak(encoded).hex(), 16)
        nft_token_ids.append(token_id)
        user_card = UserCard(
            user_id=user.id,
            card_id=card_id,
            pack_opening_id=pack_opening.id,
            source="pack_opening",
            status="available",
            is_active=True,
            nft_token_id=token_id,
            chain_id=chain_id if cards_contract else None,
            contract_address=cards_contract or None,
        )
        db.add(user_card)

    pack_opening.status = "completed"
    pack_opening.nft_token_ids = nft_token_ids
    pack_opening.cards_count = len(card_ids)

    user_pack_result = await db.execute(
        select(UserPack).where(UserPack.id == pack_opening.pack_id)
    )
    user_pack = user_pack_result.scalar_one_or_none()
    if user_pack:
        user_pack.is_opened = True

    logger.info(
        "Processed PackOpened: user_id=%s opening_id=%s cards=%d",
        user.id,
        opening_id,
        len(card_ids),
    )
    return True


async def confirm_pack_opening_by_tx_hash(
    tx_hash: str,
    pack_opening_id: int,
    db: AsyncSession,
) -> Literal["already_completed", "processed", "not_found", "mismatch"]:
    """
    Confirm on-chain mintWithSignature by tx hash: load PackOpening, verify PackOpened event matches (opening_id),
    apply same logic as listener.
    """
    result = await db.execute(
        select(PackOpening).where(PackOpening.id == pack_opening_id)
    )
    opening = result.scalar_one_or_none()
    if not opening:
        return "not_found"
    if opening.status == "completed":
        return "already_completed"
    if opening.status != "prepared":
        return "mismatch"

    user_result = await db.execute(select(User).where(User.id == opening.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return "not_found"
    wallet = (user.wallet_address or "").strip().lower()
    if not wallet:
        return "mismatch"

    def _get_event():
        return _parse_pack_opened_from_receipt(tx_hash)

    args = await asyncio.to_thread(_get_event)
    if not args:
        return "not_found"

    opening_id_ev = int(args.get("openingId", 0))
    if opening_id_ev != opening.id:
        return "mismatch"

    user_address = args.get("user")
    if hasattr(user_address, "lower"):
        user_address = user_address.lower()
    else:
        user_address = str(user_address).lower()
    if user_address != wallet:
        return "mismatch"

    card_ids = [int(x) for x in (args.get("cardIds") or [])]
    ok = await _apply_pack_opened_event(
        user_address=user_address,
        opening_id=opening_id_ev,
        card_ids=card_ids,
        db=db,
    )
    return "processed" if ok else "mismatch"


def _fetch_pack_opened_events(from_block: int, to_block: int) -> list[dict]:
    """
    Fetch PackOpened logs from HodleagueCards in the given block range.
    Returns list of {"user": address, "openingId": int, "cardIds": list[int]}.
    """
    cards_address = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    if not cards_address:
        return []
    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 15}))
    try:
        logs = w3.eth.get_logs(
            {
                "address": Web3.to_checksum_address(cards_address),
                "fromBlock": from_block,
                "toBlock": to_block,
                "topics": [PACK_OPENED_TOPIC],
            }
        )
    except Exception as e:
        logger.warning("get_logs PackOpened failed: %s", e)
        return []
    out = []
    for log in logs:
        if not log.get("topics") or len(log["topics"]) < 3:
            continue
        try:
            user_topic = log["topics"][1]
            opening_id_topic = log["topics"][2]
            user_address = Web3.to_checksum_address("0x" + (user_topic.hex() if hasattr(user_topic, "hex") else str(user_topic))[-40:])
            opening_id = int((opening_id_topic.hex() if hasattr(opening_id_topic, "hex") else str(opening_id_topic)), 16)
            from eth_abi import decode
            raw_data = _log_data_to_bytes(log.get("data"))
            card_ids = list(decode(["uint256[]"], raw_data)[0]) if raw_data else []
        except Exception as e:
            logger.debug("Decode PackOpened log failed: %s", e)
            continue
        out.append({"user": user_address, "openingId": opening_id, "cardIds": card_ids})
    return out


# Block range to poll: ~2 sec/block on Avalanche C-Chain, 10s job => ~5 blocks; use 20 for margin.
PACK_OPENED_POLL_BLOCKS = 100


async def process_pack_opened_events_job() -> None:
    """
    Poll recent blocks for PackOpened events and apply them to the DB.
    So even if the client never calls /confirm with tx_hash, we still create UserCards
    when the user mints via HodleagueCards.mintWithSignature.
    """
    cards_address = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    if not cards_address:
        return
    try:
        w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 10}))
        latest = w3.eth.block_number
        from_block = max(0, latest - PACK_OPENED_POLL_BLOCKS)
        events = await asyncio.to_thread(_fetch_pack_opened_events, from_block, latest)
        if not events:
            return
        async with AsyncSessionLocal() as db:
            for ev in events:
                try:
                    await _apply_pack_opened_event(
                        user_address=ev["user"],
                        opening_id=int(ev["openingId"]),
                        card_ids=[int(x) for x in ev["cardIds"]],
                        db=db,
                    )
                    await db.commit()
                except Exception as e:
                    logger.warning("apply PackOpened event opening_id=%s: %s", ev.get("openingId"), e)
                    await db.rollback()
    except Exception as e:
        logger.warning("process_pack_opened_events_job failed: %s", e)
