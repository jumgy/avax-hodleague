# main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router
from api.routes.admin import admin_router
from services.scheduler_service import scheduler_service
from config import Config

from models.database import create_tables_sync, init_database

# Startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Hodleague starting up...")
    
    try:
        create_tables_sync()
        logging.info("✅ Database tables created/verified")
    except Exception as e:
        logging.error(f"❌ Database initialization failed: {e}")
    
    try:
        await scheduler_service.start()
        logging.info("✅ Price monitoring scheduler started")
    except Exception as e:
        logging.error(f"❌ Failed to start scheduler: {e}")

    yield

    try:
        await scheduler_service.stop()
        logging.info("✅ Price monitoring scheduler stopped")
    except Exception as e:
        logging.error(f"❌ Error stopping scheduler: {e}")

    logging.info("🛑 Hodleague shutting down...")

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

# Include routers
app.include_router(api_router, prefix="/api")
app.include_router(admin_router)

# Setup logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)

logger = logging.getLogger(__name__)

# Main index endpoint
@app.get("/", tags=["Root"])
async def root():
    """Main API information endpoint"""
    return {
        "message": "Hodleague API",
        "version": "1.0.0",
        "framework": "FastAPI",
        "docs": "/swagger",
        "endpoints": [
            "GET /api/tokens - Get 30 game tokens for user selection",
            "GET /api/simulation-tokens - Get 100 tokens for simulation calculations", 
            "GET /api/tournament - Get tournament information",
            "POST /api/lock-deck - Lock a deck of 5 tokens",
            "POST /api/simulate-session - Run simulation for locked deck",
            "GET /api/session/{session_id} - Get session details",
            "GET /api/session/{session_id}/results - Get simulation results",
            "GET /api/sessions - Get all sessions"
        ]
    }

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "fantasy-crypto-api"}

# Run configuration for development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=6000,
        reload=True,
        log_level=Config.LOG_LEVEL.lower()
    )