import asyncio
from web3.exceptions import TransactionNotFound
from web3 import Web3
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class Web3VerificationService:
    """
    Сервис для проверки блокчейн-транзакций регистрации в турнире
    """
    
    def __init__(self, web3_provider_url: str, contract_address: str, contract_abi: list):
        """
        :param web3_provider_url: RPC URL (из Config.WEB3_PROVIDER_URL)
        :param contract_address: Адрес контракта (из Config.TOURNAMENT_CONTRACT_ADDRESS)
        :param contract_abi: ABI контракта (из Config.TOURNAMENT_CONTRACT_ABI)
        """
        try:
            self.web3 = Web3(Web3.HTTPProvider(web3_provider_url))
            self.contract_address = Web3.to_checksum_address(contract_address)
            self.contract = self.web3.eth.contract(
                address=self.contract_address,
                abi=contract_abi
            )
            
            if not self.web3.is_connected():
                raise Exception(f"Failed to connect to Web3 provider: {web3_provider_url}")
            
            logger.info(f"Web3VerificationService initialized. Connected to {web3_provider_url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Web3VerificationService: {str(e)}")
            raise
    
    async def verify_register_transaction(
        self,
        tx_hash: str,
        tournament_id: int,
        expected_deck_hash: str,
        user_wallet: str
    ) -> Dict:
        """
        Проверяет транзакцию регистрации (registerDeck)
        
        :param tx_hash: Хеш транзакции (0x...)
        :param tournament_id: ID турнира
        :param expected_deck_hash: Ожидаемый хеш деки (SHA256 hex)
        :param user_wallet: Адрес кошелька пользователя
        :return: {"valid": bool, "error": str (если invalid), "block_number": int, "gas_used": int}
        """
        await asyncio.sleep(2)  # Первая задержка
        
        tx_receipt = None
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                tx_receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                if tx_receipt and tx_receipt.blockNumber is not None:
                    break
            except TransactionNotFound:
                pass
            except Exception as e:
                logger.error(f"Error fetching transaction receipt {tx_hash}: {str(e)}")
            
            if attempt < max_attempts - 1:
                logger.info(f"Transaction {tx_hash} not found, retry {attempt+1}/{max_attempts}")
                await asyncio.sleep(2)
        
        # Если после всех попыток не нашли
        if not tx_receipt:
            return {
                "valid": False,
                "error": "Transaction not found or not yet mined. Please wait a few seconds and try again."
            }
        
        # Проверка статуса (1 = success, 0 = failed)
        if tx_receipt.status != 1:
            return {
                "valid": False,
                "error": "Transaction failed on blockchain"
            }
        
        # Получаем саму транзакцию
        try:
            tx = self.web3.eth.get_transaction(tx_hash)
        except Exception as e:
            logger.error(f"Error fetching transaction {tx_hash}: {str(e)}")
            return {
                "valid": False,
                "error": f"Error fetching transaction: {str(e)}"
            }
        
        # Проверка отправителя (from)
        tx_from = tx['from'].lower()
        expected_wallet = user_wallet.lower()
        if tx_from != expected_wallet:
            return {
                "valid": False,
                "error": f"Transaction from wrong wallet. Expected: {expected_wallet}, got: {tx_from}"
            }
        
        # Проверка получателя (to) - должен быть наш контракт
        tx_to = tx['to'].lower() if tx['to'] else None
        expected_contract = self.contract_address.lower()
        if tx_to != expected_contract:
            return {
                "valid": False,
                "error": f"Transaction sent to wrong contract. Expected: {expected_contract}, got: {tx_to}"
            }
        
        # Декодирование input data
        try:
            function_obj, params = self.contract.decode_function_input(tx['input'])
            
            # Проверка имени функции
            if function_obj.fn_name != 'registerDeck':
                return {
                    "valid": False,
                    "error": f"Wrong function called: {function_obj.fn_name}. Expected: registerDeck"
                }
            
            # Проверка tournamentId
            if params['tournamentId'] != tournament_id:
                return {
                    "valid": False,
                    "error": f"Wrong tournament ID. Expected: {tournament_id}, got: {params['tournamentId']}"
                }
            
            # Проверка deckHash
            actual_hash = params['deckHash'].hex() if isinstance(params['deckHash'], bytes) else params['deckHash']
            expected_hash_clean = expected_deck_hash.replace('0x', '').lower()
            actual_hash_clean = actual_hash.replace('0x', '').lower()
            
            if actual_hash_clean != expected_hash_clean:
                return {
                    "valid": False,
                    "error": "Deck hash mismatch",
                    "expected": expected_hash_clean,
                    "got": actual_hash_clean
                }
                
        except Exception as e:
            logger.error(f"Error decoding transaction input: {str(e)}")
            return {
                "valid": False,
                "error": f"Error decoding transaction: {str(e)}"
            }
        
        # ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ
        logger.info(f"✅ Transaction {tx_hash} verified successfully for tournament {tournament_id}")
        return {
            "valid": True,
            "tx_hash": tx_hash,
            "block_number": tx_receipt.blockNumber,
            "gas_used": tx_receipt.gasUsed
        }
    async def verify_unregister_transaction(
        self,
        tx_hash: str,
        tournament_id: int,
        user_wallet: str
    ) -> Dict:
        """
        Проверяет транзакцию отмены регистрации (unregisterDeck)
        :param tx_hash: Хеш транзакции
        :param tournament_id: ID турнира
        :param user_wallet: Адрес кошелька пользователя
        :return: {"valid": bool, "error": str (если invalid)}
        """
        # ЖДЕМ 2 СЕКУНДЫ + делаем 3 попытки (так же как в register)
        await asyncio.sleep(2)
        
        tx_receipt = None
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                tx_receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                if tx_receipt and tx_receipt.blockNumber is not None:
                    break
            except TransactionNotFound:
                pass
            except Exception as e:
                logger.error(f"Error fetching unregister transaction receipt {tx_hash}: {str(e)}")
            
            if attempt < max_attempts - 1:
                logger.info(f"Unregister transaction {tx_hash} not found, retry {attempt+1}/{max_attempts}")
                await asyncio.sleep(2)
        
        # Если после всех попыток не нашли
        if not tx_receipt:
            return {
                "valid": False,
                "error": "Transaction not found or not yet mined. Please wait a few seconds and try again."
            }
        
        # Проверка статуса
        if tx_receipt.status != 1:
            return {
                "valid": False,
                "error": "Transaction failed on blockchain"
            }
        
        # Получаем саму транзакцию
        try:
            tx = self.web3.eth.get_transaction(tx_hash)
        except Exception as e:
            logger.error(f"Error fetching unregister transaction {tx_hash}: {str(e)}")
            return {
                "valid": False,
                "error": f"Error fetching transaction: {str(e)}"
            }
        
        # Проверка отправителя
        if tx['from'].lower() != user_wallet.lower():
            return {
                "valid": False,
                "error": "Transaction from wrong wallet"
            }
        
        # Проверка контракта
        if tx['to'].lower() != self.contract_address.lower():
            return {
                "valid": False,
                "error": "Transaction sent to wrong contract"
            }
        
        # Декодирование
        try:
            function_obj, params = self.contract.decode_function_input(tx['input'])
            
            if function_obj.fn_name != 'unregisterDeck':
                return {
                    "valid": False,
                    "error": f"Wrong function: {function_obj.fn_name}"
                }
            
            if params['tournamentId'] != tournament_id:
                return {
                    "valid": False,
                    "error": "Wrong tournament ID"
                }
                
        except Exception as e:
            logger.error(f"Error verifying unregister tx: {str(e)}")
            return {
                "valid": False,
                "error": str(e)
            }
        
        logger.info(f"✅ Unregister transaction {tx_hash} verified successfully")
        return {
            "valid": True,
            "tx_hash": tx_hash
        }
    
    def check_registration_onchain(self, tournament_id: int, user_wallet: str) -> Dict:
        """
        Проверяет статус регистрации напрямую из контракта (read-only)
        
        :param tournament_id: ID турнира
        :param user_wallet: Адрес кошелька
        :return: {"is_registered": bool, "deck_hash": str}
        """
        try:
            user_address = Web3.to_checksum_address(user_wallet)
            deck_hash = self.contract.functions.registrations(tournament_id, user_address).call()
            
            # bytes32(0) означает что не зарегистрирован
            is_registered = deck_hash != b'\x00' * 32
            
            return {
                "is_registered": is_registered,
                "deck_hash": deck_hash.hex() if is_registered else None
            }
            
        except Exception as e:
            logger.error(f"Error checking registration onchain: {str(e)}")
            return {
                "is_registered": False,
                "error": str(e)
            }