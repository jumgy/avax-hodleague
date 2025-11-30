# migrations/migrate_001_create_and_update.py
"""
Migration: Create all missing tables from models
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from models.database import sync_engine, Base
import logging

logger = logging.getLogger(__name__)

def create_all_tables():
    """Create all tables from SQLAlchemy models"""
    try:
        print("🚀 Creating all database tables from models...")
        
        # Импортируем все модели чтобы они зарегистрировались в Base.metadata
        from models.user_models import User
        from models.token_models import Token, TokenPrice  # ДВЕ модели в одном файле!
        from models.tournament_models import Tournament
        from models.card_models import Card
        
        print(f"📋 Models registered in Base.metadata:")
        for table_name in Base.metadata.tables.keys():
            print(f"  - {table_name}")
        
        # Создаем все таблицы
        Base.metadata.create_all(bind=sync_engine)
        print("✅ All tables created successfully!")
        
        # Проверяем что создалось
        inspector = inspect(sync_engine)
        existing_tables = inspector.get_table_names()
        
        print(f"📋 Created tables ({len(existing_tables)}):")
        for table in existing_tables:
            columns = inspector.get_columns(table)
            print(f"  - {table} ({len(columns)} columns)")
            # Показываем первые несколько колонок для key tables
            if table in ['users', 'tokens', 'token_prices']:
                col_names = [col['name'] for col in columns[:5]]
                print(f"    Columns: {', '.join(col_names)}")
                if len(columns) > 5:
                    print(f"    ... and {len(columns)-5} more")
            
        return existing_tables
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        print(f"❌ Error creating tables: {e}")
        raise

def verify_tables():
    """Verify all expected tables exist"""
    try:
        # ПРАВИЛЬНЫЙ список ожидаемых таблиц
        expected_tables = ['users', 'tokens', 'token_prices', 'tournaments', 'cards']
        
        inspector = inspect(sync_engine)
        existing_tables = inspector.get_table_names()
        
        print("🔍 Verifying required tables...")
        all_good = True
        
        for table in expected_tables:
            if table in existing_tables:
                columns = inspector.get_columns(table)
                print(f"✅ {table} - {len(columns)} columns")
            else:
                print(f"❌ {table} - MISSING!")
                all_good = False
        
        # Показываем детали для ключевых таблиц
        if 'users' in existing_tables:
            user_columns = [col['name'] for col in inspector.get_columns('users')]
            print(f"   👤 users: {', '.join(user_columns)}")
            
        if 'token_prices' in existing_tables:
            price_columns = [col['name'] for col in inspector.get_columns('token_prices')]
            print(f"   💰 token_prices: {', '.join(price_columns)}")
        
        return all_good
        
    except Exception as e:
        logger.error(f"Error verifying tables: {e}")
        return False

def insert_sample_data():
    """Insert some sample data for testing"""
    try:
        print("🔄 Inserting sample data...")
        
        with sync_engine.connect() as conn:
            trans = conn.begin()
            
            # Проверяем есть ли уже данные
            result = conn.execute(text("SELECT COUNT(*) FROM tokens"))
            token_count = result.scalar()
            
            if token_count == 0:
                print("➕ Adding sample tokens...")
                
                sample_tokens = [
                    ("Bitcoin", "BTC", 10, "https://cryptoicons.org/api/icon/btc/200"),
                    ("Ethereum", "ETH", 9, "https://cryptoicons.org/api/icon/eth/200"),
                    ("Solana", "SOL", 8, "https://cryptoicons.org/api/icon/sol/200"),
                ]
                
                for name, symbol, weight, image_url in sample_tokens:
                    conn.execute(text("""
                        INSERT INTO tokens (name, symbol, weight, image_url) 
                        VALUES (:name, :symbol, :weight, :image_url)
                    """), {
                        "name": name, 
                        "symbol": symbol, 
                        "weight": weight, 
                        "image_url": image_url
                    })
                
                print(f"✅ Added {len(sample_tokens)} sample tokens")
            else:
                print(f"✅ Tokens table already has {token_count} records")
            
            trans.commit()
            
    except Exception as e:
        print(f"⚠️  Sample data insertion failed: {e}")
        if 'trans' in locals():
            trans.rollback()

def run_migration():
    """Execute full migration"""
    try:
        print("🚀 Starting database migration...")
        print(f"🔗 Database: hodleague")
        print(f"👤 User: hodleague_user")
        
        # 1. Создаем все таблицы
        created_tables = create_all_tables()
        
        # 2. Проверяем что все нужные таблицы созданы
        if verify_tables():
            print("🎉 All required tables created successfully!")
        else:
            print("⚠️  Migration completed with warnings - some tables missing")
        
        # 3. Добавляем немного тестовых данных
        if 'tokens' in created_tables:
            insert_sample_data()
        
        # 4. Показываем финальное состояние
        print("\n📊 Final database state:")
        with sync_engine.connect() as conn:
            for table in created_tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  {table}: {count} rows")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
