"""
Service for minting HodleaguePacks (ERC-1155) on-chain via hot wallet.
Used by admin to grant packs to users.
"""

import asyncio
import logging
from typing import Optional

from eth_account import Account
from web3 import Web3

from config import Config
from services.pack_signing_service import sign_reveal_open

logger = logging.getLogger(__name__)

# Minimal ABI for HodleaguePacks mint, balanceOf, setPackPrice.
PACKS_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "packTypeId", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"},
            {"internalType": "uint256", "name": "id", "type": "uint256"},
        ],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "packTypeId", "type": "uint256"},
            {"internalType": "uint256", "name": "price", "type": "uint256"},
        ],
        "name": "setPackPrice",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "commitId", "type": "uint256"}],
        "name": "getCommit",
        "outputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "packTypeId", "type": "uint256"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "commitId", "type": "uint256"},
            {"internalType": "uint256[]", "name": "cardIds", "type": "uint256[]"},
            {"internalType": "bytes32", "name": "serverSeed", "type": "bytes32"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "relayerRevealOpen",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def _get_admin_account() -> Account:
    """Return Account for NFT_ADMIN key (DEFAULT_ADMIN_ROLE). Raises if not configured."""
    key = (Config.NFT_ADMIN_PRIVATE_KEY or "").strip()
    if not key:
        raise ValueError("NFT_ADMIN_PRIVATE_KEY is not set")
    if key.startswith("0x"):
        key = key[2:]
    return Account.from_key(key)


def _get_hot_wallet_account() -> Account:
    """Return Account for HOT_WALLET key (MINTER_ROLE). Raises if not configured."""
    key = (Config.HOT_WALLET_PRIVATE_KEY or "").strip()
    if not key:
        raise ValueError("HOT_WALLET_PRIVATE_KEY is not set")
    if key.startswith("0x"):
        key = key[2:]
    return Account.from_key(key)


def _get_signer_account() -> Account:
    """Return Account for PACK_SIGNER key (SIGNER_ROLE). Used to send relayerRevealOpen tx."""
    key = (Config.PACK_SIGNER_PRIVATE_KEY or "").strip()
    if not key:
        raise ValueError("PACK_SIGNER_PRIVATE_KEY is not set")
    if key.startswith("0x"):
        key = key[2:]
    return Account.from_key(key)


def _get_packs_contract():
    """Return Web3 contract instance for HodleaguePacks. Raises if not configured."""
    address = (Config.PACKS_CONTRACT_ADDRESS or "").strip()
    if not address:
        raise ValueError("PACKS_CONTRACT_ADDRESS is not set")
    provider_url = Config.WEB3_PROVIDER_URL
    w3 = Web3(Web3.HTTPProvider(provider_url, request_kwargs={"timeout": 10}))
    return w3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=PACKS_ABI,
    )


