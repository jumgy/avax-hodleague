# migrations/migration_runner.py
import os
import sys
import importlib.util
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

# Добавляем корневую папку в PATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import sync_engine, get_sync_db

class MigrationRunner:
    def __init__(self):
        self.migrations_dir = os.path.dirname(os.path.abspath(__file__))
    
    def get_migration_files(self):
        """Get all migration files sorted by name"""
        files = [f for f in os.listdir(self.migrations_dir) if f.startswith('migrate_') and f.endswith('.py')]
        return sorted(files)
    
    def run_migration(self, migration_file):
        """Run a specific migration file"""
        print(f"🔄 Running migration: {migration_file}")
        
        # Import migration module
        spec = importlib.util.spec_from_file_location(
            migration_file[:-3], 
            os.path.join(self.migrations_dir, migration_file)
        )
        migration_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration_module)
        
        # Run migration
        migration_module.run_migration()
        print(f"✅ Migration completed: {migration_file}")
    
    def run_all_migrations(self):
        """Run all pending migrations"""
        print("🚀 Starting migration process...")
        
        migration_files = self.get_migration_files()
        
        if not migration_files:
            print("📭 No migrations found")
            return
        
        for migration_file in migration_files:
            try:
                self.run_migration(migration_file)
            except Exception as e:
                print(f"❌ Migration failed: {migration_file}")
                print(f"Error: {e}")
                raise
        
        print("🎉 All migrations completed successfully!")

if __name__ == "__main__":
    runner = MigrationRunner()
    runner.run_all_migrations()