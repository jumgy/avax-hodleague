"""
Service for checking native (gas) balance on EVM chains via RPC.
Can be used to check Avalanche C-Chain balance for gas (e.g. before registration).
"""

import asyncio
import logging
from typing import Optional

from web3 import Web3

logger = logging.getLogger(__name__)


async def get_native_balance_wei(provider_url: str, wallet_address: str) -> Optional[int]:
    """
    Fetch native token balance (wei) for an address on the given chain.

    :param provider_url: RPC URL (e.g. Avalanche C-Chain).
    :param wallet_address: EOA address (0x...).
    :return: Balance in wei, or None if RPC failed (caller should treat as no balance / fallback).
    """
    try:
        web3 = Web3(Web3.HTTPProvider(provider_url, request_kwargs={"timeout": 5}))
        address = Web3.to_checksum_address(wallet_address)
        # Run sync call in thread to avoid blocking
        balance = await asyncio.to_thread(web3.eth.get_balance, address)
        return balance
    except Exception as e:
        logger.warning("Failed to get balance for %s on %s: %s", wallet_address[:10], provider_url[:40], e)
        return None
