# migrations/migrate_003_sqlalchemy_proper.py
"""
Proper SQLAlchemy migration: Create all tables using models
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from models.database import Base, sync_engine
import logging

logger = logging.getLogger(__name__)

def check_database_permissions():
    """Check if we can create tables"""
    try:
        with sync_engine.connect() as conn:
            # Проверяем простым запросом
            result = conn.execute(text("SELECT current_user, session_user"))
            user_info = result.fetchone()
            print(f"🔐 Connected as: {user_info[0]} (session: {user_info[1]})")
            
            # Проверяем права на схему
            result = conn.execute(text("""
                SELECT has_schema_privilege(current_user, 'public', 'CREATE') as can_create,
                       has_schema_privilege(current_user, 'public', 'USAGE') as can_use
            """))
            perms = result.fetchone()
            print(f"📋 Schema permissions - CREATE: {perms[0]}, USAGE: {perms[1]}")
            
            return perms[0]  # True если можем создавать
            
    except Exception as e:
        print(f"❌ Permission check failed: {e}")
        return False

def create_tables_sqlalchemy():
    """Create tables using SQLAlchemy models - no ENUM problems!"""
    try:
        print("🚀 Creating tables using SQLAlchemy models...")
        
        # Импортируем все модели
        from models.user_models import User
        from models.token_models import Token, TokenPrice
        from models.tournament_models import Tournament  # Исправленная без ENUM
        from models.card_models import Card
        
        print("📋 Registered models:")
        for table_name, table in Base.metadata.tables.items():
            print(f"  - {table_name}")
        
        # Создаем все таблицы
        print("🔨 Creating tables...")
        Base.metadata.create_all(bind=sync_engine)
        
        print("✅ Tables created successfully!")
        
        # Проверяем что создалось
        inspector = inspect(sync_engine)
        existing_tables = inspector.get_table_names()
        
        print(f"📋 Created tables ({len(existing_tables)}):")
        for table in existing_tables:
            columns = inspector.get_columns(table)
            print(f"  ✅ {table} ({len(columns)} columns)")
        
        return existing_tables
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        raise

def insert_initial_data():
    """Insert some test data"""
    try:
        print("🔄 Inserting initial data...")
        
        with sync_engine.connect() as conn:
            # Проверяем есть ли данные в tokens
            result = conn.execute(text("SELECT COUNT(*) FROM tokens"))
            token_count = result.scalar()
            
            if token_count == 0:
                print("➕ Adding sample tokens...")
                trans = conn.begin()
                
                tokens = [
                    ("Bitcoin", "BTC", 10, "https://cryptoicons.org/api/icon/btc/200"),
                    ("Ethereum", "ETH", 9, "https://cryptoicons.org/api/icon/eth/200"), 
                    ("Solana", "SOL", 8, "https://cryptoicons.org/api/icon/sol/200"),
                    ("Polygon", "MATIC", 7, "https://cryptoicons.org/api/icon/matic/200"),
                    ("Chainlink", "LINK", 6, "https://cryptoicons.org/api/icon/link/200")
                ]
                
                for name, symbol, weight, image_url in tokens:
                    conn.execute(text("""
                        INSERT INTO tokens (name, symbol, weight, image_url) 
                        VALUES (:name, :symbol, :weight, :image_url)
                    """), {"name": name, "symbol": symbol, "weight": weight, "image_url": image_url})
                
                trans.commit()
                print(f"✅ Added {len(tokens)} tokens")
            else:
                print(f"✅ Tokens table already has {token_count} records")
        
    except Exception as e:
        print(f"⚠️  Initial data insertion failed: {e}")

def run_migration():
    """Execute proper migration"""
    try:
        print("🚀 Starting proper SQLAlchemy migration...")
        print(f"🔗 Database: hodleague")
        print(f"👤 User: hodleague_user")
        
        # 1. Проверяем права
        if not check_database_permissions():
            print("❌ Insufficient database permissions!")
            print("💡 Try running as postgres user or fix permissions")
            return
        
        # 2. Создаем таблицы через SQLAlchemy
        tables = create_tables_sqlalchemy()
        
        # 3. Добавляем начальные данные
        if tables:
            insert_initial_data()
        
        # 4. Финальная проверка
        print("\n📊 Final database state:")
        with sync_engine.connect() as conn:
            for table in tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  📋 {table}: {count} rows")
        
        print("🎉 Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
