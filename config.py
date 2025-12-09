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
    
    # Game settings
    GAME_DURATION_DAYS = 7
    DECK_SIZE = 5
    
    # Cache settings (seconds)
    TOKEN_DATA_CACHE_TTL = 300  # 5 minutes
    
    # Logging
    LOG_LEVEL = 'INFO'