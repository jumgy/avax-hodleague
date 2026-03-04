"""
Signing service for HodleagueCards.mintWithSignature.
Produces EIP-191 signatures that match the contract's expected payload.
"""

import logging
from typing import List

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_abi import encode
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

    Solidity side reconstructs the message as:
      keccak256(abi.encodePacked(
          user,
          openingId,
          cardIds,
          serverSeed,
          block.chainid,
          address(this)
      ))

    Here we mirror that with solidityKeccak and include chainId and cards contract address.
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
    address = Web3.to_checksum_address(user_address)
    contract_addr = Web3.to_checksum_address(cards_address)

    # solidity: abi.encodePacked(address,uint256,uint256[],bytes32,uint256,address)
    encoded = encode(
        ["address", "uint256", "uint256[]", "bytes32", "uint256", "address"],
        [address, opening_id, card_ids, server_seed, chain_id, contract_addr],
    )
    message_hash = Web3.keccak(encoded)
    signable = encode_defunct(primitive=message_hash)
    account = _get_signer_account()
    signed = account.sign_message(signable)
    return bytes(signed.signature)
