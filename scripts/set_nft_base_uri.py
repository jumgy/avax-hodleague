"""
Script to update HodleagueCards base URI (for metadata tokenURI).
Use when switching between local and production API, or after deploying with wrong BASE_URI.

Requires NFT_ADMIN_PRIVATE_KEY (key with DEFAULT_ADMIN_ROLE on HodleagueCards).
Requires NFT_METADATA_BASE_URL in .env (e.g. http://localhost:8000/nft/cards/ for local).

Local testing:
  1. Run backend: uvicorn main:app
  2. (Optional) Expose via ngrok: ngrok http 8000
  3. Set NFT_METADATA_BASE_URL in .env:
     - Local only: http://localhost:8000/nft/cards/
     - With ngrok: https://YOUR_SUBDOMAIN.ngrok.io/nft/cards/
  4. Run: python -m scripts.set_nft_base_uri

Note: Wallets and marketplaces fetch tokenURI from the network. They cannot reach
localhost. Use ngrok (or similar) if you need metadata to be fetchable externally.
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from eth_account import Account
from web3 import Web3

from config import Config


CARDS_ABI = [
    {
        "inputs": [{"internalType": "string", "name": "baseURI", "type": "string"}],
        "name": "setBaseURI",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def main() -> None:
    base_url = (Config.NFT_METADATA_BASE_URL or "").strip()
    if not base_url:
        print("NFT_METADATA_BASE_URL is not set in .env")
        sys.exit(1)

    if not base_url.endswith("/"):
        base_url = base_url + "/"
        print(f"Added trailing slash: {base_url}")

    cards_addr = (Config.CARDS_CONTRACT_ADDRESS or "").strip()
    if not cards_addr:
        print("CARDS_CONTRACT_ADDRESS is not set in .env")
        sys.exit(1)

    key = (Config.NFT_ADMIN_PRIVATE_KEY or "").strip()
    if not key:
        print(
            "NFT_ADMIN_PRIVATE_KEY is not set. "
            "Use the deployer key (has DEFAULT_ADMIN_ROLE on HodleagueCards)."
        )
        sys.exit(1)
    if key.startswith("0x"):
        key = key[2:]
    account = Account.from_key(key)

    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 15}))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(cards_addr),
        abi=CARDS_ABI,
    )

    print(f"Setting base URI to: {base_url}")
    print(f"Contract: {cards_addr}")
    print(f"Chain ID: {Config.CHAIN_ID}")
    print()

    tx = contract.functions.setBaseURI(base_url).build_transaction(
        {
            "from": account.address,
            "gas": 100_000,
            "chainId": Config.CHAIN_ID,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Transaction sent: {tx_hash.hex()}")
    print("Wait for confirmation, then tokenURI will return the new base URL.")


if __name__ == "__main__":
    main()
