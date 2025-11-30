# migrations/add_sample_data.py
"""
Add sample data to empty tables
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models.database import sync_engine
import logging

def add_sample_tokens():
    """Add sample tokens"""
    try:
        print("🔄 Adding sample tokens...")
        
        with sync_engine.connect() as conn:
            # Проверяем есть ли данные
            result = conn.execute(text("SELECT COUNT(*) FROM tokens"))
            token_count = result.scalar()
            
            if token_count == 0:
                print("➕ Inserting sample tokens...")
                
                # Используем отдельные транзакции для каждого токена
                tokens = [
                    ("Bitcoin", "BTC", 10, "https://cryptoicons.org/api/icon/btc/200"),
                    ("Ethereum", "ETH", 9, "https://cryptoicons.org/api/icon/eth/200"), 
                    ("Solana", "SOL", 8, "https://cryptoicons.org/api/icon/sol/200"),
                    ("Polygon", "MATIC", 7, "https://cryptoicons.org/api/icon/matic/200"),
                    ("Chainlink", "LINK", 6, "https://cryptoicons.org/api/icon/link/200")
                ]
                
                for name, symbol, weight, image_url in tokens:
                    trans = conn.begin()
                    try:
                        conn.execute(text("""
                            INSERT INTO tokens (name, symbol, weight, image_url) 
                            VALUES (:name, :symbol, :weight, :image_url)
                        """), {"name": name, "symbol": symbol, "weight": weight, "image_url": image_url})
                        trans.commit()
                        print(f"  ✅ Added {symbol}")
                    except Exception as e:
                        trans.rollback()
                        print(f"  ⚠️ Failed to add {symbol}: {e}")
                
                # Проверяем результат
                result = conn.execute(text("SELECT COUNT(*) FROM tokens"))
                final_count = result.scalar()
                print(f"✅ Successfully added tokens. Total: {final_count}")
                
                # Показываем что добавилось
                result = conn.execute(text("SELECT name, symbol FROM tokens ORDER BY weight DESC"))
                tokens_list = result.fetchall()
                print("📋 Tokens in database:")
                for token in tokens_list:
                    print(f"  - {token[1]}: {token[0]}")
                    
            else:
                print(f"✅ Tokens table already has {token_count} records")
        
    except Exception as e:
        print(f"❌ Error adding tokens: {e}")

if __name__ == "__main__":
    add_sample_tokens()
