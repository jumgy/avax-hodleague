# models/database.py

import os
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config import Config
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = Config.DATABASE_URL

# Validate that we're using asyncpg driver
if "asyncpg" not in DATABASE_URL:
    raise ValueError(
        "DATABASE_URL must use asyncpg driver for async operations. "
        "Example: postgresql+asyncpg://user:password@localhost:5432/dbname"
    )


async_engine = create_async_engine(
    DATABASE_URL,
    echo=Config.DB_ECHO,
    pool_size=20,              # Увеличил для concurrent запросов
    max_overflow=10,           # Уменьшил overflow
    pool_pre_ping=True,        # Проверка соединения перед использованием
    pool_recycle=3600,         # Пересоздавать соединения каждый час
    pool_timeout=30,           # Таймаут ожидания соединения из пула
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for all models
Base = declarative_base()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get async database session.
    
    Usage in routes:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    
    Auto-commits on success, rolls back on exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            await session.close()

async def init_database():
    """
    Initialize database - create all tables.
    Call this on application startup in main.py:
    
        @app.on_event("startup")
        async def startup():
            await init_database()
    """
    try:
        logger.info("Initializing database...")
        
        # Import all models to register them with Base
        from . import token_models, user_models, card_models, tournament_models
        
        async with async_engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
        raise

async def close_database():
    """
    Close database connections.
    Call this on application shutdown in main.py:
    
        @app.on_event("shutdown")
        async def shutdown():
            await close_database()
    """
    try:
        logger.info("Closing database connections...")
        await async_engine.dispose()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing database: {e}", exc_info=True)

async def check_database_connection() -> bool:
    """
    Check if database connection is working.
    Returns True if connection is successful.
    
    Useful for health checks:
        @router.get("/health")
        async def health_check():
            db_ok = await check_database_connection()
            return {"database": "ok" if db_ok else "error"}
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")
        logger.info("✅ Database connection check: OK")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection check failed: {e}")
        return False


def get_database_info() -> dict:
    """
    Get database configuration info (without sensitive data).
    Returns dict with connection pool stats.
    """
    try:
        return {
            "url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "Not configured",
            "engine": "PostgreSQL",
            "driver": "asyncpg",
            "async_support": True,
            "pool_size": async_engine.pool.size(),
            "checked_out": async_engine.pool.checkedout(),
            "overflow": async_engine.pool.overflow(),
        }
    except Exception as e:
        logger.error(f"Error getting database info: {e}")
        return {"error": str(e)}


class DatabaseSession:
    """
    Context manager for manual database operations outside of FastAPI routes.
    
    Usage:
        async with DatabaseSession() as db:
            result = await db.execute(select(User).where(User.id == 1))
            user = result.scalar_one_or_none()
            
            if user:
                user.balance += 100
                # Auto-commits on exit
    
    Auto-commits on success, rolls back on exception.
    """
    
    def __init__(self):
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> AsyncSession:
        self.session = AsyncSessionLocal()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            try:
                if exc_type:
                    await self.session.rollback()
                    logger.error(f"Transaction rolled back due to: {exc_val}")
                else:
                    await self.session.commit()
            except Exception as e:
                await self.session.rollback()
                logger.error(f"Error during transaction cleanup: {e}")
            finally:
                await self.session.close()

# ============================================================================
# MIGRATION HELPER (for Alembic or manual migrations)
# ============================================================================

async def drop_all_tables():
    """
    ⚠️ DANGER: Drop all tables from database.
    Use only in development/testing!
    """
    if Config.ENVIRONMENT == "production":
        raise RuntimeError("❌ Cannot drop tables in production!")
    
    try:
        logger.warning("⚠️ Dropping all tables...")
        from . import token_models, user_models, card_models, tournament_models
        
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        
        logger.info("✅ All tables dropped")
    except Exception as e:
        logger.error(f"❌ Failed to drop tables: {e}")
        raise


def validate_database_config():
    """
    Validate database configuration on module import.
    Raises ValueError if configuration is invalid.
    """
    if not DATABASE_URL or "username:password" in DATABASE_URL:
        raise ValueError(
            "DATABASE_URL environment variable must be set with valid PostgreSQL connection string. "
            "Example: postgresql+asyncpg://user:password@localhost:5432/dbname"
        )
    
    if "asyncpg" not in DATABASE_URL:
        raise ValueError("DATABASE_URL must use asyncpg driver (postgresql+asyncpg://)")
    
    logger.info("✅ Database configuration validated")

# Validate on import
validate_database_config()

if __name__ == "__main__":
    # Test database connection
    import asyncio
    
    async def test_connection():
        print("🔍 Testing database connection...")
        print(f"📊 Database info: {get_database_info()}")
        
        success = await check_database_connection()
        
        if success:
            print("✅ Database connection successful!")
            
            # Test session creation
            try:
                async with DatabaseSession() as db:
                    result = await db.execute("SELECT version()")
                    version = result.scalar()
                    print(f"📦 PostgreSQL version: {version}")
            except Exception as e:
                print(f"❌ Session test failed: {e}")
        else:
            print("❌ Database connection failed!")
        
        await close_database()
    
    asyncio.run(test_connection())