# models/database.py
import os
from typing import AsyncGenerator, Optional
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from config import Config
import logging

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = Config.DATABASE_URL
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

# SQLAlchemy engines
async_engine = create_async_engine(
    DATABASE_URL,
    echo=Config.DB_ECHO,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=os.environ.get("DB_ECHO", "False").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Session makers
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)

# Base class for all models
Base = declarative_base()


# Dependency for FastAPI
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get async database session.
    Use this in your route dependencies.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


# Sync session for migrations and one-time operations
def get_sync_db():
    """
    Get sync database session for migrations and admin operations.
    """
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Sync database session error: {e}")
        raise
    finally:
        db.close()

async def init_database():
    """
    Initialize database - create all tables.
    Call this on application startup.
    """
    try:
        logger.info("Initializing database...")
        async with async_engine.begin() as conn:
            # from . import token_models, user_models, card_models, tournament_models
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_database():
    """
    Close database connections.
    Call this on application shutdown.
    """
    try:
        logger.info("Closing database connections...")
        await async_engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")


def create_tables_sync():
    """
    Synchronous function to create tables.
    Useful for migrations and setup scripts.
    """
    try:
        logger.info("Creating tables (sync)...")
        # from . import token_models, user_models, card_models, tournament_models
        
        Base.metadata.create_all(bind=sync_engine)
        logger.info("Tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        raise


async def check_database_connection():
    """
    Check if database connection is working.
    Returns True if connection is successful.
    """
    try:
        clean_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        
        import asyncpg
        conn = await asyncpg.connect(clean_url)
        await conn.fetchval("SELECT 1")
        await conn.close()
        
        logger.info("Database connection check: OK")
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


# Helper function to get database info
def get_database_info():
    """
    Get database configuration info (without sensitive data).
    """
    return {
        "url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "Not configured",
        "engine": "PostgreSQL",
        "async_support": True,
        "pool_size": async_engine.pool.size(),
        "checked_out": async_engine.pool.checkedout(),
    }


# Context manager for manual database operations
class DatabaseSession:
    """
    Context manager for manual database operations.
    
    Usage:
        async with DatabaseSession() as db:
            result = await db.execute(query)
    """
    
    def __init__(self):
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> AsyncSession:
        self.session = AsyncSessionLocal()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type:
                await self.session.rollback()
                logger.error(f"Database transaction rolled back due to: {exc_val}")
            else:
                await self.session.commit()
            await self.session.close()


# Configuration validation
def validate_database_config():
    """
    Validate database configuration.
    Raises ValueError if configuration is invalid.
    """
    if not DATABASE_URL or DATABASE_URL == "postgresql+asyncpg://username:password@localhost:5432/fantasy_crypto":
        raise ValueError(
            "DATABASE_URL environment variable must be set with valid PostgreSQL connection string. "
            "Example: postgresql+asyncpg://user:password@localhost:5432/dbname"
        )
    
    if "asyncpg" not in DATABASE_URL:
        raise ValueError("DATABASE_URL must use asyncpg driver for async operations")
    
    logger.info("Database configuration validated successfully")


# Initialize on import
if __name__ == "__main__":
    # For testing database connection
    import asyncio
    
    async def test_connection():
        validate_database_config()
        success = await check_database_connection()
        if success:
            print("✅ Database connection successful")
        else:
            print("❌ Database connection failed")
        await close_database()
    
    asyncio.run(test_connection())