import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'fantasy-crypto-game-secret-key-2025'
    DEBUG = os.environ.get('FLASK_DEBUG') == 'True'
    JWT_SECRET = SECRET_KEY

    # Database settings (NEW)
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/fantasy_crypto')
    DB_ECHO = os.environ.get('DB_ECHO', 'False').lower() == 'true'

    # Добавляем отдельные параметры БД для скриптов
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'postgres')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'hodleague')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'restapi')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'your-strong-password-here-2025')

    # CoinMarketCap API settings
    COINMARKETCAP_API_KEY = os.environ.get('COINMARKETCAP_API_KEY') or 'your-api-key-here'
    COINMARKETCAP_BASE_URL = 'https://pro-api.coinmarketcap.com/v1'

    # ===== WEB3 & BLOCKCHAIN SETTINGS =====
    WEB3_PROVIDER_URL = os.environ.get('WEB3_PROVIDER_URL', 'https://api.mainnet.abs.xyz')
    TOURNAMENT_CONTRACT_ADDRESS = os.environ.get('TOURNAMENT_CONTRACT_ADDRESS', '0x507Db3dfd3695270D7F2b08a25906e171C07B4C4')
    
    # Contract ABI
    TOURNAMENT_CONTRACT_ABI = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "uint256", "name": "tournamentId", "type": "uint256"},
                {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
                {"indexed": False, "internalType": "bytes32", "name": "deckHash", "type": "bytes32"}
            ],
            "name": "Registered",
            "type": "event"
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "uint256", "name": "tournamentId", "type": "uint256"},
                {"indexed": True, "internalType": "address", "name": "user", "type": "address"}
            ],
            "name": "Unregistered",
            "type": "event"
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "tournamentId", "type": "uint256"},
                {"internalType": "bytes32", "name": "deckHash", "type": "bytes32"}
            ],
            "name": "registerDeck",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "", "type": "uint256"},
                {"internalType": "address", "name": "", "type": "address"}
            ],
            "name": "registrations",
            "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "uint256", "name": "tournamentId", "type": "uint256"}],
            "name": "unregisterDeck",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]

    # Game settings
    GAME_DURATION_DAYS = 7
    DECK_SIZE = 5

    # Cache settings (seconds)
    TOKEN_DATA_CACHE_TTL = 300  # 5 minutes

    # Logging
    LOG_LEVEL = 'INFO'