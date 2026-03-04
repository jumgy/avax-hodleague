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
        # Nonce stored in memory (use Redis in production)
        self.nonce_storage: Dict[str, Dict] = {}
        self.cleanup_interval = 600  # 10 min cleanup

        # Web3 provider for EIP-1271
        try:
            self.w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
            if self.w3.is_connected():
                logger.info(f"Web3 connected to {Config.WEB3_PROVIDER_URL}")
            else:
                logger.warning(f"Web3 provider not connected: {Config.WEB3_PROVIDER_URL}")
        except Exception as e:
            logger.error(f"Failed to initialize Web3 provider: {e}")
            self.w3 = None
        
        # EIP-1271 magic value
        self.EIP1271_MAGIC_VALUE = "0x1626ba7e"

    def generate_nonce(self, wallet_address: str) -> str:
        """Generate nonce for signature."""
        wallet_address = wallet_address.lower()

        nonce = secrets.token_hex(16)
        timestamp = int(time.time())

        message = f"Welcome to Hodleague!\n\nPlease sign this message to authenticate your wallet.\n\nWallet: {wallet_address}\nNonce: {nonce}\nTimestamp: {timestamp}"
        
        # Store nonce with timestamp
        self.nonce_storage[wallet_address] = {
            'nonce': nonce,
            'message': message,
            'timestamp': timestamp,
            'expires_at': timestamp + 300  # 5 min to sign
        }

        self._cleanup_expired_nonces()

        logger.info(f"Generated nonce for wallet: {wallet_address[:10]}...")
        return message

    def _decode_abstract_signature(self, signature: str) -> str:
        """Decode ABI-encoded signature from Abstract Global Wallet."""
        try:
            sig = signature[2:] if signature.startswith('0x') else signature
            
            if len(sig) <= 132:
                return signature
            

            data = sig[128:]
            
            sig_length_hex = data[:64]
            sig_length = int(sig_length_hex, 16)
            
            actual_signature = data[64:64 + (sig_length * 2)]
            
            logger.info(f"Decoded Abstract signature: {len(actual_signature)//2} bytes")
            return f"0x{actual_signature}"
            
        except Exception as e:
            logger.debug(f"Not an Abstract signature, using as-is: {e}")
            return signature


    async def verify_signature(self, wallet_address: str, signature: str) -> bool:
        """Verify signature (same logic as viem.verifyMessage())."""
        wallet_address = wallet_address.lower()

        if wallet_address not in self.nonce_storage:
            logger.warning(f"No nonce found for wallet: {wallet_address[:10]}...")
            return False
        
        nonce_data = self.nonce_storage[wallet_address]
        
        if time.time() > nonce_data['expires_at']:
            logger.warning(f"Nonce expired for wallet: {wallet_address[:10]}...")
            del self.nonce_storage[wallet_address]
            return False
        
        try:
            message = nonce_data['message']
            
            # 1. Check EOA vs contract
            checksum_address = to_checksum_address(wallet_address)
            code = self.w3.eth.get_code(checksum_address)
            is_contract = len(code) > 0 and code != b'\x00'
            
            
            if not is_contract:
                # EOA verification
                return await self._verify_eoa_signature(wallet_address, message, signature)
            else:
                # Smart contract (EIP-1271) verification
                return await self._verify_eip1271_viem_style(wallet_address, message, signature)
            
        except Exception as e:
            logger.warning(f"❌ ERROR: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            return False

    async def _verify_eoa_signature(self, wallet_address: str, message: str, signature: str) -> bool:
        """EOA verification"""
        try:
            message_hash = encode_defunct(text=message)
            recovered_address = Account.recover_message(message_hash, signature=signature)
            
            if recovered_address.lower() == wallet_address.lower():
                del self.nonce_storage[wallet_address]
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"EOA verification failed: {e}")
            return False


    async def _verify_eip1271_viem_style(self, wallet_address: str, message: str, signature: str) -> bool:
        """EIP-1271 verification for smart contract wallets."""
        try:
            checksum_address = to_checksum_address(wallet_address)
            
            # EIP-1271 ABI
            eip1271_abi = [{
                "inputs": [
                    {"name": "hash", "type": "bytes32"},
                    {"name": "signature", "type": "bytes"}
                ],
                "name": "isValidSignature",
                "outputs": [{"name": "magicValue", "type": "bytes4"}],
                "stateMutability": "view",
                "type": "function"
            }]
            
            contract = self.w3.eth.contract(
                address=checksum_address,
                abi=eip1271_abi
            )
            
            # Build EIP-191 hash.
            message_bytes = message.encode('utf-8')
            prefix = b'\x19Ethereum Signed Message:\n'
            length = str(len(message_bytes)).encode('utf-8')
            message_hash = Web3.keccak(prefix + length + message_bytes)
            
            # Convert signature to bytes.
            signature_bytes = bytes.fromhex(signature[2:] if signature.startswith('0x') else signature)
            
            # Call contract.
            magic_value = contract.functions.isValidSignature(
                message_hash,
                signature_bytes
            ).call()
            
            # Check magic value
            if isinstance(magic_value, bytes):
                result_hex = magic_value.hex()
            elif isinstance(magic_value, int):
                result_hex = format(magic_value, '08x')
            else:
                result_hex = str(magic_value).replace('0x', '')
            
            is_valid = result_hex.lower() == "1626ba7e"
            
            if is_valid:
                del self.nonce_storage[wallet_address]
            
            return is_valid
            
        except Exception as e:
            logger.error(f"EIP-1271 verification error: {e}")
            return False

    async def get_user_by_wallet(self, wallet_address: str, db: AsyncSession) -> Optional[User]:
        """Get user by wallet address."""
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
        """Fetch profile from Abstract API."""
        try:
            url = f"https://backend.portal.abs.xyz/api/user/address/{wallet_address.lower()}"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                
                if response.status_code in [200, 304]:
                    data = response.json()
                    user_data = data.get('user', {})
                    
                    nickname = user_data.get('name')
                    avatar_url = user_data.get('overrideProfilePictureUrl')
                    
                    
                    return {
                        'nickname': nickname,
                        'avatar_url': avatar_url
                    }

                    
        except Exception as e:
            logger.error(f"Failed to fetch Abstract profile: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return {'nickname': None, 'avatar_url': None}

    async def create_or_get_user(
        self,
        wallet_address: str,
        db: AsyncSession,
        nickname: str = None,
        avatar_url: str = None,
        referral_code: str = None
    ) -> User:
        """Create or get user by wallet."""
        try:
            wallet_address = wallet_address.lower()

            # Find existing
            existing_query = select(User).where(User.wallet_address == wallet_address)
            existing_result = await db.execute(existing_query)
            existing_user = existing_result.scalar_one_or_none()
            
            if existing_user:
                logger.info(f"Existing user: {existing_user.nickname}")
                return existing_user
            
            # Fetch Abstract profile if not provided
            if not nickname or not avatar_url:
                abstract_profile = await self.fetch_abstract_profile(wallet_address)
                
                if abstract_profile:
                    if not nickname and abstract_profile.get('nickname'):
                        nickname = abstract_profile['nickname']
                    
                    if not avatar_url and abstract_profile.get('avatar_url'):
                        avatar_url = abstract_profile['avatar_url']

            # Default nickname
            if not nickname:
                nickname = f"Player{wallet_address[2:8].upper()}"
            
            # Ensure unique nickname
            counter = 1
            original_nickname = nickname
            while True:
                check_query = select(User).where(User.nickname == nickname)
                check_result = await db.execute(check_query)
                if check_result.scalar_one_or_none() is None:
                    break
                nickname = f"{original_nickname}{counter}"
                counter += 1
            
            # Referral route
            referral_route = f"{nickname}{secrets.randbelow(9999):04d}"
            while True:
                check_query = select(User).where(User.referral_route == referral_route)
                check_result = await db.execute(check_query)
                if check_result.scalar_one_or_none() is None:
                    break
                referral_route = f"{nickname}{secrets.randbelow(9999):04d}"
            
            # Default avatar
            if not avatar_url:
                avatar_url = None

            referrer_id = None
            if referral_code:
                referrer_query = select(User).where(User.referral_route == referral_code)
                referrer_result = await db.execute(referrer_query)
                referrer = referrer_result.scalar_one_or_none()
                
                if referrer:
                    referrer_id = referrer.id
                    referrer.referral_count += 1
                    logger.info(f"User registered via referral: {referral_code} (referrer: {referrer.nickname})")
                else:
                    logger.warning(f"Invalid referral code: {referral_code}")

            # Create user
            new_user = User(
                wallet_address=wallet_address,
                nickname=nickname,
                referral_route=referral_route,
                avatar_url=avatar_url,
                referred_by_id=referrer_id
            )
            
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            logger.info(f"Created user: {new_user.nickname}")
            
            return new_user
            
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            await db.rollback()
            raise

    def create_jwt_token(self, user: User) -> str:
        """Create JWT token for user."""
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
        """Verify JWT token."""
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
        """Remove expired nonces."""
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