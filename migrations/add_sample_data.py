#!/usr/bin/env python3
"""
Sample Data Script for Hodleague Fantasy Crypto Game
Adds sample cryptocurrency tokens to the database with proper transaction handling
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from models.database import sync_engine
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseSeeder:
    """Handle database seeding operations with proper transaction management"""
    
    def __init__(self):
        self.engine = sync_engine
        
    def check_connection(self):
        """Verify database connection"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT current_database(), current_user"))
                db_info = result.fetchone()
                print(f"🔗 Connected to database: {db_info[0]} as user: {db_info[1]}")
                return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
    
    def check_table_exists(self, table_name):
        """Check if a table exists in the database"""
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            return table_name in tables
        except Exception as e:
            print(f"❌ Error checking table existence: {e}")
            return False
    
    def get_table_count(self, table_name):
        """Get the number of rows in a table"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar()
        except Exception as e:
            print(f"❌ Error counting rows in {table_name}: {e}")
            return -1
    
    def insert_single_token(self, conn, name, symbol, weight, image_url):
        """Insert a single token with individual transaction"""
        try:
            # Start a new transaction for this insert
            trans = conn.begin()
            
            # Check if token already exists
            check_result = conn.execute(
                text("SELECT COUNT(*) FROM tokens WHERE symbol = :symbol"),
                {"symbol": symbol}
            )
            
            if check_result.scalar() > 0:
                trans.rollback()
                print(f"  ⚠️  {symbol} already exists, skipping")
                return False
            
            # Insert the token
            conn.execute(
                text("""
                    INSERT INTO tokens (name, symbol, weight, image_url, is_active, created_at, updated_at) 
                    VALUES (:name, :symbol, :weight, :image_url, :is_active, :created_at, :updated_at)
                """), 
                {
                    "name": name,
                    "symbol": symbol, 
                    "weight": weight,
                    "image_url": image_url,
                    "is_active": True,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            
            # Commit the transaction
            trans.commit()
            print(f"  ✅ Added {symbol}: {name}")
            return True
            
        except Exception as e:
            # Rollback on error
            if 'trans' in locals():
                trans.rollback()
            print(f"  ❌ Failed to add {symbol}: {e}")
            return False
    
    def add_sample_tokens(self):
        """Add sample cryptocurrency tokens to the database"""
        
        sample_tokens = [
            ("Bitcoin", "BTC", 10, "https://cryptoicons.org/api/icon/btc/200"),
            ("Ethereum", "ETH", 9, "https://cryptoicons.org/api/icon/eth/200"),
            ("Solana", "SOL", 8, "https://cryptoicons.org/api/icon/sol/200"),
            ("Polygon", "MATIC", 7, "https://cryptoicons.org/api/icon/matic/200"),
            ("Chainlink", "LINK", 6, "https://cryptoicons.org/api/icon/link/200"),
            ("Cardano", "ADA", 5, "https://cryptoicons.org/api/icon/ada/200"),
            ("Polkadot", "DOT", 4, "https://cryptoicons.org/api/icon/dot/200"),
            ("Avalanche", "AVAX", 3, "https://cryptoicons.org/api/icon/avax/200"),
            ("Binance Coin", "BNB", 2, "https://cryptoicons.org/api/icon/bnb/200"),
            ("XRP", "XRP", 1, "https://cryptoicons.org/api/icon/xrp/200")
        ]
        
        try:
            print("🚀 Starting token insertion process...")
            
            # Check if tokens table exists
            if not self.check_table_exists('tokens'):
                print("❌ Tokens table does not exist!")
                return False
            
            # Check current token count
            current_count = self.get_table_count('tokens')
            if current_count == -1:
                return False
                
            print(f"📊 Current tokens in database: {current_count}")
            
            if current_count > 0:
                print("⚠️  Tokens table is not empty. Adding only missing tokens...")
            
            # Use a single connection for all operations
            success_count = 0
            failed_count = 0
            
            with self.engine.connect() as conn:
                print(f"📝 Processing {len(sample_tokens)} tokens...")
                
                for name, symbol, weight, image_url in sample_tokens:
                    if self.insert_single_token(conn, name, symbol, weight, image_url):
                        success_count += 1
                    else:
                        failed_count += 1
            
            # Final statistics
            final_count = self.get_table_count('tokens')
            print(f"\n📊 Insertion completed:")
            print(f"  ✅ Successfully added: {success_count} tokens")
            print(f"  ❌ Failed/Skipped: {failed_count} tokens")
            print(f"  📋 Total tokens in database: {final_count}")
            
            return success_count > 0
            
        except Exception as e:
            print(f"❌ Error in token insertion process: {e}")
            return False
    
    def display_current_tokens(self):
        """Display all tokens currently in the database"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT id, name, symbol, weight, is_active 
                        FROM tokens 
                        ORDER BY weight DESC, symbol ASC
                    """)
                )
                
                tokens = result.fetchall()
                
                if not tokens:
                    print("📋 No tokens found in database")
                    return
                
                print(f"\n📋 Current tokens in database ({len(tokens)}):")
                print("  ID | Symbol | Name                | Weight | Active")
                print("  ---|--------|---------------------|--------|-------")
                
                for token in tokens:
                    active_status = "✅" if token[4] else "❌"
                    print(f"  {token[0]:2d} | {token[2]:6s} | {token[1]:19s} | {token[3]:6d} | {active_status}")
                    
        except Exception as e:
            print(f"❌ Error displaying tokens: {e}")
    
    def add_sample_price_data(self):
        """Add sample price data for existing tokens"""
        try:
            print("\n💰 Adding sample price data...")
            
            # Sample prices for major cryptocurrencies (approximate values)
            sample_prices = {
                "BTC": {"price": 42000.50, "market_cap": 825000000000, "change_24h": 2.35},
                "ETH": {"price": 2800.75, "market_cap": 337000000000, "change_24h": 1.85},
                "SOL": {"price": 95.25, "market_cap": 42000000000, "change_24h": 4.20},
                "MATIC": {"price": 0.85, "market_cap": 8500000000, "change_24h": -1.25},
                "LINK": {"price": 14.60, "market_cap": 8200000000, "change_24h": 0.75},
            }
            
            with self.engine.connect() as conn:
                # Get token IDs
                result = conn.execute(
                    text("SELECT id, symbol FROM tokens WHERE symbol = ANY(:symbols)"),
                    {"symbols": list(sample_prices.keys())}
                )
                
                token_map = {row[1]: row[0] for row in result}
                success_count = 0
                
                for symbol, price_data in sample_prices.items():
                    if symbol in token_map:
                        token_id = token_map[symbol]
                        
                        trans = conn.begin()
                        try:
                            conn.execute(
                                text("""
                                    INSERT INTO token_prices (token_id, price, market_cap, change_24h, sources_count, timestamp)
                                    VALUES (:token_id, :price, :market_cap, :change_24h, :sources_count, :timestamp)
                                """),
                                {
                                    "token_id": token_id,
                                    "price": price_data["price"],
                                    "market_cap": price_data["market_cap"],
                                    "change_24h": price_data["change_24h"],
                                    "sources_count": 1,
                                    "timestamp": datetime.utcnow()
                                }
                            )
                            trans.commit()
                            print(f"  ✅ Added price data for {symbol}: ${price_data['price']:,.2f}")
                            success_count += 1
                        except Exception as e:
                            trans.rollback()
                            print(f"  ❌ Failed to add price data for {symbol}: {e}")
                
                print(f"📊 Added price data for {success_count} tokens")
                
        except Exception as e:
            print(f"❌ Error adding price data: {e}")
    
    def run_full_seeding(self):
        """Run the complete seeding process"""
        print("🚀 Starting database seeding process...")
        print("=" * 50)
        
        # Check connection
        if not self.check_connection():
            return False
        
        # Add tokens
        tokens_added = self.add_sample_tokens()
        
        # Add price data
        if tokens_added:
            self.add_sample_price_data()
        
        # Display final state
        self.display_current_tokens()
        
        print("\n🎉 Database seeding completed!")
        return True

def main():
    """Main execution function"""
    try:
        seeder = DatabaseSeeder()
        success = seeder.run_full_seeding()
        
        if success:
            print("\n✅ Sample data has been successfully added to the database!")
            print("🚀 You can now start the application and test the APIs.")
        else:
            print("\n❌ Seeding process failed. Please check the errors above.")
            return 1
            
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n❌ Unexpected error occurred: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
