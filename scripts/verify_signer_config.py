"""
Verify backend signer config for HodleagueCards.mintWithSignature.

Checks:
  - PACK_SIGNER_PRIVATE_KEY is set and derives to an address.
  - CARDS_CONTRACT_ADDRESS and WEB3_PROVIDER_URL are set.
  - The signer address has SIGNER_ROLE on the Cards contract (hasRole(SIGNER_ROLE, signer)).

Usage:
  python -m scripts.verify_signer_config

  Uses .env from project root (CARDS_CONTRACT_ADDRESS, CHAIN_ID, PACK_SIGNER_PRIVATE_KEY, WEB3_PROVIDER_URL).

For manual check with Foundry cast (same RPC and contract as in .env):
  SIGNER_ROLE = keccak256("SIGNER_ROLE")
  cast call <CARDS_CONTRACT_ADDRESS> "hasRole(bytes32,address)(bool)" $(cast keccak "SIGNER_ROLE") <SIGNER_ADDRESS> --rpc-url <WEB3_PROVIDER_URL>

  Get signer address from private key:
  cast wallet address --private-key <PACK_SIGNER_PRIVATE_KEY>
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from eth_account import Account
from web3 import Web3


def main() -> None:
    from config import Config

    cards_addr = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    rpc = (Config.WEB3_PROVIDER_URL or "").strip()
    key = (Config.PACK_SIGNER_PRIVATE_KEY or "").strip()
    chain_id = Config.CHAIN_ID

    print("Verify signer config for HodleagueCards.mintWithSignature")
    print("-" * 50)

    if not cards_addr:
        print("CARDS_CONTRACT_ADDRESS is not set in .env")
        sys.exit(1)
    if not rpc:
        print("WEB3_PROVIDER_URL is not set in .env")
        sys.exit(1)
    if not key:
        print("PACK_SIGNER_PRIVATE_KEY is not set in .env")
        sys.exit(1)

    if key.startswith("0x"):
        key = key[2:]
    try:
        account = Account.from_key(key)
    except Exception as e:
        print(f"Invalid PACK_SIGNER_PRIVATE_KEY: {e}")
        sys.exit(1)

    signer_address = account.address
    print(f"CARDS_CONTRACT_ADDRESS: {cards_addr}")
    print(f"CHAIN_ID:                {chain_id}")
    print(f"WEB3_PROVIDER_URL:       {rpc}")
    print(f"Signer address:          {signer_address}")

    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        print("Cannot connect to RPC. Check WEB3_PROVIDER_URL.")
        sys.exit(1)

    # SIGNER_ROLE = keccak256("SIGNER_ROLE") (same as in HodleagueCards.sol)
    signer_role = w3.keccak(text="SIGNER_ROLE")
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(cards_addr),
        abi=[
            {
                "inputs": [
                    {"internalType": "bytes32", "name": "role", "type": "bytes32"},
                    {"internalType": "address", "name": "account", "type": "address"},
                ],
                "name": "hasRole",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function",
            }
        ],
    )
    try:
        has_role = contract.functions.hasRole(signer_role, signer_address).call()
    except Exception as e:
        print(f"Contract call failed: {e}")
        print("(Contract may not be deployed at this address or RPC may be wrong.)")
        sys.exit(1)

    if has_role:
        print("\nResult: SIGNER_ROLE is granted to the signer address. OK.")
    else:
        print("\nResult: SIGNER_ROLE is NOT granted to the signer address. mintWithSignature will revert.")
        print("Grant SIGNER_ROLE from an account with DEFAULT_ADMIN_ROLE on HodleagueCards:")
        print(f"  grantRole(SIGNER_ROLE, {signer_address})")
        sys.exit(1)

    print("\n--- Manual check with Foundry cast ---")
    print("Get signer address:")
    print("  cast wallet address --private-key <PACK_SIGNER_PRIVATE_KEY>")
    print("Check SIGNER_ROLE on contract:")
    print(
        f'  cast call {cards_addr} "hasRole(bytes32,address)(bool)" '
        f'$(cast keccak "SIGNER_ROLE") {signer_address} --rpc-url {rpc}'
    )
    print("Grant SIGNER_ROLE (as admin):")
    print(
        f'  cast send {cards_addr} "grantRole(bytes32,address)" '
        f'$(cast keccak "SIGNER_ROLE") {signer_address} --rpc-url {rpc} --private-key <ADMIN_PRIVATE_KEY>'
    )


if __name__ == "__main__":
    main()
