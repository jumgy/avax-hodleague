# test_abstract_wallet.py
import requests
from web3 import Web3

# Конфигурация
API_URL = "http://localhost:8000"  # Или твой бек
ABSTRACT_WALLET_ADDRESS = "0xa9D155c56b003558BF9918862a263FE8C36c8F08"  # Адрес твоего Abstract кошелька
ABSTRACT_RPC = "https://api.mainnet.abs.xyz"

w3 = Web3(Web3.HTTPProvider(ABSTRACT_RPC))

# Проверяем, что это контракт
code = w3.eth.get_code(ABSTRACT_WALLET_ADDRESS)
if code == b'':
    print("❌ This is not a smart contract wallet!")
    exit(1)

print(f"✅ Testing Abstract smart contract wallet: {ABSTRACT_WALLET_ADDRESS}")
print(f"📝 Contract code length: {len(code)} bytes\n")

# Шаг 1: Получаем nonce
print("📝 Step 1: Requesting nonce...")
response = requests.post(
    f"{API_URL}/api/auth/nonce",
    json={"wallet_address": ABSTRACT_WALLET_ADDRESS}
)

if response.status_code != 200:
    print(f"❌ Failed: {response.text}")
    exit(1)

data = response.json()
message = data["message"]
print(f"✅ Got message:\n{message}\n")

print("⚠️  Now you need to:")
print("1. Open Abstract wallet interface")
print("2. Sign this message:")
print(f"\n{message}\n")
print("3. Paste the signature below:")

signature = input("Signature (0x...): ").strip()

# Шаг 2: Верифицируем
print("\n🔐 Verifying EIP-1271 signature...")
response = requests.post(
    f"{API_URL}/api/auth/verify",
    json={
        "wallet_address": ABSTRACT_WALLET_ADDRESS,
        "signature": signature
    }
)

if response.status_code != 200:
    print(f"❌ Verification failed: {response.status_code}")
    print(response.text)
    exit(1)

result = response.json()
print(f"\n✅ EIP-1271 Authentication successful!")
print(f"👤 User: {result['user']['nickname']}")
print(f"🎟️  Token: {result['access_token'][:30]}...")