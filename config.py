import os
from datetime import timedelta

class Config:
    """Application configuration"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'fantasy-crypto-game-secret-key-2025'
    DEBUG = os.environ.get('FLASK_DEBUG') == 'True'
    
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