async def mint_pack_to_user(
    wallet_address: str,
    pack_type_id: int,
    amount: int,
) -> str:
    """
    Mint packs to a user's wallet on-chain.

    Args:
        wallet_address: Recipient Ethereum address (0x...).
        pack_type_id: Pack type ID (maps to ERC-1155 token ID).
        amount: Number of packs to mint.

    Returns:
        Transaction hash (0x...).

    Raises:
        ValueError: If config or parameters are invalid.
        Exception: If RPC or transaction fails.
    """
    if amount < 1:
        raise ValueError("amount must be at least 1")
    if pack_type_id < 1:
        raise ValueError("pack_type_id must be at least 1")

    account = _get_hot_wallet_account()
    contract = _get_packs_contract()
    to_address = Web3.to_checksum_address(wallet_address)

    def _build_and_send():
        w3 = contract.w3
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.mint(to_address, pack_type_id, amount).build_transaction(
            {
                "from": account.address,
                "gas": 200_000,
                "chainId": Config.CHAIN_ID,
                "nonce": nonce,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    try:
        tx_hash = await asyncio.to_thread(_build_and_send)
        logger.info("Pack mint tx submitted: %s (to=%s, packTypeId=%s, amount=%s)", tx_hash, to_address[:10], pack_type_id, amount)
        return tx_hash
    except Exception as e:
        logger.error("Pack mint failed: %s", e)
        raise


async def get_on_chain_pack_balance(wallet_address: str, pack_type_id: int) -> Optional[int]:
    """
    Get ERC-1155 pack balance for a wallet and pack type.

    Args:
        wallet_address: Ethereum address (0x...).
        pack_type_id: Pack type ID (ERC-1155 token ID).

    Returns:
        Balance count, or None if contract/RPC not configured or call fails.
    """
    address = (Config.PACKS_CONTRACT_ADDRESS or "").strip()
    if not address:
        return None

    try:
        contract = _get_packs_contract()
        addr = Web3.to_checksum_address(wallet_address)

        def _call():
            return contract.functions.balanceOf(addr, pack_type_id).call()

        balance = await asyncio.to_thread(_call)
        return balance
    except Exception as e:
        logger.debug("balanceOf failed for %s pack %s: %s", wallet_address[:10], pack_type_id, e)
        return None


async def get_commit(commit_id: int) -> Optional[tuple[str, int, int]]:
    """
    Get commit data from HodleaguePacks for two-step reveal.
    Returns (user_address, pack_type_id, timestamp) or None if commit does not exist.
    """
    address = (Config.PACKS_CONTRACT_ADDRESS or "").strip()
    if not address:
        return None
    try:
        contract = _get_packs_contract()

        def _call():
            return contract.functions.getCommit(commit_id).call()

        result = await asyncio.to_thread(_call)
        # getCommit returns (user, packTypeId, timestamp)
        user_addr, pack_type_id, ts = result
        if not user_addr or user_addr == "0x0000000000000000000000000000000000000000":
            return None
        return (Web3.to_checksum_address(user_addr), pack_type_id, ts)
    except Exception as e:
        logger.debug("getCommit failed for commit_id=%s: %s", commit_id, e)
        return None


async def relayer_reveal_open(
    commit_id: int,
    user_wallet_address: str,
    card_ids: list[int],
    server_seed: bytes,
) -> str:
    """
    Call relayerRevealOpen on HodleaguePacks as SIGNER. Used for abandoned commits
    (user got prepare-open but never sent revealOpen). Cards mint to user_wallet_address.
    """
    if len(server_seed) != 32:
        raise ValueError("server_seed must be 32 bytes")
    signature = sign_reveal_open(
        user_address=user_wallet_address,
        commit_id=commit_id,
        card_ids=card_ids,
        server_seed=server_seed,
    )
    account = _get_signer_account()
    contract = _get_packs_contract()

    def _build_and_send():
        w3 = contract.w3
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.relayerRevealOpen(
            commit_id,
            card_ids,
            server_seed,
            signature,
        ).build_transaction(
            {
                "from": account.address,
                "gas": 500_000,
                "chainId": Config.CHAIN_ID,
                "nonce": nonce,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    tx_hash = await asyncio.to_thread(_build_and_send)
    logger.info(
        "Relayer reveal tx submitted: %s (commit_id=%s, user=%s)",
        tx_hash,
        commit_id,
        user_wallet_address[:10],
    )
    return tx_hash


async def set_pack_price(pack_type_id: int, price_wei: int) -> str:
    """
    Set pack price for buyPack. Requires DEFAULT_ADMIN_ROLE (NFT_ADMIN_PRIVATE_KEY).

    Args:
        pack_type_id: Pack type ID (ERC-1155 token ID).
        price_wei: Price in wei (0 = not for sale).

    Returns:
        Transaction hash.
    """
    if pack_type_id < 1:
        raise ValueError("pack_type_id must be at least 1")
    if price_wei < 0:
        raise ValueError("price_wei must be non-negative")

    account = _get_admin_account()
    contract = _get_packs_contract()

    def _build_and_send():
        w3 = contract.w3
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.setPackPrice(pack_type_id, price_wei).build_transaction(
            {
                "from": account.address,
                "gas": 100_000,
                "chainId": Config.CHAIN_ID,
                "nonce": nonce,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    try:
        tx_hash = await asyncio.to_thread(_build_and_send)
        logger.info("setPackPrice tx: %s pack_type=%s price=%s wei", tx_hash, pack_type_id, price_wei)
        return tx_hash
    except Exception as e:
        logger.error("setPackPrice failed: %s", e)
        raise
