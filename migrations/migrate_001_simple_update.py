# migrations/migrate_002_simple_tables.py
"""
Simple migration: Create tables without ENUMs
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models.database import sync_engine
import logging

logger = logging.getLogger(__name__)

def create_tables_manually():
    """Create tables with simple SQL - no ENUMs"""
    try:
        print("🚀 Creating tables manually...")
        
        with sync_engine.connect() as conn:
            trans = conn.begin()
            
            # 1. Users table
            print("👥 Creating users table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    wallet_address VARCHAR(42) NOT NULL UNIQUE,
                    nickname VARCHAR(50) NOT NULL UNIQUE,
                    referral_route VARCHAR(20) NOT NULL UNIQUE,
                    avatar_url VARCHAR(500) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # 2. Tokens table
            print("🪙 Creating tokens table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tokens (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    symbol VARCHAR(20) NOT NULL UNIQUE,
                    weight INTEGER NOT NULL,
                    image_url VARCHAR(500) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # 3. Token prices table  
            print("💰 Creating token_prices table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS token_prices (
                    id SERIAL PRIMARY KEY,
                    token_id INTEGER NOT NULL REFERENCES tokens(id),
                    price DECIMAL(20,8) NOT NULL,
                    market_cap BIGINT,
                    change_24h DECIMAL(10,4),
                    sources_count INTEGER NOT NULL DEFAULT 1,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # 4. Tournaments table (БЕЗ ENUM!)
            print("🏆 Creating tournaments table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tournaments (
                    id SERIAL PRIMARY KEY,
                    tournament_number INTEGER NOT NULL UNIQUE,
                    status VARCHAR(20) NOT NULL DEFAULT 'registration',
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # 5. Cards table
            print("🎴 Creating cards table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cards (
                    id SERIAL PRIMARY KEY,
                    token_id INTEGER NOT NULL REFERENCES tokens(id),
                    rarity VARCHAR(20) NOT NULL,
                    design_type VARCHAR(50) NOT NULL,
                    background_image_url VARCHAR(500) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # 6. Создаем индексы
            print("📊 Creating indexes...")
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_users_wallet ON users(wallet_address)",
                "CREATE INDEX IF NOT EXISTS idx_users_nickname ON users(nickname)",
                "CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_token_prices_token_id ON token_prices(token_id)",
                "CREATE INDEX IF NOT EXISTS idx_token_prices_timestamp ON token_prices(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_tournaments_status ON tournaments(status)",
                "CREATE INDEX IF NOT EXISTS idx_cards_token_id ON cards(token_id)"
            ]
            
            for index_sql in indexes:
                conn.execute(text(index_sql))
            
            trans.commit()
            print("✅ All tables created successfully!")
            
            # Проверяем что создалось
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            print(f"📋 Created tables: {', '.join(tables)}")
            
            # Добавляем тестовые токены
            print("🔄 Adding sample tokens...")
            result = conn.execute(text("SELECT COUNT(*) FROM tokens"))
            if result.scalar() == 0:
                trans = conn.begin()
                conn.execute(text("""
                    INSERT INTO tokens (name, symbol, weight, image_url) VALUES 
                    ('Bitcoin', 'BTC', 10, 'https://cryptoicons.org/api/icon/btc/200'),
                    ('Ethereum', 'ETH', 9, 'https://cryptoicons.org/api/icon/eth/200'),
                    ('Solana', 'SOL', 8, 'https://cryptoicons.org/api/icon/sol/200')
                """))
                trans.commit()
                print("✅ Added sample tokens")
            
            return tables
            
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        if 'trans' in locals():
            trans.rollback()
        raise

def run_migration():
    """Execute migration"""
    try:
        print("🚀 Starting simple migration without ENUMs...")
        print(f"🔗 Database: hodleague")
        print(f"👤 User: hodleague_user")
        
        tables = create_tables_manually()
        
        # Показываем финальное состояние
        print("\n📊 Final database state:")
        with sync_engine.connect() as conn:
            for table in tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  {table}: {count} rows")
        
        print("🎉 Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
