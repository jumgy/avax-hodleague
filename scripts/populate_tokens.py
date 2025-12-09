import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text
from datetime import datetime

# Импортируем только сервис CoinMarketCap и конфиг
from services.coinmarketcap_service import CoinMarketCapService
from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Game tokens with their weights
GAME_TOKENS_WEIGHTS = {
    # Вес 10
    'BTC': 10, 'ETH': 10, 'XRP': 10,
    
    # Вес 9
    'BNB': 9, 'SOL': 9, 'TRX': 9,
    
    # Вес 8
    'DOGE': 8, 'ADA': 8, 'AVAX': 8,
    
    # Вес 7
    'HYPE': 7, 'WLFI': 7, 'ZEC': 7,
    
    # Вес 6
    'ENA': 6, 'APT': 6, 'M': 6,
    
    # Вес 5
    'PUMP': 5, 'KCS': 5, 'POL': 5,
    
    # Вес 4
    'KAS': 4, 'FLR': 4, 'DASH': 4,
    
    # Вес 3
    'FET': 3, 'LDO': 3, 'XTZ': 3,
    
    # Вес 2
    'DCR': 2, 'IOTA': 2, 'AB': 2,
    
    # Вес 1
    'KAIA': 1, 'FLOKI': 1, 'SPX': 1,
}

def create_database_connection():
    """Create database connection"""
    try:
        # Используем DATABASE_URL напрямую, но заменяем asyncpg на psycopg2 для синхронного подключения
        db_url = Config.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        return engine, SessionLocal()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def clear_tokens_table(session):
    """Clear all records from tokens table with cascade"""
    try:
        logger.info("Clearing tokens table with cascade...")
        
        # Delete token_prices first (safe approach)
        logger.info("Deleting token_prices...")
        prices_result = session.execute(text("DELETE FROM token_prices"))
        prices_deleted = prices_result.rowcount
        logger.info(f"Deleted {prices_deleted} token_prices records")
        
        # Then delete tokens
        logger.info("Deleting tokens...")
        tokens_result = session.execute(text("DELETE FROM tokens"))
        tokens_deleted = tokens_result.rowcount
        logger.info(f"Deleted {tokens_deleted} tokens records")
        
        session.commit()
        logger.info(f"Successfully cleared tokens and related data")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clear tokens table: {e}")
        session.rollback()
        return False

def get_tokens_data_from_cmc(cmc_service):
    """Get token data from CoinMarketCap API"""
    try:
        logger.info("Fetching token data from CoinMarketCap...")
        
        # Get specific tokens by symbols
        symbols_list = list(GAME_TOKENS_WEIGHTS.keys())
        logger.info(f"Fetching data for {len(symbols_list)} tokens: {symbols_list}")
        
        tokens_data = cmc_service.get_specific_cryptocurrencies(symbols_list)
        
        if not tokens_data:
            logger.error("Failed to get tokens data from CoinMarketCap")
            return {}
            
        logger.info(f"Successfully fetched data for {len(tokens_data)} tokens")
        return tokens_data
        
    except Exception as e:
        logger.error(f"Error fetching tokens data: {e}")
        return {}

def insert_token_with_sql(session, symbol, name, weight, image_url):
    """Insert token using raw SQL to avoid model import issues"""
    try:
        sql = text("""
            INSERT INTO tokens (name, symbol, weight, image_url, is_active, created_at, updated_at)
            VALUES (:name, :symbol, :weight, :image_url, :is_active, :created_at, :updated_at)
        """)
        
        session.execute(sql, {
            'name': name,
            'symbol': symbol,
            'weight': weight,
            'image_url': image_url,
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        })
        
        return True
        
    except Exception as e:
        logger.error(f"Error inserting token {symbol}: {e}")
        return False

