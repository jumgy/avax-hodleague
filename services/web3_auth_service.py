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

    async def verify_signature(self, wallet_address: str, signature: str) -> bool:
        """Верифицируем подпись для EOA и смарт-контрактных кошельков"""
        wallet_address = wallet_address.lower()
        
        # Проверяем, есть ли nonce для этого кошелька
        if wallet_address not in self.nonce_storage:
            logger.warning(f"No nonce found for wallet: {wallet_address[:10]}...")
            return False
        
        nonce_data = self.nonce_storage[wallet_address]
        
        # Проверяем, не истек ли nonce
        if time.time() > nonce_data['expires_at']:
            logger.warning(f"Nonce expired for wallet: {wallet_address[:10]}...")
            del self.nonce_storage[wallet_address]
            return False
        
        try:
            message = nonce_data['message']
            message_hash = encode_defunct(text=message)
            
            # 1. Сначала пробуем как обычный кошелек (EOA)
            try:
                recovered_address = Account.recover_message(message_hash, signature=signature)
                
                if recovered_address.lower() == wallet_address.lower():
                    logger.info(f"✅ Valid EOA signature for wallet: {wallet_address[:10]}...")
                    del self.nonce_storage[wallet_address]
                    return True
            except Exception as eoa_error:
                logger.debug(f"EOA recovery failed, trying EIP-1271: {eoa_error}")
            
            # 2. Если EOA не сработало, пробуем EIP-1271 (смарт-контракт)
            is_valid = await self._verify_eip1271_signature(
                wallet_address, 
                message, 
                signature
            )
            
            if is_valid:
                logger.info(f"✅ Valid EIP-1271 signature for wallet: {wallet_address[:10]}...")
                del self.nonce_storage[wallet_address]
                return True
            
            logger.warning(f"❌ Invalid signature for wallet: {wallet_address[:10]}...")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying signature: {e}", exc_info=True)
            return False

    async def _verify_eip1271_signature(
        self, 
        contract_address: str, 
        message: str, 
        signature: str
    ) -> bool:
        """Проверка подписи через EIP-1271 для смарт-контрактных кошельков"""
        try:
            # Проверяем, что Web3 инициализирован
            if not self.w3:
                logger.error("Web3 provider not initialized")
                return False
            
            # Проверяем, является ли адрес контрактом
            checksum_address = to_checksum_address(contract_address)
            code = self.w3.eth.get_code(checksum_address)
            
            if code == b'' or code == b'\x00' or code.hex() == '0x':
                logger.debug(f"Address {contract_address[:10]}... is not a contract (EOA)")
                return False
            
            logger.info(f"Address {contract_address[:10]}... is a smart contract, verifying with EIP-1271")
            
            # Кодируем сообщение так же, как для EOA
            message_hash = encode_defunct(text=message)
            
            # Получаем hash bytes
            if hasattr(message_hash, 'body'):
                hash_bytes = message_hash.body
            elif hasattr(message_hash, 'message_hash'):
                hash_bytes = message_hash.message_hash
            else:
                hash_bytes = message_hash
            
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
            
            # Создаем контракт
            contract = self.w3.eth.contract(
                address=checksum_address,
                abi=eip1271_abi
            )
            
            # Убираем '0x' из подписи если есть
            signature_bytes = bytes.fromhex(signature[2:] if signature.startswith('0x') else signature)
            
            # Вызываем isValidSignature
            magic_value = contract.functions.isValidSignature(
                hash_bytes,
                signature_bytes
            ).call()
            
            # Проверяем magic value
            magic_hex = magic_value.hex() if isinstance(magic_value, bytes) else hex(magic_value)[2:]
            expected_magic = self.EIP1271_MAGIC_VALUE[2:]
            
            is_valid = magic_hex == expected_magic
            
            logger.info(f"EIP-1271 verification: {'✅ VALID' if is_valid else '❌ INVALID'} (magic: 0x{magic_hex})")
            return is_valid
            
        except Exception as e:
            logger.error(f"EIP-1271 verification error: {e}", exc_info=True)
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
            
            # Создаем нового пользователя
            if not nickname:
                nickname = f"Player{wallet_address[2:8].upper()}"
            
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
            
            # Дефолтный avatar
            if not avatar_url:
                avatar_url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={wallet_address}"
            
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