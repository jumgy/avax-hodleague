import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text
from datetime import datetime

from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_database_connection():
    """Create database connection"""
    try:
        db_url = Config.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        return engine, SessionLocal()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def clear_cards_table(session):
    """Clear all records from cards table"""
    try:
        logger.info("Clearing cards table...")
        result = session.execute(text("DELETE FROM cards"))
        deleted_count = result.rowcount
        session.commit()
        logger.info(f"Deleted {deleted_count} existing card records")
        return True
    except Exception as e:
        logger.error(f"Failed to clear cards table: {e}")
        session.rollback()
        return False

def get_tokens_and_rarity(session):
    """Get all tokens and common rarity ID"""
    try:
        # Get all active tokens
        tokens_result = session.execute(text("SELECT id, symbol, name FROM tokens WHERE is_active = true ORDER BY id"))
        tokens = [(row[0], row[1], row[2]) for row in tokens_result]
        logger.info(f"Found {len(tokens)} active tokens")
        
        # Get common rarity ID
        rarity_result = session.execute(text("SELECT id FROM rarities WHERE name = 'common' AND is_active = true"))
        rarity_row = rarity_result.fetchone()
        
        if not rarity_row:
            logger.error("Common rarity not found!")
            return [], None
            
        common_rarity_id = rarity_row[0]
        logger.info(f"Found common rarity with ID: {common_rarity_id}")
        
        return tokens, common_rarity_id
        
    except Exception as e:
        logger.error(f"Error getting tokens and rarity: {e}")
        return [], None

def generate_background_placeholder(token_symbol):
    """Generate placeholder background URL for token card"""
    # Different placeholder styles based on token
    colors = {
        'BTC': 'f7931a/ffffff',  # Bitcoin orange
        'ETH': '627eea/ffffff',  # Ethereum blue
        'XRP': '23292f/ffffff',  # XRP dark
        'BNB': 'f3ba2f/000000',  # Binance yellow
        'SOL': '14f195/000000',  # Solana green
        'DOGE': 'c2a633/ffffff', # Doge gold
        'ADA': '0033ad/ffffff',  # Cardano blue
    }
    
    # Use token-specific colors or default
    color_scheme = colors.get(token_symbol, '6366f1/ffffff')  # Default indigo
    
    # Create placeholder with token symbol
    placeholder_url = f"https://via.placeholder.com/400x600/{color_scheme}?text={token_symbol}+CARD"
    
    return placeholder_url

def insert_card_with_sql(session, token_id, token_symbol, rarity_id):
    """Insert card using raw SQL"""
    try:
        background_url = generate_background_placeholder(token_symbol)
        design_type = "classic"
        
        sql = text("""
            INSERT INTO cards (token_id, rarity_id, design_type, background_image_url, is_active, created_at, updated_at)
            VALUES (:token_id, :rarity_id, :design_type, :background_image_url, :is_active, :created_at, :updated_at)
        """)
        
        session.execute(sql, {
            'token_id': token_id,
            'rarity_id': rarity_id,
            'design_type': design_type,
            'background_image_url': background_url,
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        })
        
        return True
        
    except Exception as e:
        logger.error(f"Error inserting card for token {token_symbol}: {e}")
        return False

def populate_cards(session):
    """Populate cards table based on tokens"""
    try:
        # Get tokens and rarity
        tokens, common_rarity_id = get_tokens_and_rarity(session)
        
        if not tokens or common_rarity_id is None:
            logger.error("Cannot proceed without tokens or rarity data")
            return 0, 0
        
        successful_cards = []
        failed_cards = []
        
        logger.info(f"Creating cards for {len(tokens)} tokens with common rarity (ID: {common_rarity_id})")
        
        for token_id, token_symbol, token_name in tokens:
            try:
                logger.info(f"Creating card for token: {token_symbol} ({token_name})")
                
                success = insert_card_with_sql(session, token_id, token_symbol, common_rarity_id)
                
                if success:
                    successful_cards.append(token_symbol)
                    logger.info(f"✅ Successfully created card for {token_symbol}")
                else:
                    failed_cards.append(token_symbol)
                    logger.error(f"❌ Failed to create card for {token_symbol}")
                    
            except Exception as e:
                logger.error(f"Failed to create card for {token_symbol}: {e}")
                failed_cards.append(token_symbol)
        
        # Commit all inserts
        session.commit()
        logger.info(f"Successfully inserted {len(successful_cards)} cards")
        
        # Report results
        logger.info(f"=== RESULTS ===")
        logger.info(f"Total cards to process: {len(tokens)}")
        logger.info(f"Successfully created: {len(successful_cards)}")
        logger.info(f"Failed to create: {len(failed_cards)}")
        
        if successful_cards:
            logger.info(f"Successful cards: {', '.join(successful_cards)}")
        
        if failed_cards:
            logger.warning(f"Failed cards: {', '.join(failed_cards)}")
            
        return len(successful_cards), len(failed_cards)
        
    except Exception as e:
        logger.error(f"Error populating cards: {e}")
        session.rollback()
        return 0, 0

def verify_cards_table(session):
    """Verify cards were inserted correctly"""
    try:
        logger.info("Verifying cards table...")
        
        # Count total cards
        total_result = session.execute(text("SELECT COUNT(*) FROM cards"))
        total_count = total_result.scalar()
        
        active_result = session.execute(text("SELECT COUNT(*) FROM cards WHERE is_active = true"))
        active_count = active_result.scalar()
        
        logger.info(f"Total cards in database: {total_count}")
        logger.info(f"Active cards: {active_count}")
        
        # Show sample cards with token and rarity info
        sample_result = session.execute(text("""
            SELECT c.id, t.symbol, t.name, r.name as rarity_name, c.design_type, 
                   c.background_image_url
            FROM cards c
            JOIN tokens t ON c.token_id = t.id
            JOIN rarities r ON c.rarity_id = r.id
            ORDER BY t.weight DESC, t.symbol
            LIMIT 10
        """))
        
        logger.info("Sample of created cards:")
        for row in sample_result:
            card_id, symbol, name, rarity, design, bg_url = row
            bg_info = "Placeholder" if "placeholder" in bg_url else "Custom"
            logger.info(f"  Card #{card_id}: {symbol} ({name}) - {rarity} {design} ({bg_info})")
        
        # Show cards by token weight
        weight_result = session.execute(text("""
            SELECT t.weight, count(c.id) as card_count, 
                   string_agg(t.symbol, ', ' ORDER BY t.symbol) as tokens
            FROM cards c
            JOIN tokens t ON c.token_id = t.id
            WHERE c.is_active = true
            GROUP BY t.weight
            ORDER BY t.weight DESC
        """))
        
        logger.info("Cards by token weight:")
        for row in weight_result:
            weight, count, tokens = row
            logger.info(f"  Weight {weight}: {count} cards ({tokens})")
            
        return True
        
    except Exception as e:
        logger.error(f"Error verifying cards table: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("=== Starting cards population script ===")
    
    session = None
    try:
        # Create database connection
        logger.info("Connecting to database...")
        engine, session = create_database_connection()
        
        # Clear existing cards
        if not clear_cards_table(session):
            logger.error("Failed to clear cards table. Aborting.")
            return False
        
        # Populate cards
        success_count, fail_count = populate_cards(session)
        
        if success_count == 0:
            logger.error("No cards were successfully created. Aborting.")
            return False
        
        # Verify results
        verify_cards_table(session)
        
        logger.info("=== Cards population completed successfully! ===")
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