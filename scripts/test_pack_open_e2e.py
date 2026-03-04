"""
E2E test script for off-chain packs + on-chain card mint via HodleagueCards.mintWithSignature.

Flow:
  1. test-verify → create/get user and JWT.
  2. admin mint (off-chain) → create UserPack in DB.
  3. admin list packs → get user_pack_id.
  4. /api/packs/prepare-open with {user_pack_id, client_seed} → card_ids, server_seed, signature.
  5. mintWithSignature(user, openingId, cardIds, serverSeed, signature) on HodleagueCards.
  6. /api/packs/openings/{id}/confirm with tx_hash → mark opening completed, create UserCard.
  7. /nft/cards/{tokenId} → fetch metadata for minted NFT.

Uses HOT_WALLET as test user. Requires backend, .env (CARDS_CONTRACT_ADDRESS, HOT_WALLET, PACK_SIGNER, CHAIN_ID),
admin credentials, pack type with guaranteed_slots and cards in DB.

Usage:
  python -m scripts.test_pack_open_e2e
  python -m scripts.test_pack_open_e2e --api-url http://localhost:8000 --pack-type-id 1
"""

import argparse
import os
import sys
import secrets

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from eth_account import Account
import requests
from web3 import Web3

try:
    from web3.middleware import ExtraDataToPOAMiddleware as _poa_middleware
except ImportError:
    from web3.middleware import geth_poa_middleware as _poa_middleware

from config import Config

API_BASE = "http://localhost:8000"
PACK_TYPE_ID = 1

