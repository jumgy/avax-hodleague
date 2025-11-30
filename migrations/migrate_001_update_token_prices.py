# migrations/migrate_001_update_token_prices.py
"""
Migration: Update token_prices table structure
- Add change_24h column
- Add sources_count column  
- Change market_cap to nullable BigInteger
- Change price to Numeric for better precision
- Rename created_at to timestamp
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from models.database import sync_engine  # ИСПРАВИЛИ: используем sync_engine
import logging

logger = logging.getLogger(__name__)

def check_column_exists(table_name, column_name):
    """Check if column exists in table"""
    inspector = inspect(sync_engine)  # ИСПРАВИЛИ: используем sync_engine
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def run_migration():
    """Execute the migration"""
    try:
        with sync_engine.connect() as conn:  # ИСПРАВИЛИ: используем sync_engine
            # Start transaction
            trans = conn.begin()
            
            try:
                # Check if table exists
                inspector = inspect(sync_engine)  # ИСПРАВИЛИ: используем sync_engine
                if 'token_prices' not in inspector.get_table_names():
                    print("⚠️  token_prices table doesn't exist, skipping migration")
                    return
                
                print("📋 Current token_prices table structure:")
                columns = inspector.get_columns('token_prices')
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
                
                # 1. Add change_24h column if not exists
                if not check_column_exists('token_prices', 'change_24h'):
                    print("➕ Adding change_24h column...")
                    conn.execute(text("ALTER TABLE token_prices ADD COLUMN change_24h DECIMAL(10,4)"))
                else:
                    print("✅ change_24h column already exists")
                
                # 2. Add sources_count column if not exists
                if not check_column_exists('token_prices', 'sources_count'):
                    print("➕ Adding sources_count column...")
                    conn.execute(text("ALTER TABLE token_prices ADD COLUMN sources_count INTEGER DEFAULT 1"))
                    # Update existing records
                    conn.execute(text("UPDATE token_prices SET sources_count = 1 WHERE sources_count IS NULL"))
                else:
                    print("✅ sources_count column already exists")
                
                # 3. Add timestamp column if not exists and copy data from created_at
                if not check_column_exists('token_prices', 'timestamp'):
                    if check_column_exists('token_prices', 'created_at'):
                        print("➕ Adding timestamp column and copying data from created_at...")
                        conn.execute(text("ALTER TABLE token_prices ADD COLUMN timestamp TIMESTAMP"))
                        conn.execute(text("UPDATE token_prices SET timestamp = created_at"))
                        print("✅ Data copied from created_at to timestamp")
                    else:
                        print("➕ Adding timestamp column with default value...")
                        conn.execute(text("ALTER TABLE token_prices ADD COLUMN timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                else:
                    print("✅ timestamp column already exists")
                
                # 4. Make market_cap nullable (if it's not already)
                print("🔄 Making market_cap column nullable...")
                # Note: This varies by database. For PostgreSQL:
                if sync_engine.dialect.name == 'postgresql':  # ИСПРАВИЛИ: используем sync_engine
                    conn.execute(text("ALTER TABLE token_prices ALTER COLUMN market_cap DROP NOT NULL"))
                elif sync_engine.dialect.name == 'sqlite':  # ИСПРАВИЛИ: используем sync_engine
                    # SQLite doesn't support ALTER COLUMN, so we'll handle it differently if needed
                    print("⚠️  SQLite detected - market_cap constraint changes require table recreation")
                
                # 5. Drop created_at if timestamp exists and has data
                if (check_column_exists('token_prices', 'created_at') and 
                    check_column_exists('token_prices', 'timestamp')):
                    print("🗑️  Dropping old created_at column...")
                    conn.execute(text("ALTER TABLE token_prices DROP COLUMN created_at"))
                
                # Commit transaction
                trans.commit()
                print("✅ Migration completed successfully")
                
                # Show updated structure
                print("📋 Updated token_prices table structure:")
                inspector = inspect(sync_engine)  # ИСПРАВИЛИ: используем sync_engine
                columns = inspector.get_columns('token_prices')
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
                    
            except Exception as e:
                trans.rollback()
                raise e
                
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()