def populate_tokens(session, cmc_service):
    """Populate tokens table with game tokens"""
    try:
        # Get tokens data from CMC
        cmc_tokens_data = get_tokens_data_from_cmc(cmc_service)
        
        successful_tokens = []
        failed_tokens = []
        
        logger.info("Creating token records...")
        
        for symbol, weight in GAME_TOKENS_WEIGHTS.items():
            try:
                cmc_data = cmc_tokens_data.get(symbol)
                
                if cmc_data:
                    # Use real data from CoinMarketCap
                    name = cmc_data['name']
                    image_url = f"https://s2.coinmarketcap.com/static/img/coins/200x200/{cmc_data['id']}.png"
                    logger.info(f"Creating token {symbol} ({name}) with real CMC data")
                else:
                    # Use placeholder data
                    name = f"{symbol} Token"
                    image_url = f"https://s2.coinmarketcap.com/static/img/coins/200x200/1.png"
                    logger.warning(f"Creating token {symbol} with placeholder data")
                
                # Insert using raw SQL
                success = insert_token_with_sql(session, symbol, name, weight, image_url)
                
                if success:
                    successful_tokens.append(symbol)
                else:
                    failed_tokens.append(symbol)
                    
            except Exception as e:
                logger.error(f"Failed to create token {symbol}: {e}")
                failed_tokens.append(symbol)
        
        # Commit all inserts
        session.commit()
        logger.info(f"Successfully inserted {len(successful_tokens)} tokens")
        
        # Report results
        logger.info(f"=== RESULTS ===")
        logger.info(f"Total tokens to process: {len(GAME_TOKENS_WEIGHTS)}")
        logger.info(f"Successfully created: {len(successful_tokens)}")
        logger.info(f"Failed to create: {len(failed_tokens)}")
        
        if successful_tokens:
            logger.info(f"Successful tokens: {', '.join(successful_tokens)}")
        
        if failed_tokens:
            logger.warning(f"Failed tokens: {', '.join(failed_tokens)}")
            
        return len(successful_tokens), len(failed_tokens)
        
    except Exception as e:
        logger.error(f"Error populating tokens: {e}")
        session.rollback()
        return 0, len(GAME_TOKENS_WEIGHTS)

def verify_tokens_table(session):
    """Verify tokens were inserted correctly"""
    try:
        logger.info("Verifying tokens table...")
        
        # Count total tokens
        total_result = session.execute(text("SELECT COUNT(*) FROM tokens"))
        total_count = total_result.scalar()
        
        active_result = session.execute(text("SELECT COUNT(*) FROM tokens WHERE is_active = true"))
        active_count = active_result.scalar()
        
        logger.info(f"Total tokens in database: {total_count}")
        logger.info(f"Active tokens: {active_count}")
        
        # Show weight distribution
        weight_result = session.execute(text("SELECT weight, array_agg(symbol) as symbols FROM tokens GROUP BY weight ORDER BY weight DESC"))
        
        logger.info("Weight distribution:")
        for row in weight_result:
            weight = row[0]
            symbols = row[1]
            logger.info(f"  Weight {weight}: {', '.join(symbols)} ({len(symbols)} tokens)")
            
        return True
        
    except Exception as e:
        logger.error(f"Error verifying tokens table: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("=== Starting tokens population script ===")
    
    session = None
    try:
        # Initialize services
        logger.info("Initializing CoinMarketCap service...")
        cmc_service = CoinMarketCapService()
        
        # Create database connection
        logger.info("Connecting to database...")
        engine, session = create_database_connection()
        
        # Clear existing tokens
        if not clear_tokens_table(session):
            logger.error("Failed to clear tokens table. Aborting.")
            return False
        
        # Populate tokens
        success_count, fail_count = populate_tokens(session, cmc_service)
        
        if success_count == 0:
            logger.error("No tokens were successfully created. Aborting.")
            return False
        
        # Verify results
        verify_tokens_table(session)
        
        logger.info("=== Tokens population completed successfully! ===")
        return True
        
    except Exception as e:
        logger.error(f"Script execution failed: {e}")
        return False
        
    finally:
        if session:
            session.close()

if __name__ == "__main__":
    success = main()
    if success:
        logger.info("Script completed successfully")
        sys.exit(0)
    else:
        logger.error("Script failed")
        sys.exit(1)