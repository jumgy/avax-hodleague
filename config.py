import os
import sys
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # ✅ API Server settings
    PORT = int(os.environ.get('PORT', 8000))
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000')
    
    @staticmethod
    def get_cors_origins():
        """Возвращает список origins с проверкой для production"""
        origins_str = Config.CORS_ORIGINS.strip()
        
        # В production НЕ разрешаем wildcard
        if Config.ENVIRONMENT == "production":
            if origins_str == "*":
                raise ValueError("❌ CORS_ORIGINS='*' запрещен в production!")
            
            # Парсим origins
            origins = [origin.strip() for origin in origins_str.split(',') if origin.strip()]
            
            # Проверяем что нет localhost в production
            localhost_origins = [o for o in origins if 'localhost' in o or '127.0.0.1' in o]
            if localhost_origins:
                raise ValueError(f"❌ Localhost origins запрещены в production: {localhost_origins}")
            
            return origins
        
        # Для dev/uat - без ограничений
        return [origin.strip() for origin in origins_str.split(',') if origin.strip()]
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'fantasy-crypto-game-secret-key-2025'
    DEBUG = os.environ.get('FLASK_DEBUG') == 'True'
    
    # В production принудительно отключаем DEBUG
    if ENVIRONMENT == "production":
        if DEBUG:
            print("⚠️  DEBUG принудительно отключен в production")
            DEBUG = False
        
        # Проверяем что SECRET_KEY не дефолтный
        if 'fantasy-crypto' in SECRET_KEY.lower() or SECRET_KEY == 'fantasy-crypto-game-secret-key-2025':
            raise ValueError("❌ Дефолтный SECRET_KEY запрещен в production! Сгенерируйте новый.")
    
    JWT_SECRET = SECRET_KEY
    
    # Swagger Protection
    SWAGGER_USERNAME: str = os.getenv("SWAGGER_USERNAME", "admin")
    SWAGGER_PASSWORD: str = os.getenv("SWAGGER_PASSWORD", "admin")
    
    # В production проверяем что креды НЕ дефолтные
    if ENVIRONMENT == "production":
        if SWAGGER_USERNAME == "admin" or SWAGGER_PASSWORD == "admin":
            raise ValueError("❌ Дефолтные Swagger креды запрещены в production!")
    
    # Database settings
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/fantasy_crypto')
    DB_ECHO = os.environ.get('DB_ECHO', 'False').lower() == 'true'
    
    # В production принудительно отключаем DB_ECHO
    if ENVIRONMENT == "production" and DB_ECHO:
        print("⚠️  DB_ECHO принудительно отключен в production")
        DB_ECHO = False
    
    # Отдельные параметры БД для скриптов
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'postgres')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'hodleague')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'restapi')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'your-strong-password-here-2025')
    
    # В production проверяем пароль БД
    if ENVIRONMENT == "production":
        if 'your-strong-password' in POSTGRES_PASSWORD.lower() or len(POSTGRES_PASSWORD) < 16:
            raise ValueError("❌ Слабый POSTGRES_PASSWORD в production! Минимум 16 символов.")
    
    # CoinMarketCap API settings
    COINMARKETCAP_API_KEY = os.environ.get('COINMARKETCAP_API_KEY') or 'your-api-key-here'
    
    # В production проверяем что API ключ установлен
    if ENVIRONMENT == "production":
        if COINMARKETCAP_API_KEY == 'your-api-key-here':
            raise ValueError("❌ COINMARKETCAP_API_KEY не установлен в production!")
    
    COINMARKETCAP_BASE_URL = 'https://pro-api.coinmarketcap.com/v1'

    # ===== ADMIN PANEL SETTINGS =====
    ADMIN_JWT_SECRET_KEY: str = os.getenv("ADMIN_JWT_SECRET_KEY", "admin-default-secret-dev")
    ADMIN_JWT_EXPIRE_HOURS: int = int(os.getenv("ADMIN_JWT_EXPIRE_HOURS", "8"))
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
    
    # В production проверяем админские креды
    if ENVIRONMENT == "production":
        # Проверка admin JWT secret
        if "default" in ADMIN_JWT_SECRET_KEY.lower() or len(ADMIN_JWT_SECRET_KEY) < 32:
            raise ValueError("❌ ADMIN_JWT_SECRET_KEY слишком слабый для production! Минимум 32 символа.")
        
        # Проверка дефолтных креденшалов
        if ADMIN_USERNAME == "admin" or ADMIN_PASSWORD == "admin":
            raise ValueError("❌ Дефолтные админские креденшалы запрещены в production!")
        
        # Проверка сложности пароля
        if len(ADMIN_PASSWORD) < 16:
            raise ValueError("❌ ADMIN_PASSWORD слишком короткий для production! Минимум 16 символов.")
    
    # ===== WEB3 & BLOCKCHAIN SETTINGS =====
    WEB3_PROVIDER_URL = os.environ.get('WEB3_PROVIDER_URL', 'https://api.mainnet.abs.xyz')
    TOURNAMENT_CONTRACT_ADDRESS = os.environ.get('TOURNAMENT_CONTRACT_ADDRESS', '0x507Db3dfd3695270D7F2b08a25906e171C07B4C4')
    
    # Contract ABI (оставляем как есть)
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
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    if ENVIRONMENT == "production" and LOG_LEVEL in ['DEBUG', 'INFO']:
        print(f"⚠️  LOG_LEVEL изменен с {LOG_LEVEL} на WARNING в production")
        LOG_LEVEL = 'WARNING'
    
    STATIC_BASE_URL = os.environ.get('STATIC_BASE_URL', 'http://localhost:8080')

# Выводим текущую конфигурацию при старте
print(f"🔧 Config loaded: ENVIRONMENT={Config.ENVIRONMENT}, DEBUG={Config.DEBUG}, LOG_LEVEL={Config.LOG_LEVEL}")