# Minimal ABI for HodleagueCards.mintWithSignature
CARDS_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "openingId", "type": "uint256"},
            {"internalType": "uint256[]", "name": "cardIds", "type": "uint256[]"},
            {"internalType": "bytes32", "name": "serverSeed", "type": "bytes32"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "mintWithSignature",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def get_wallet_address() -> str:
    """Derive wallet address from HOT_WALLET_PRIVATE_KEY."""
    key = (Config.HOT_WALLET_PRIVATE_KEY or "").strip()
    if not key:
        raise SystemExit("HOT_WALLET_PRIVATE_KEY is not set")
    if key.startswith("0x"):
        key = key[2:]
    acc = Account.from_key(key)
    return acc.address


def main() -> None:
    global API_BASE, PACK_TYPE_ID
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=API_BASE, help="Backend API base URL")
    parser.add_argument("--pack-type-id", type=int, default=PACK_TYPE_ID, help="Pack type ID")
    args = parser.parse_args()
    API_BASE = args.api_url.rstrip("/")
    PACK_TYPE_ID = args.pack_type_id

    wallet = get_wallet_address()
    print(f"[Config] ENVIRONMENT={Config.ENVIRONMENT}, DEBUG={Config.DEBUG}, LOG_LEVEL={Config.LOG_LEVEL}")
    print(f"Using wallet: {wallet}")

    # 1. Test auth -> user JWT
    print("\n[1/7] Test auth (create/get user)...")
    r = requests.post(
        f"{API_BASE}/api/auth/test-verify",
        json={"wallet_address": wallet},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    user_jwt = data["access_token"]
    user_id = data["user"]["id"]
    print(f"  User ID: {user_id}")

    # 2. Admin login
    print("\n[2/7] Admin login...")
    r = requests.post(
        f"{API_BASE}/panel/auth/signin",
        json={
            "username": Config.ADMIN_USERNAME,
            "password": Config.ADMIN_PASSWORD,
        },
        timeout=10,
    )
    r.raise_for_status()
    admin_jwt = r.json()["access_token"]

    # 3. Admin mint pack (off-chain UserPack)
    print("\n[3/7] Admin mint pack (off-chain)...")
    r = requests.post(
        f"{API_BASE}/panel/packs/mint",
        json={
            "user_id": user_id,
            "pack_type_id": PACK_TYPE_ID,
            "amount": 1,
        },
        headers={"Authorization": f"Bearer {admin_jwt}"},
        timeout=10,
    )
    r.raise_for_status()
    mint_resp = r.json()
    print(
        f"  Granted {mint_resp['amount']} pack(s) of type {mint_resp['pack_type_id']} to user {mint_resp['user_id']}"
    )

    # 4. List user packs via admin to get user_pack_id
    print("\n[4/7] Fetching user packs (admin list)...")
    r = requests.get(
        f"{API_BASE}/panel/packs/list/{user_id}",
        headers={"Authorization": f"Bearer {admin_jwt}"},
        timeout=10,
    )
    r.raise_for_status()
    packs_data = r.json()
    packs = packs_data.get("packs", [])
    unopened = [p for p in packs if (not p.get("is_opened")) and p.get("pack_type_id") == PACK_TYPE_ID]
    if not unopened:
        raise SystemExit("No unopened packs of requested type found for user")
    user_pack_id = unopened[0]["id"]
    print(f"  Using user_pack_id={user_pack_id} (pack_type_id={PACK_TYPE_ID})")

    # 5. Prepare-open with user_pack_id + client_seed
    print("\n[5/7] Prepare-open (off-chain)...")
    client_seed_bytes = secrets.token_bytes(32)
    client_seed_hex = "0x" + client_seed_bytes.hex()
    r = requests.post(
        f"{API_BASE}/api/packs/prepare-open",
        json={"user_pack_id": user_pack_id, "client_seed": client_seed_hex},
        headers={"Authorization": f"Bearer {user_jwt}"},
        timeout=10,
    )
    r.raise_for_status()
    prep = r.json()
    pack_opening_id = prep["pack_opening_id"]
    card_ids = prep["card_ids"]
    server_seed_hex = prep["server_seed"]
    signature_hex = prep["signature"]
    print(f"  Pack opening ID: {pack_opening_id}")
    print(f"  Card IDs: {card_ids}")

    # 6. mintWithSignature on HodleagueCards
    print("\n[6/7] Submitting mintWithSignature tx...")
    key = (Config.HOT_WALLET_PRIVATE_KEY or "").strip()
    if key.startswith("0x"):
        key = key[2:]
    account = Account.from_key(key)
    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 15}))
    w3.middleware_onion.inject(_poa_middleware, layer=0)
    cards_contract = w3.eth.contract(
        address=Web3.to_checksum_address(Config.CARDS_CONTRACT_ADDRESS),
        abi=CARDS_ABI,
    )
    server_seed = bytes.fromhex(server_seed_hex.replace("0x", ""))
    if len(server_seed) != 32:
        server_seed = (server_seed + b"\x00" * 32)[:32]
    signature = bytes.fromhex(signature_hex.replace("0x", ""))
    nonce = w3.eth.get_transaction_count(account.address)
    tx = cards_contract.functions.mintWithSignature(
        account.address,
        pack_opening_id,
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
    tx_hash_hex = tx_hash.hex()
    if not tx_hash_hex.startswith("0x"):
        tx_hash_hex = "0x" + tx_hash_hex
    print(f"  mintWithSignature tx: {tx_hash_hex}")

    # 7. Wait for tx, confirm by tx hash, fetch metadata
    print("\n[7/7] Waiting for tx confirmation and confirming with backend...")
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    r = requests.post(
        f"{API_BASE}/api/packs/openings/{pack_opening_id}/confirm",
        json={"tx_hash": tx_hash_hex},
        headers={"Authorization": f"Bearer {user_jwt}"},
        timeout=15,
    )
    r.raise_for_status()
    status_data = r.json()
    nft_ids = status_data.get("nft_token_ids") or []
    print(f"  Status: {status_data.get('status', '')}, NFT token IDs: {nft_ids}")

    print("\nFetching metadata for first NFT...")
    if nft_ids:
        nft_id = nft_ids[0]
        r = requests.get(f"{API_BASE}/nft/cards/{nft_id}", timeout=5)
        r.raise_for_status()
        meta = r.json()
        print(f"  NFT {nft_id}: {meta.get('name', '')} - {meta.get('description', '')[:50]}...")
    else:
        print("  No nft_token_ids in response.")

    print("\nE2E test completed successfully.")


if __name__ == "__main__":
    main()
