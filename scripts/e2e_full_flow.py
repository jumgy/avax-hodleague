"""
Full E2E flow: wallet auth -> packs -> open pack -> mint cards -> register deck in tournament.

Flow:
  1. POST /api/auth/nonce -> sign message -> POST /api/auth/verify (session keeps cookie).
  2. GET /api/packs/available (check packs).
  3. Get user_pack_id via admin GET /panel/packs/list/{user_id} (requires ADMIN_USERNAME/PASSWORD).
  4. POST /api/packs/prepare-open -> card_ids, server_seed, signature.
  5. HodleagueCards.mintWithSignature(...) on-chain.
  6. POST /api/packs/openings/{id}/confirm with tx_hash (response includes full opening + cards_received, no extra GET).
  7. GET /api/users/me?include_cards=true -> pick 5 cards for deck.
  8. POST /api/tournaments/{id}/validate-deck -> deck_hash.
  9. TournamentRegistry.registerDeck(tournamentId, deckHash) on-chain.
  10. POST /api/tournaments/{id}/register with tx_hash and deck_composition.

Required:
  - WALLET_PRIVATE_KEY: set in script (placeholder below) or env; testnet wallet with some AVAX.
  - Backend .env: CARDS_CONTRACT_ADDRESS, TOURNAMENT_CONTRACT_ADDRESS, WEB3_PROVIDER_URL, CHAIN_ID (e.g. 43113).
  - For step 3: ADMIN_USERNAME, ADMIN_PASSWORD in .env (to list user packs; no public endpoint for pack IDs).

Usage:
  python -m scripts.e2e_full_flow
  python -m scripts.e2e_full_flow --api-url https://avax.back.hodleague.com --tournament-id 1
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

try:
    from web3.middleware import ExtraDataToPOAMiddleware as _poa_middleware
except ImportError:
    from web3.middleware import geth_poa_middleware as _poa_middleware

# --------------- CONFIG (override via env or CLI) ---------------
API_BASE = os.getenv("E2E_API_URL", "https://avax.back.hodleague.com")
TOURNAMENT_ID = int(os.getenv("E2E_TOURNAMENT_ID", "1"))
# Avalanche Fuji testnet
CHAIN_ID = int(os.getenv("CHAIN_ID", "43113"))
WEB3_PROVIDER_URL = os.getenv("WEB3_PROVIDER_URL", "https://api.avax-test.network/ext/bc/C/rpc")
CARDS_CONTRACT_ADDRESS = os.getenv("CARDS_CONTRACT_ADDRESS", "0xA8E0d17d72d97CB5C5Bf7f93eFaDc823BB2311eD")
TOURNAMENT_CONTRACT_ADDRESS = os.getenv("TOURNAMENT_CONTRACT_ADDRESS", "0x2Fa5F1C94061Ff8d1D8706D7FC184F9162C7d444")

# Insert your testnet wallet private key here (or set WALLET_PRIVATE_KEY in .env; do not commit).
WALLET_PRIVATE_KEY = ""

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
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "used",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]

TOURNAMENT_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "tournamentId", "type": "uint256"},
            {"internalType": "bytes32", "name": "deckHash", "type": "bytes32"},
        ],
        "name": "registerDeck",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def get_wallet():
    key = (WALLET_PRIVATE_KEY or "").strip()
    if not key or key == "YOUR_PRIVATE_KEY_HEX_HERE":
        raise SystemExit("Set WALLET_PRIVATE_KEY in the script or in .env (testnet wallet with AVAX).")
    if key.startswith("0x"):
        key = key[2:]
    return Account.from_key(key)


def main():
    global API_BASE, TOURNAMENT_ID
    parser = argparse.ArgumentParser(description="E2E: auth -> packs -> open -> mint -> tournament register")
    parser.add_argument("--api-url", default=API_BASE, help="Backend API base URL")
    parser.add_argument("--tournament-id", type=int, default=TOURNAMENT_ID, help="Tournament ID to register for")
    args = parser.parse_args()
    API_BASE = args.api_url.rstrip("/")
    TOURNAMENT_ID = args.tournament_id

    account = get_wallet()
    wallet = account.address
    if not wallet.startswith("0x"):
        wallet = "0x" + wallet
    wallet_lower = wallet.lower()

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    # ---------- 1. Auth: nonce -> sign -> verify ----------
    print("\n[1/10] Auth: request nonce...")
    r = session.post(f"{API_BASE}/api/auth/nonce", json={"wallet_address": wallet_lower}, timeout=15)
    r.raise_for_status()
    data = r.json()
    message = data["message"]
    print(f"  Message to sign: {message[:60]}...")

    print("  Signing message...")
    signable = encode_defunct(text=message)
    signed = account.sign_message(signable)
    signature_hex = signed.signature.hex()

    print("  Verify (login)...")
    r = session.post(
        f"{API_BASE}/api/auth/verify",
        json={"wallet_address": wallet_lower, "signature": signature_hex},
        timeout=15,
    )
    r.raise_for_status()
    auth_data = r.json()
    user_id = auth_data["user"]["id"]
    packs_granted = auth_data.get("packs_granted") or 0
    print(f"  User ID: {user_id}, packs_granted: {packs_granted}")

    # ---------- 2. Available packs (list with user_pack_id per pack) ----------
    print("\n[2/10] GET /api/packs/available...")
    r = session.get(f"{API_BASE}/api/packs/available", timeout=10)
    r.raise_for_status()
    avail = r.json()
    packs = avail.get("packs", [])
    total = avail.get("available_packs", 0)
    print(f"  Available packs: {total}")
    if total == 0:
        print("  No packs to open. Ensure backend granted packs on first login or run seed_common_pack_type.")
        # Continue anyway to try tournament with existing cards

    # ---------- 3. Unopened packs (from /packs/available, each has user_pack_id) ----------
    print("\n[3/10] Unopened packs from /packs/available...")
    unopened = [{"id": p["user_pack_id"]} for p in packs]
    if not unopened:
        print("  No unopened packs for this user.")
        pack_opening_id = None
    else:
        print(f"  Unopened packs: {len(unopened)}")

    w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URL, request_kwargs={"timeout": 20}))
    w3.middleware_onion.inject(_poa_middleware, layer=0)
    cards_contract = w3.eth.contract(
        address=Web3.to_checksum_address(CARDS_CONTRACT_ADDRESS),
        abi=CARDS_ABI,
    )

    # ---------- 4 & 5 & 6. Prepare open -> mint -> confirm (skip packs whose opening already used on-chain) ----------
    pack_opening_id = None
    if unopened:
        for pack_idx, pack_item in enumerate(unopened):
            user_pack_id = pack_item["id"]
            print(f"\n[4/10] POST /api/packs/prepare-open (user_pack_id={user_pack_id})...")
            client_seed = secrets.token_bytes(32)
            client_seed_hex = "0x" + client_seed.hex()
            r = session.post(
                f"{API_BASE}/api/packs/prepare-open",
                json={"user_pack_id": user_pack_id, "client_seed": client_seed_hex},
                timeout=15,
            )
            r.raise_for_status()
            prep = r.json()
            pack_opening_id = prep["pack_opening_id"]
            card_ids = prep["card_ids"]
            server_seed_hex = prep["server_seed"]
            sig_hex = prep["signature"]
            print(f"  pack_opening_id={pack_opening_id}, card_ids={card_ids}")

            # If this opening was already minted on-chain (e.g. previous run), try next pack.
            try:
                already_used = cards_contract.functions.used(pack_opening_id).call()
            except Exception:
                already_used = False
            if already_used:
                print(f"  Opening {pack_opening_id} already used on-chain, trying next pack...")
                if pack_idx + 1 >= len(unopened):
                    print("  No more unopened packs with unused opening.")
                    pack_opening_id = None
                continue

            print("\n[5/10] mintWithSignature on HodleagueCards...")
            server_seed_b = bytes.fromhex(server_seed_hex.replace("0x", ""))
            if len(server_seed_b) != 32:
                server_seed_b = (server_seed_b + b"\x00" * 32)[:32]
            sig_b = bytes.fromhex(sig_hex.replace("0x", ""))
            nonce = w3.eth.get_transaction_count(account.address)
            tx = cards_contract.functions.mintWithSignature(
                Web3.to_checksum_address(wallet),
                pack_opening_id,
                card_ids,
                server_seed_b,
                sig_b,
            ).build_transaction(
                {
                    "from": account.address,
                    "gas": 500_000,
                    "chainId": CHAIN_ID,
                    "nonce": nonce,
                }
            )
            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash
            if not tx_hash_hex.startswith("0x"):
                tx_hash_hex = "0x" + tx_hash_hex
            print(f"  tx: {tx_hash_hex}")

            print("\n[6/10] Wait for tx and confirm with backend...")
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            r = session.post(
                f"{API_BASE}/api/packs/openings/{pack_opening_id}/confirm",
                json={"tx_hash": tx_hash_hex},
                timeout=15,
            )
            r.raise_for_status()
            conf = r.json()
            print(f"  Status: {conf.get('status', '')}")
            cards_received = conf.get("cards_received") or []
            if cards_received:
                print(f"  Cards received (from confirm response): {len(cards_received)}")
            break
        else:
            pack_opening_id = None

    if pack_opening_id is None and unopened:
        print("\n[4-6/10] All prepared openings were already used on-chain; skipped mint.")
    elif pack_opening_id is None:
        print("\n[4-6/10] Skipped (no pack to open).")

    # ---------- 7. My cards ----------
    print("\n[7/10] GET /api/users/me?include_cards=true...")
    r = session.get(f"{API_BASE}/api/users/me", params={"include_cards": "true"}, timeout=10)
    r.raise_for_status()
    me = r.json()
    cards = me.get("cards") or []
    print(f"  User cards: {len(cards)}")
    if len(cards) < 5:
        print("  Need at least 5 cards to register a deck. Open more packs or add cards.")
        return

    # Build deck: 5 cards, one per token, total weight <= 35
    weight_limit = 35
    by_token = {}
    for c in cards:
        uid = c.get("user_card_id")
        sym = c.get("token_symbol") or ""
        w = c.get("token_weight") or 0
        if uid is None:
            continue
        if sym not in by_token or by_token[sym][1] > w:
            by_token[sym] = (uid, w)
    one_per_token = sorted(by_token.values(), key=lambda x: x[1])
    if len(one_per_token) < 5:
        print("  Need at least 5 different tokens in collection to build a deck.")
        return
    deck_composition = [uid for (uid, _) in one_per_token[:5]]
    total_weight = sum(w for (_, w) in one_per_token[:5])
    if total_weight > weight_limit:
        print(f"  Lightest 5 cards total weight {total_weight} > limit {weight_limit}. Add more cards or reduce weight.")
        return
    print(f"  Deck (user_card_ids): {deck_composition}, total_weight={total_weight}")

    # ---------- 8. Validate deck ----------
    print("\n[8/10] POST validate-deck...")
    r = session.post(
        f"{API_BASE}/api/tournaments/{TOURNAMENT_ID}/validate-deck",
        json={"deck_composition": deck_composition},
        timeout=15,
    )
    r.raise_for_status()
    val = r.json()
    if not val.get("valid"):
        print(f"  Validation failed: {val.get('message', '')}")
        return
    deck_hash_hex = val.get("deck_hash", "")
    if not deck_hash_hex.startswith("0x"):
        deck_hash_hex = "0x" + deck_hash_hex
    print(f"  deck_hash: {deck_hash_hex[:20]}...")

    # ---------- 9. registerDeck on-chain ----------
    print("\n[9/10] registerDeck on TournamentRegistry...")
    w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URL, request_kwargs={"timeout": 20}))
    w3.middleware_onion.inject(_poa_middleware, layer=0)
    tournament_contract = w3.eth.contract(
        address=Web3.to_checksum_address(TOURNAMENT_CONTRACT_ADDRESS),
        abi=TOURNAMENT_ABI,
    )
    deck_hash_bytes = bytes.fromhex(deck_hash_hex.replace("0x", ""))
    if len(deck_hash_bytes) != 32:
        deck_hash_bytes = (deck_hash_bytes + b"\x00" * 32)[:32]
    nonce = w3.eth.get_transaction_count(account.address)
    tx = tournament_contract.functions.registerDeck(TOURNAMENT_ID, deck_hash_bytes).build_transaction(
        {
            "from": account.address,
            "gas": 200_000,
            "chainId": CHAIN_ID,
            "nonce": nonce,
        }
    )
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    reg_tx_hex = tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash
    if not reg_tx_hex.startswith("0x"):
        reg_tx_hex = "0x" + reg_tx_hex
    print(f"  tx: {reg_tx_hex}")

    # ---------- 10. Final register with backend ----------
    print("\n[10/10] POST register with tx_hash...")
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    r = session.post(
        f"{API_BASE}/api/tournaments/{TOURNAMENT_ID}/register",
        json={"deck_composition": deck_composition, "tx_hash": reg_tx_hex},
        timeout=15,
    )
    r.raise_for_status()
    reg_resp = r.json()
    print(f"  success: {reg_resp.get('success')}, deck_id: {reg_resp.get('deck_id')}")

    print("\nE2E full flow completed successfully.")


if __name__ == "__main__":
    main()
