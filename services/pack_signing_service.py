"""
Signing service for HodleagueCards.mintWithSignature.
Produces EIP-191 signatures that match the contract's expected payload.
"""

import logging
from typing import List

from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from config import Config

logger = logging.getLogger(__name__)


def _get_signer_account() -> Account:
    """Return Account for SIGNER_ROLE key. Raises if not configured."""
    key = (Config.PACK_SIGNER_PRIVATE_KEY or "").strip()
    if not key:
        raise ValueError("PACK_SIGNER_PRIVATE_KEY is not set")
    if key.startswith("0x"):
        key = key[2:]
    return Account.from_key(key)


def _encode_packed_for_mint(
    user_address: str,
    opening_id: int,
    card_ids: List[int],
    server_seed: bytes,
    chain_id: int,
    contract_address: str,
) -> bytes:
    """
    Build bytes matching Solidity abi.encodePacked(
        user, openingId, cardIds, serverSeed, block.chainid, address(this)
    ).
    Packed encoding: address=20 bytes, uint256=32 bytes, uint256[]=no length, each element 32 bytes.
    """
    parts: List[bytes] = []
    # address (20 bytes)
    parts.append(Web3.to_bytes(hexstr=Web3.to_checksum_address(user_address)))
    # uint256 openingId (32 bytes, big-endian)
    parts.append(opening_id.to_bytes(32, "big"))
    # uint256[] cardIds: no length prefix, each element 32 bytes
    for cid in card_ids:
        parts.append(cid.to_bytes(32, "big"))
    # bytes32 serverSeed (32 bytes)
    if len(server_seed) != 32:
        raise ValueError("server_seed must be 32 bytes")
    parts.append(server_seed)
    # uint256 chainId (32 bytes)
    parts.append(chain_id.to_bytes(32, "big"))
    # address contract (20 bytes)
    parts.append(Web3.to_bytes(hexstr=Web3.to_checksum_address(contract_address)))
    return b"".join(parts)


def sign_mint_with_signature(
    user_address: str,
    opening_id: int,
    card_ids: List[int],
    server_seed: bytes,
) -> bytes:
    """
    Sign payload for HodleagueCards.mintWithSignature(
        user,
        openingId,
        cardIds,
        serverSeed,
        signature
    ).

    Solidity reconstructs the message as:
      keccak256(abi.encodePacked(
          user,
          openingId,
          cardIds,
          serverSeed,
          block.chainid,
          address(this)
      ))

    We use the same packed encoding so the recovered signer matches SIGNER_ROLE.
    """
    if len(server_seed) != 32:
        raise ValueError("server_seed must be 32 bytes")
    if not user_address:
        raise ValueError("user_address is required")
    if opening_id <= 0:
        raise ValueError("opening_id must be positive")
    if not card_ids:
        raise ValueError("card_ids cannot be empty")

    cards_address = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    if not cards_address:
        raise ValueError("CARDS_CONTRACT_ADDRESS is not set")

    chain_id = Config.CHAIN_ID
    packed = _encode_packed_for_mint(
        user_address, opening_id, card_ids, server_seed, chain_id, cards_address
    )
    message_hash = Web3.keccak(packed)
    signable = encode_defunct(primitive=message_hash)
    account = _get_signer_account()
    signed = account.sign_message(signable)
    return bytes(signed.signature)
