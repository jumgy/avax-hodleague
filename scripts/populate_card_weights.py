# scripts/populate_card_weights.py

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

def clear_card_weights_table(session):
    """Clear all records from card_weights table"""
    try:
        logger.info("Clearing card_weights table...")
        result = session.execute(text("DELETE FROM card_weights"))
        deleted_count = result.rowcount
        session.commit()
        logger.info(f"Deleted {deleted_count} existing card weight records")
        return True
    except Exception as e:
        logger.error(f"Failed to clear card_weights table: {e}")
        session.rollback()
        return False

def get_tier_from_token_weight(weight: int) -> tuple:
    """
    Determine tier and base_weight from token weight
    
    Distribution for 35 cards (5 packs x 7 cards pool):
    - weight >= 8: TOP (9 cards) - base_weight 3.0
    - weight >= 5: MID (13 cards) - base_weight 2.0
    - weight < 5: LOW (13 cards) - base_weight 1.0
    
    Returns:
        tuple: (tier_name, base_weight)
    """
    if weight >= 8:
        return ("top", 3.0)
    elif weight >= 5:
        return ("mid", 2.0)
    else:
        return ("low", 1.0)

def populate_card_weights(session):
    """
    Populate card_weights table based on token weights
    
    Joins cards -> tokens to get weight, then creates card_weight entries
    """
    try:
        logger.info("Fetching cards with token information...")
        
        # Get all active cards with their token weights
        query = text("""
            SELECT 
                c.id as card_id,
                c.token_id,
                t.symbol as token_symbol,
                t.weight as token_weight
            FROM cards c
            JOIN tokens t ON c.token_id = t.id
            WHERE c.is_active = true AND t.is_active = true
            ORDER BY t.weight DESC, t.symbol
        """)
        
        result = session.execute(query)
        cards_data = result.fetchall()
        
        if not cards_data:
            logger.warning("No active cards found")
            return 0, 0
        
        logger.info(f"Found {len(cards_data)} active cards to process")
        
        successful_count = 0
        failed_count = 0
        
        # Statistics for reporting
        tier_stats = {"top": [], "mid": [], "low": []}
        
        logger.info("Creating card_weight records...")
        logger.info("=" * 80)
        
        for card in cards_data:
            card_id = card.card_id
            token_symbol = card.token_symbol
            token_weight = card.token_weight
            
            # Determine tier and base_weight
            tier_name, base_weight = get_tier_from_token_weight(token_weight)
            
            try:
                # Insert card_weight
                insert_sql = text("""
                    INSERT INTO card_weights 
                    (card_id, base_weight, current_multiplier, last_updated)
                    VALUES (:card_id, :base_weight, :multiplier, :last_updated)
                """)
                
                session.execute(insert_sql, {
                    'card_id': card_id,
                    'base_weight': base_weight,
                    'multiplier': 1.0,
                    'last_updated': datetime.utcnow()
                })
                
                successful_count += 1
                tier_stats[tier_name].append(token_symbol)
                
                logger.info(
                    f"✅ {token_symbol:8s} | weight={token_weight:2d} | "
                    f"tier={tier_name.upper():4s} | base_weight={base_weight}"
                )
                
            except Exception as e:
                logger.error(f"❌ Failed to create weight for card {card_id} ({token_symbol}): {e}")
                failed_count += 1
        
        # Commit all inserts
        session.commit()
        
        # Report results
        logger.info("=" * 80)
        logger.info("CARD WEIGHTS POPULATION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total cards processed: {len(cards_data)}")
        logger.info(f"Successfully created: {successful_count}")
        logger.info(f"Failed to create: {failed_count}")
        logger.info("-" * 80)
        logger.info("TIER DISTRIBUTION:")
        logger.info(f"  🔥 TOP tier (base_weight 3.0): {len(tier_stats['top'])} cards")
        logger.info(f"     Tokens: {', '.join(tier_stats['top'])}")
        logger.info(f"  ⚡ MID tier (base_weight 2.0): {len(tier_stats['mid'])} cards")
        logger.info(f"     Tokens: {', '.join(tier_stats['mid'])}")
        logger.info(f"  📦 LOW tier (base_weight 1.0): {len(tier_stats['low'])} cards")
        logger.info(f"     Tokens: {', '.join(tier_stats['low'])}")
        logger.info("=" * 80)
        
        return successful_count, failed_count
        
    except Exception as e:
        logger.error(f"Error populating card_weights: {e}")
        session.rollback()
        return 0, len(cards_data) if 'cards_data' in locals() else 0

def verify_card_weights(session):
    """Verify card_weights were inserted correctly"""
    try:
        logger.info("Verifying card_weights table...")
        
        # Count by tier
        verify_query = text("""
            SELECT 
                cw.base_weight,
                COUNT(*) as count,
                ARRAY_AGG(t.symbol ORDER BY t.weight DESC, t.symbol) as tokens
            FROM card_weights cw
            JOIN cards c ON cw.card_id = c.id
            JOIN tokens t ON c.token_id = t.id
            GROUP BY cw.base_weight
            ORDER BY cw.base_weight DESC
        """)
        
        result = session.execute(verify_query)
        
        logger.info("\n" + "=" * 80)
        logger.info("VERIFICATION RESULTS:")
        logger.info("=" * 80)
        
        for row in result:
            base_weight, count, tokens = row
            tier_name = "TOP" if base_weight >= 3.0 else ("MID" if base_weight >= 2.0 else "LOW")
            tier_emoji = "🔥" if tier_name == "TOP" else ("⚡" if tier_name == "MID" else "📦")
            
            logger.info(f"\n{tier_emoji} {tier_name} tier (base_weight={base_weight}):")
            logger.info(f"  Count: {count} cards")
            logger.info(f"  Tokens: {', '.join(tokens)}")
        
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"Error verifying card_weights: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("STARTING CARD WEIGHTS POPULATION SCRIPT")
    logger.info("For 35 cards: 5 packs x 7 cards pool (5 drops per pack)")
    logger.info("=" * 80)
    
    session = None
    
    try:
        # Create database connection
        logger.info("Connecting to database...")
        engine, session = create_database_connection()
        
        # Clear existing card weights
        if not clear_card_weights_table(session):
            logger.error("Failed to clear card_weights table. Aborting.")
            return False
        
        # Populate card weights
        success_count, fail_count = populate_card_weights(session)
        
        if success_count == 0:
            logger.error("No card weights were successfully created. Aborting.")
            return False
        
        # Verify results
        verify_card_weights(session)
        
        logger.info("=" * 80)
        logger.info("✅ CARD WEIGHTS POPULATION COMPLETED SUCCESSFULLY!")
        logger.info("=" * 80)
        
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
        logger.info("✅ Script completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Script failed")
        sys.exit(1)