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

# Rarities data
RARITIES_DATA = [
    {
        'name': 'common',
        'description': 'Common rarity cards with standard scoring',
        'score_bonus': 1,
        'color': '#6B7280'  # Gray
    }
]

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

def clear_rarities_table(session):
    """Clear all records from rarities table"""
    try:
        logger.info("Clearing rarities table...")
        result = session.execute(text("DELETE FROM rarities"))
        deleted_count = result.rowcount
        session.commit()
        logger.info(f"Deleted {deleted_count} existing rarity records")
        return True
    except Exception as e:
        logger.error(f"Failed to clear rarities table: {e}")
        session.rollback()
        return False

def insert_rarity_with_sql(session, name, description, score_bonus, color):
    """Insert rarity using raw SQL"""
    try:
        sql = text("""
            INSERT INTO rarities (name, description, score_bonus, color, is_active, created_at, updated_at)
            VALUES (:name, :description, :score_bonus, :color, :is_active, :created_at, :updated_at)
        """)
        
        session.execute(sql, {
            'name': name,
            'description': description,
            'score_bonus': score_bonus,
            'color': color,
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        })
        
        return True
        
    except Exception as e:
        logger.error(f"Error inserting rarity {name}: {e}")
        return False

def populate_rarities(session):
    """Populate rarities table"""
    try:
        successful_rarities = []
        failed_rarities = []
        
        logger.info("Creating rarity records...")
        
        for rarity_data in RARITIES_DATA:
            try:
                name = rarity_data['name']
                description = rarity_data['description']
                score_bonus = rarity_data['score_bonus']
                color = rarity_data['color']
                
                logger.info(f"Creating rarity: {name} (bonus: {score_bonus}, color: {color})")
                
                success = insert_rarity_with_sql(session, name, description, score_bonus, color)
                
                if success:
                    successful_rarities.append(name)
                    logger.info(f"✅ Successfully created rarity {name}")
                else:
                    failed_rarities.append(name)
                    logger.error(f"❌ Failed to create rarity {name}")
                    
            except Exception as e:
                logger.error(f"Failed to create rarity {name}: {e}")
                failed_rarities.append(name)
        
        # Commit all inserts
        session.commit()
        logger.info(f"Successfully inserted {len(successful_rarities)} rarities")
        
        # Report results
        logger.info(f"=== RESULTS ===")
        logger.info(f"Total rarities to process: {len(RARITIES_DATA)}")
        logger.info(f"Successfully created: {len(successful_rarities)}")
        logger.info(f"Failed to create: {len(failed_rarities)}")
        
        if successful_rarities:
            logger.info(f"Successful rarities: {', '.join(successful_rarities)}")
        
        if failed_rarities:
            logger.warning(f"Failed rarities: {', '.join(failed_rarities)}")
            
        return len(successful_rarities), len(failed_rarities)
        
    except Exception as e:
        logger.error(f"Error populating rarities: {e}")
        session.rollback()
        return 0, len(RARITIES_DATA)

def verify_rarities_table(session):
    """Verify rarities were inserted correctly"""
    try:
        logger.info("Verifying rarities table...")
        
        # Count total rarities
        total_result = session.execute(text("SELECT COUNT(*) FROM rarities"))
        total_count = total_result.scalar()
        
        active_result = session.execute(text("SELECT COUNT(*) FROM rarities WHERE is_active = true"))
        active_count = active_result.scalar()
        
        logger.info(f"Total rarities in database: {total_count}")
        logger.info(f"Active rarities: {active_count}")
        
        # Show all rarities
        rarities_result = session.execute(text("SELECT name, description, score_bonus, color FROM rarities ORDER BY score_bonus"))
        
        logger.info("Created rarities:")
        for row in rarities_result:
            name, description, score_bonus, color = row
            logger.info(f"  {name.upper()}: bonus={score_bonus}, color={color}")
            logger.info(f"    Description: {description}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error verifying rarities table: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("=== Starting rarities population script ===")
    
    session = None
    try:
        # Create database connection
        logger.info("Connecting to database...")
        engine, session = create_database_connection()
        
        # Clear existing rarities
        if not clear_rarities_table(session):
            logger.error("Failed to clear rarities table. Aborting.")
            return False
        
        # Populate rarities
        success_count, fail_count = populate_rarities(session)
        
        if success_count == 0:
            logger.error("No rarities were successfully created. Aborting.")
            return False
        
        # Verify results
        verify_rarities_table(session)
        
        logger.info("=== Rarities population completed successfully! ===")
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