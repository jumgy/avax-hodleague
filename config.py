import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration"""

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # API Server settings
    PORT = int(os.environ.get("PORT", 8000))
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000")

    @staticmethod
    def get_cors_origins():
        """Return list of origins with production checks."""
        origins_str = Config.CORS_ORIGINS.strip()

        # In production do not allow wildcard.
        if Config.ENVIRONMENT == "production":
            if origins_str == "*":
                raise ValueError("CORS_ORIGINS='*' is not allowed in production.")

            origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]

            # No localhost in production.
            localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
            if localhost_origins:
                raise ValueError(f"Localhost origins are not allowed in production: {localhost_origins}")

            return origins

        # Dev/uat: no restrictions.
        return [origin.strip() for origin in origins_str.split(",") if origin.strip()]

    # Flask settings
    SECRET_KEY = os.environ.get("SECRET_KEY") or "fantasy-crypto-game-secret-key-2025"
    DEBUG = os.environ.get("FLASK_DEBUG") == "True"

    # Force DEBUG off in production.
    if ENVIRONMENT == "production":
        if DEBUG:
            print("[Config] DEBUG forced off in production")
            DEBUG = False

        # SECRET_KEY must not be default in production.
        if "fantasy-crypto" in SECRET_KEY.lower() or SECRET_KEY == "fantasy-crypto-game-secret-key-2025":
            raise ValueError("Default SECRET_KEY is not allowed in production. Generate a new one.")

    JWT_SECRET = SECRET_KEY

    # Swagger Protection
    SWAGGER_USERNAME: str = os.getenv("SWAGGER_USERNAME", "admin")
    SWAGGER_PASSWORD: str = os.getenv("SWAGGER_PASSWORD", "admin")

    # In production Swagger credentials must not be default.
    if ENVIRONMENT == "production":
        if SWAGGER_USERNAME == "admin" or SWAGGER_PASSWORD == "admin":
            raise ValueError("Default Swagger credentials are not allowed in production.")

    # Database settings
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fantasy_crypto"
    )
    DB_ECHO = os.environ.get("DB_ECHO", "False").lower() == "true"

    # Force DB_ECHO off in production.
    if ENVIRONMENT == "production" and DB_ECHO:
        print("[Config] DB_ECHO forced off in production")
        DB_ECHO = False

    # DB params for scripts.
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres")
    POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "hodleague")
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "restapi")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "your-strong-password-here-2025")

    # In production require strong DB password.
    if ENVIRONMENT == "production":
        if "your-strong-password" in POSTGRES_PASSWORD.lower() or len(POSTGRES_PASSWORD) < 16:
            raise ValueError("Weak POSTGRES_PASSWORD in production. Minimum 16 characters.")

    # CoinMarketCap API settings
    COINMARKETCAP_API_KEY = os.environ.get("COINMARKETCAP_API_KEY") or "your-api-key-here"

    # In production API key must be set.
    if ENVIRONMENT == "production":
        if COINMARKETCAP_API_KEY == "your-api-key-here":
            raise ValueError("COINMARKETCAP_API_KEY must be set in production.")

    COINMARKETCAP_BASE_URL = "https://pro-api.coinmarketcap.com/v1"

    # ===== ADMIN PANEL SETTINGS =====
    ADMIN_JWT_SECRET_KEY: str = os.getenv("ADMIN_JWT_SECRET_KEY", "admin-default-secret-dev")
    ADMIN_JWT_EXPIRE_HOURS: int = int(os.getenv("ADMIN_JWT_EXPIRE_HOURS", "8"))
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")

    # In production validate admin credentials.
    if ENVIRONMENT == "production":
        if "default" in ADMIN_JWT_SECRET_KEY.lower() or len(ADMIN_JWT_SECRET_KEY) < 32:
            raise ValueError("ADMIN_JWT_SECRET_KEY too weak for production. Minimum 32 characters.")

        if ADMIN_USERNAME == "admin" or ADMIN_PASSWORD == "admin":
            raise ValueError("Default admin credentials are not allowed in production.")

        if len(ADMIN_PASSWORD) < 16:
            raise ValueError("ADMIN_PASSWORD too short for production. Minimum 16 characters.")

    # ===== WEB3 & BLOCKCHAIN SETTINGS =====
    WEB3_PROVIDER_URL = os.environ.get("WEB3_PROVIDER_URL", "https://api.mainnet.abs.xyz")
    TOURNAMENT_CONTRACT_ADDRESS = os.environ.get(
        "TOURNAMENT_CONTRACT_ADDRESS", "0x507Db3dfd3695270D7F2b08a25906e171C07B4C4"
    )
    # Abstract chain ID (for frontend / audit)
    ABSTRACT_CHAIN_ID = 2741

    # Avalanche C-Chain (optional; if not set, only Abstract is used)
    WEB3_PROVIDER_URL_AVALANCHE = os.environ.get("WEB3_PROVIDER_URL_AVALANCHE", "")
    TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE = os.environ.get("TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "")
    AVALANCHE_CHAIN_ID = 43114

    # Min native balance (wei) to consider "enough gas" for registerDeck
    MIN_GAS_BALANCE_ABSTRACT = int(os.environ.get("MIN_GAS_BALANCE_ABSTRACT", "100000000000000"))  # 0.0001 ETH equiv
    MIN_GAS_BALANCE_AVALANCHE = int(os.environ.get("MIN_GAS_BALANCE_AVALANCHE", "100000000000000"))  # 0.0001 AVAX

    # Contract ABI.
    TOURNAMENT_CONTRACT_ABI = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "uint256", "name": "tournamentId", "type": "uint256"},
                {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
                {"indexed": False, "internalType": "bytes32", "name": "deckHash", "type": "bytes32"},
            ],
            "name": "Registered",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "uint256", "name": "tournamentId", "type": "uint256"},
                {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            ],
            "name": "Unregistered",
            "type": "event",
        },
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
        {
            "inputs": [
                {"internalType": "uint256", "name": "", "type": "uint256"},
                {"internalType": "address", "name": "", "type": "address"},
            ],
            "name": "registrations",
            "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "uint256", "name": "tournamentId", "type": "uint256"}],
            "name": "unregisterDeck",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]

    # Game settings
    GAME_DURATION_DAYS = 7
    DECK_SIZE = 5

    # Cache settings (seconds)
    TOKEN_DATA_CACHE_TTL = 300  # 5 minutes

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    if ENVIRONMENT == "production" and LOG_LEVEL in ["DEBUG", "INFO"]:
        print(f"[Config] LOG_LEVEL changed from {LOG_LEVEL} to WARNING in production")
        LOG_LEVEL = "WARNING"

    STATIC_BASE_URL = os.environ.get("STATIC_BASE_URL", "http://localhost:8080")


# Log current config on startup (ASCII only for Windows cp1251 / pytest).
print(f"[Config] ENVIRONMENT={Config.ENVIRONMENT}, DEBUG={Config.DEBUG}, LOG_LEVEL={Config.LOG_LEVEL}")
