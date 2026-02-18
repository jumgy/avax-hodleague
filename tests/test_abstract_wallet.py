# test_abstract_wallet.py
# Интерактивный скрипт проверки EIP-1271 для Abstract wallet.
# Запуск: python -m tests.test_abstract_wallet (не собирается pytest при tests/).
import requests
from web3 import Web3

API_URL = "http://localhost:8000"
ABSTRACT_WALLET_ADDRESS = "0xa9D155c56b003558BF9918862a263FE8C36c8F08"
ABSTRACT_RPC = "https://api.mainnet.abs.xyz"


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(ABSTRACT_RPC))
    code = w3.eth.get_code(ABSTRACT_WALLET_ADDRESS)
    if code == b"":
        print("[FAIL] This is not a smart contract wallet!")
        raise SystemExit(1)

    print(f"[OK] Testing Abstract smart contract wallet: {ABSTRACT_WALLET_ADDRESS}")
    print(f"[OK] Contract code length: {len(code)} bytes\n")

    print("[OK] Step 1: Requesting nonce...")
    response = requests.post(
        f"{API_URL}/api/auth/nonce",
        json={"wallet_address": ABSTRACT_WALLET_ADDRESS},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"[FAIL] {response.text}")
        raise SystemExit(1)

    data = response.json()
    message = data["message"]
    print(f"[OK] Got message:\n{message}\n")
    print("[WARNING] Now you need to:")
    print("1. Open Abstract wallet interface")
    print("2. Sign this message:")
    print(f"\n{message}\n")
    print("3. Paste the signature below:")
    signature = input("Signature (0x...): ").strip()

    print("\n[OK] Verifying EIP-1271 signature...")
    response = requests.post(
        f"{API_URL}/api/auth/verify",
        json={"wallet_address": ABSTRACT_WALLET_ADDRESS, "signature": signature},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"[FAIL] Verification failed: {response.status_code}\n{response.text}")
        raise SystemExit(1)

    result = response.json()
    print("\n[OK] EIP-1271 Authentication successful!")
    print(f"[OK] User: {result['user']['nickname']}")
    print(f"[OK] Token: {result['access_token'][:30]}...")


if __name__ == "__main__":
    main()
