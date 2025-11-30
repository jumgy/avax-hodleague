# migrations/migrate_001_simple_update.py
"""
Simple migration: Update token_prices table structure step by step
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models.database import sync_engine
import logging

logger = logging.getLogger(__name__)

def run_migration():
    """Execute the migration step by step"""
    try:
        print("🚀 Starting simple migration for token_prices...")
        
        with sync_engine.connect() as conn:
            
            # Выполняем каждый шаг отдельной транзакцией
            steps = [
                ("Adding change_24h column", "ALTER TABLE token_prices ADD COLUMN IF NOT EXISTS change_24h DECIMAL(10,4)"),
                ("Adding sources_count column", "ALTER TABLE token_prices ADD COLUMN IF NOT EXISTS sources_count INTEGER DEFAULT 1"),
                ("Adding timestamp column", "ALTER TABLE token_prices ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("Making market_cap nullable", "ALTER TABLE token_prices ALTER COLUMN market_cap DROP NOT NULL")
            ]
            
            for step_name, sql_command in steps:
                try:
                    print(f"🔄 {step_name}...")
                    
                    # Новая транзакция для каждого шага
                    trans = conn.begin()
                    conn.execute(text(sql_command))
                    trans.commit()
                    
                    print(f"✅ {step_name} - completed")
                    
                except Exception as e:
                    print(f"⚠️  {step_name} - skipped: {e}")
                    trans.rollback()
                    continue
            
            # Копируем данные из created_at в timestamp если нужно
            try:
                print("🔄 Copying created_at to timestamp...")
                trans = conn.begin()
                result = conn.execute(text("""
                    UPDATE token_prices 
                    SET timestamp = created_at 
                    WHERE timestamp IS NULL AND created_at IS NOT NULL
                """))
                trans.commit()
                print(f"✅ Updated {result.rowcount} rows")
            except Exception as e:
                print(f"⚠️  Copy data step skipped: {e}")
                trans.rollback()
            
            # Удаляем created_at колонку
            try:
                print("🔄 Dropping created_at column...")
                trans = conn.begin()
                conn.execute(text("ALTER TABLE token_prices DROP COLUMN IF EXISTS created_at"))
                trans.commit()
                print("✅ Dropped created_at column")
            except Exception as e:
                print(f"⚠️  Drop column step skipped: {e}")
                trans.rollback()
                
        print("🎉 Migration completed successfully!")
        
        # Простая проверка результата
        with sync_engine.connect() as conn:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'token_prices'"))
            columns = [row[0] for row in result]
            print(f"📋 Final columns: {', '.join(columns)}")
                
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()