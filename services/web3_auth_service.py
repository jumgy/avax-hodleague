# services/web3_auth_service.py
import secrets
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from eth_account.messages import encode_defunct
from eth_account import Account
import jwt
import logging
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3
from eth_utils import to_checksum_address

from models.database import get_async_db
from models.user_models import User
from config import Config

logger = logging.getLogger(__name__)


class Web3AuthService:
    def __init__(self):
        # Храним nonce в памяти (в продакшене лучше Redis)
        self.nonce_storage: Dict[str, Dict] = {}
        self.cleanup_interval = 600  # 10 минут для cleanup
        
        # Web3 provider для EIP-1271
        try:
            self.w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
            if self.w3.is_connected():
                logger.info(f"✅ Web3 connected to {Config.WEB3_PROVIDER_URL}")
            else:
                logger.warning(f"⚠️ Web3 provider not connected: {Config.WEB3_PROVIDER_URL}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Web3 provider: {e}")
            self.w3 = None
        
        # EIP-1271 magic value
        self.EIP1271_MAGIC_VALUE = "0x1626ba7e"

    def generate_nonce(self, wallet_address: str) -> str:
        """Генерируем nonce для подписи"""
        wallet_address = wallet_address.lower()
        
        # Генерируем случайную строку
        nonce = secrets.token_hex(16)
        timestamp = int(time.time())
        
        # Создаем сообщение для подписи
        message = f"Welcome to Hodleague!\n\nPlease sign this message to authenticate your wallet.\n\nWallet: {wallet_address}\nNonce: {nonce}\nTimestamp: {timestamp}"
        
        # Сохраняем nonce с временной меткой
        self.nonce_storage[wallet_address] = {
            'nonce': nonce,
            'message': message,
            'timestamp': timestamp,
            'expires_at': timestamp + 300  # 5 минут на подпись
        }
        
        # Очищаем старые nonce
        self._cleanup_expired_nonces()
        
        logger.info(f"Generated nonce for wallet: {wallet_address[:10]}...")
        return message

    def _decode_abstract_signature(self, signature: str) -> str:
        """Декодирует ABI-encoded подпись от Abstract Global Wallet"""
        try:
            sig = signature[2:] if signature.startswith('0x') else signature
            
            if len(sig) <= 132:
                return signature
            

            data = sig[128:]
            
            sig_length_hex = data[:64]
            sig_length = int(sig_length_hex, 16)
            
            actual_signature = data[64:64 + (sig_length * 2)]
            
            logger.info(f"✅ Decoded Abstract signature: {len(actual_signature)//2} bytes")
            return f"0x{actual_signature}"
            
        except Exception as e:
            logger.debug(f"Not an Abstract signature, using as-is: {e}")
            return signature

    async def verify_signature(self, wallet_address: str, signature: str) -> bool:
        """Верифицируем подпись для EOA и смарт-контрактных кошельков"""
        wallet_address = wallet_address.lower()
        
        if wallet_address not in self.nonce_storage:
            logger.warning(f"❌ No nonce found for wallet: {wallet_address[:10]}...")
            return False
        
        nonce_data = self.nonce_storage[wallet_address]
        
        if time.time() > nonce_data['expires_at']:
            logger.warning(f"❌ Nonce expired for wallet: {wallet_address[:10]}...")
            del self.nonce_storage[wallet_address]
            return False
        
        try:
            message = nonce_data['message']
            
            logger.warning(f"🔍 VERIFYING: {wallet_address[:10]}...")
            logger.warning(f"   Signature length: {len(signature)}")
            
            # Проверяем - это контракт или EOA?
            checksum_address = to_checksum_address(wallet_address)
            code = self.w3.eth.get_code(checksum_address)
            is_contract = code != b'' and code != b'\x00' and code.hex() != '0x'
            
            logger.warning(f"   Is contract: {is_contract}")
            
            if not is_contract:
                # Обычный кошелек (Rabby)
                logger.warning(f"   Trying EOA...")
                message_hash = encode_defunct(text=message)
                decoded_signature = self._decode_abstract_signature(signature)
                
                try:
                    recovered_address = Account.recover_message(message_hash, signature=decoded_signature)
                    if recovered_address.lower() == wallet_address.lower():
                        logger.warning(f"✅ VALID EOA signature!")
                        del self.nonce_storage[wallet_address]
                        return True
                except Exception as e:
                    logger.warning(f"   EOA failed: {str(e)[:50]}")
                
                return False
            
            # Смарт-контракт (Abstract)
            logger.warning(f"   Smart contract detected, using EIP-1271...")
            
            # 🔥 ДЛЯ EIP-1271 ПЕРЕДАЕМ ОРИГИНАЛЬНУЮ ПОДПИСЬ БЕЗ ДЕКОДИРОВАНИЯ
            is_valid = await self._verify_eip1271_signature(
                wallet_address,
                message,
                signature  # ОРИГИНАЛ!
            )
            
            if is_valid:
                logger.warning(f"✅ VALID EIP-1271 signature!")
                del self.nonce_storage[wallet_address]
                return True
            
            logger.warning(f"❌ INVALID signature")
            return False
            
        except Exception as e:
            logger.warning(f"❌ ERROR: {e}")
            return False

    async def _verify_eip1271_signature(
        self, 
        contract_address: str, 
        message: str, 
        signature: str
    ) -> bool:
        """Проверка подписи через EIP-1271 для Abstract Global Wallet"""
        try:
            if not self.w3:
                logger.warning("❌ Web3 not initialized")
                return False
            
            # Проверяем сеть
            chain_id = self.w3.eth.chain_id
            logger.warning(f"   Chain ID: {chain_id}")
            
            checksum_address = to_checksum_address(contract_address)
            
            # EIP-1271 ABI
            eip1271_abi = [{
                "constant": True,
                "inputs": [
                    {"name": "_hash", "type": "bytes32"},
                    {"name": "_signature", "type": "bytes"}
                ],
                "name": "isValidSignature",
                "outputs": [{"name": "magicValue", "type": "bytes4"}],
                "type": "function"
            }]
            
            contract = self.w3.eth.contract(
                address=checksum_address,
                abi=eip1271_abi
            )
            
            # Подпись как bytes (БЕЗ декодирования!)
            signature_bytes = bytes.fromhex(
                signature[2:] if signature.startswith('0x') else signature
            )
            
            logger.warning(f"   Signature bytes: {len(signature_bytes)}")
            
            # 🔥 ПРОБУЕМ ТРИ ВАРИАНТА HASH
            
            # Вариант 1: EIP-191 prefixed
            message_hash_v1 = encode_defunct(text=message)
            if hasattr(message_hash_v1, 'body'):
                hash_v1 = message_hash_v1.body
            else:
                hash_v1 = Web3.keccak(
                    b'\x19Ethereum Signed Message:\n' + 
                    str(len(message)).encode('utf-8') + 
                    message.encode('utf-8')
                )
            
            # Вариант 2: Просто keccak256(message)
            hash_v2 = Web3.keccak(text=message)
            
            # Вариант 3: keccak256(bytes(message))
            hash_v3 = Web3.keccak(message.encode('utf-8'))
            
            hashes = [
                ('EIP-191', hash_v1),
                ('keccak(text)', hash_v2),
                ('keccak(bytes)', hash_v3)
            ]
            
            logger.warning(f"   Trying {len(hashes)} hash variants...")
            
            for name, hash_bytes in hashes:
                try:
                    logger.warning(f"   → Testing {name}: {hash_bytes.hex()[:20]}...")
                    
                    magic_value = contract.functions.isValidSignature(
                        hash_bytes,
                        signature_bytes
                    ).call()
                    
                    if isinstance(magic_value, bytes):
                        magic_hex = '0x' + magic_value.hex()
                    elif isinstance(magic_value, int):
                        magic_hex = hex(magic_value)
                    else:
                        magic_hex = str(magic_value)
                    
                    expected = self.EIP1271_MAGIC_VALUE
                    
                    logger.warning(f"     Received: {magic_hex}")
                    logger.warning(f"     Expected: {expected}")
                    
                    received_clean = magic_hex.lower().replace('0x', '')
                    expected_clean = expected.lower().replace('0x', '')
                    
                    if received_clean == expected_clean:
                        logger.warning(f"     ✅ MATCH with {name}!")
                        return True
                    else:
                        logger.warning(f"     ❌ No match")
                        
                except Exception as e:
                    logger.warning(f"     ❌ Failed: {str(e)[:80]}")
                    continue
            
            logger.warning(f"   ❌ All variants failed")
            return False
            
        except Exception as e:
            logger.warning(f"❌ EIP-1271 error: {e}")
            return False

    async def get_user_by_wallet(self, wallet_address: str, db: AsyncSession) -> Optional[User]:
        """Получаем пользователя по wallet address"""
        try:
            wallet_address = wallet_address.lower()
            query = select(User).where(User.wallet_address == wallet_address)
            result = await db.execute(query)
            user = result.scalar_one_or_none()
            return user
        except Exception as e:
            logger.error(f"Error getting user by wallet: {e}")
            return None

    async def fetch_abstract_profile(self, wallet_address: str) -> Dict[str, Optional[str]]:
        """
        Получить профиль пользователя из Abstract API
        
        Returns:
            dict: {'nickname': str, 'avatar_url': str} или пустой dict при ошибке
        """
        try:
            url = f"https://backend.portal.abs.xyz/api/user/address/{wallet_address.lower()}"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    url,
                    headers={
                        'Accept': 'application/json',
                        'User-Agent': 'Hodleague/1.0'
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    user_data = data.get('user', {})
                    
                    nickname = user_data.get('name')
                    avatar_url = user_data.get('overrideProfilePictureUrl')
                    
                    logger.info(
                        f"✅ Fetched Abstract profile for {wallet_address[:10]}...: "
                        f"nickname={nickname}, avatar={'Yes' if avatar_url else 'No'}"
                    )
                    
                    return {
                        'nickname': nickname,
                        'avatar_url': avatar_url
                    }
                else:
                    logger.debug(
                        f"Abstract API returned {response.status_code} for {wallet_address[:10]}..."
                    )
                    
        except httpx.TimeoutException:
            logger.warning(f"Abstract API timeout for {wallet_address[:10]}...")
        except Exception as e:
            logger.debug(f"Failed to fetch Abstract profile: {e}")
        
        return {}

    async def create_or_get_user(
        self, 
        wallet_address: str, 
        db: AsyncSession,
        nickname: str = None, 
        avatar_url: str = None
    ) -> User:
        """Создаем или получаем пользователя"""
        try:
            wallet_address = wallet_address.lower()
            
            # Ищем существующего пользователя
            existing_query = select(User).where(User.wallet_address == wallet_address)
            existing_result = await db.execute(existing_query)
            existing_user = existing_result.scalar_one_or_none()
            
            if existing_user:
                logger.info(f"Existing user login: {existing_user.nickname}")
                return existing_user
            

            if not nickname or not avatar_url:
                logger.info(f"Fetching profile from Abstract API for {wallet_address[:10]}...")
                abstract_profile = await self.fetch_abstract_profile(wallet_address)
                
                # Используем данные из Abstract, если они есть
                if not nickname and abstract_profile.get('nickname'):
                    nickname = abstract_profile['nickname']
                    logger.info(f"Using Abstract nickname: {nickname}")
                
                if not avatar_url and abstract_profile.get('avatar_url'):
                    avatar_url = abstract_profile['avatar_url']
                    logger.info(f"Using Abstract avatar")
            
            if not nickname:
                nickname = f"Player{wallet_address[2:8].upper()}"
                logger.info(f"Using default nickname: {nickname}")
            
            # Проверяем уникальность nickname
            counter = 1
            original_nickname = nickname
            while True:
                check_query = select(User).where(User.nickname == nickname)
                check_result = await db.execute(check_query)
                if check_result.scalar_one_or_none() is None:
                    break
                nickname = f"{original_nickname}{counter}"
                counter += 1
            
            # Генерируем referral_route на основе nickname
            referral_route = f"{nickname}{secrets.randbelow(9999):04d}"
            while True:
                check_query = select(User).where(User.referral_route == referral_route)
                check_result = await db.execute(check_query)
                if check_result.scalar_one_or_none() is None:
                    break
                referral_route = f"{nickname}{secrets.randbelow(9999):04d}"
            
            # Дефолтный avatar если не нашли в Abstract
            if not avatar_url:
                avatar_url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={wallet_address}"
                logger.info(f"Using default avatar (Dicebear)")
            
            # Создаем пользователя
            new_user = User(
                wallet_address=wallet_address,
                nickname=nickname,
                referral_route=referral_route,
                avatar_url=avatar_url
            )
            
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            logger.info(f"New user created: {new_user.nickname} ({wallet_address[:10]}...)")
            return new_user
            
        except Exception as e:
            logger.error(f"Error creating/getting user: {e}")
            await db.rollback()
            raise

    def create_jwt_token(self, user: User) -> str:
        """Создаем JWT токен для пользователя"""
        payload = {
            'user_id': user.id,
            'wallet_address': user.wallet_address,
            'nickname': user.nickname,
            'exp': datetime.utcnow() + timedelta(days=7),
            'iat': datetime.utcnow(),
            'type': 'user_access'
        }
        return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")

    def verify_jwt_token(self, token: str) -> Optional[Dict]:
        """Проверяем JWT токен"""
        try:
            payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
            if payload.get('type') != 'user_access':
                return None
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("User JWT expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid user JWT: {e}")
            return None

    def _cleanup_expired_nonces(self):
        """Очищаем истекшие nonce"""
        current_time = time.time()
        expired_wallets = [
            wallet for wallet, data in self.nonce_storage.items()
            if data['expires_at'] < current_time
        ]
        
        for wallet in expired_wallets:
            del self.nonce_storage[wallet]
        
        if expired_wallets:
            logger.info(f"Cleaned up {len(expired_wallets)} expired nonces")

# Singleton
web3_auth_service = Web3AuthService()