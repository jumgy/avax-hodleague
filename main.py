# main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from api.routes.admin import admin_router
from services.scheduler_service import scheduler_service
from config import Config
from models.database import init_database, close_database

# Setup logging first
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)

logger = logging.getLogger(__name__)

# Startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    # STARTUP
    logger.info("🚀 Hodleague starting up...")
    
    # Initialize database
    try:
        await init_database()
        logger.info("✅ Database tables created/verified")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}", exc_info=True)
    
    # Start scheduler
    try:
        await scheduler_service.start()
        logger.info("✅ Price monitoring scheduler started")
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}", exc_info=True)
    
    logger.info("✅ Application startup complete")
    
    yield
    
    # SHUTDOWN
    logger.info("🛑 Hodleague shutting down...")
    
    # Stop scheduler
    try:
        await scheduler_service.stop()
        logger.info("✅ Price monitoring scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping scheduler: {e}", exc_info=True)
    
    # Close database connections
    try:
        await close_database()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing database: {e}", exc_info=True)
    
    logger.info("✅ Application shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Hodleague API",
    description="API for fantasy cryptocurrency trading game", 
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/swagger",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Setup CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене заменить на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

# Include routers
app.include_router(api_router, prefix="/api")
app.include_router(admin_router)

# Main index endpoint
@app.get("/", tags=["Root"])
async def root():
    """Main API information endpoint"""
    return {
        "message": "Hodleague API",
        "version": "1.0.0",
        "framework": "FastAPI",
        "async_engine": "PostgreSQL + asyncpg",
        "docs": "/swagger",
        "endpoints": {
            "tokens": {
                "GET /api/tokens": "Get 30 game tokens for user selection",
                "GET /api/simulation-tokens": "Get 100 tokens for simulation calculations"
            },
            "tournaments": {
                "GET /api/tournaments": "Get tournaments list",
                "GET /api/tournaments/{id}": "Get tournament details",
                "POST /api/tournaments/register": "Register for tournament",
                "GET /api/tournaments/my-deck": "Get my tournament deck"
            },
            "simulation": {
                "POST /api/lock-deck": "Lock a deck of 5 tokens",
                "POST /api/simulate-session": "Run simulation for locked deck",
                "GET /api/session/{session_id}": "Get session details",
                "GET /api/session/{session_id}/results": "Get simulation results",
                "GET /api/sessions": "Get all sessions"
            },
            "auth": {
                "POST /api/auth/request-nonce": "Request nonce for wallet signature",
                "POST /api/auth/verify-signature": "Verify signature and login"
            },
            "admin": {
                "POST /panel/login": "Admin login",
                "GET /panel/dashboard/stats": "Dashboard statistics"
            }
        }
    }

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    from models.database import check_database_connection, get_database_info
    
    # Check database connection
    db_healthy = await check_database_connection()
    
    # Get database info
    db_info = get_database_info()
    
    return {
        "status": "healthy" if db_healthy else "degraded",
        "service": "hodleague-api",
        "version": "1.0.0",
        "database": {
            "status": "connected" if db_healthy else "disconnected",
            "engine": db_info.get("engine"),
            "driver": db_info.get("driver"),
            "pool_stats": {
                "size": db_info.get("pool_size"),
                "checked_out": db_info.get("checked_out"),
                "overflow": db_info.get("overflow")
            }
        },
        "scheduler": {
            "status": "running" if scheduler_service._started else "stopped"
        }
    }

# Database info endpoint (для отладки)
@app.get("/debug/database", tags=["Debug"])
async def database_info():
    """Get database connection information (for debugging)"""
    from models.database import get_database_info
    
    if Config.ENVIRONMENT == "production":
        return {"error": "Debug endpoints disabled in production"}
    
    return get_database_info()