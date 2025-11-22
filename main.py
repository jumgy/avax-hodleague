# main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import Config


# Startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logging.info("🚀 Hodleague starting up...")
    yield
    # Shutdown
    logging.info("🛑 Hodleague shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Hodleague API",
    description="API for fantasy cryptocurrency trading game",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/admin/api-docs",          # вместо /docs
    redoc_url="/admin/redoc",            # вместо /redoc  
    openapi_url="/admin/openapi.json"    # вместо /openapi.json
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "docs": "/admin/api-docs",
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


# Import and register API routes
from api.routes import router as api_router
app.include_router(api_router, prefix="/api")


# Run configuration for development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=Config.LOG_LEVEL.lower()
    )