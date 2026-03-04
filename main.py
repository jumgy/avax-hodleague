# main.py

import logging
import sys
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.routes import router as api_router
from api.routes.nft import router as nft_router
from utils.rate_limit import limiter
from api.routes.admin import admin_router

from services.scheduler_service import scheduler_service

from config import Config
from models.database import init_database, close_database

_logging_configured = False
def setup_logging():
    """Configure logging without duplication."""
    global _logging_configured
    if _logging_configured:
        return

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    log_level = getattr(logging, Config.LOG_LEVEL, logging.INFO)
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Dedicated log files for health checks (packs and cards).
    logs_dir = Path("logs")
    try:
        logs_dir.mkdir(exist_ok=True)
    except Exception:
        # If directory cannot be created, fail silently and keep console logs only.
        logs_dir = None

    if logs_dir is not None:
        pack_logger = logging.getLogger("pack_health")
        pack_logger.setLevel(logging.WARNING)
        pack_file_handler = logging.FileHandler(logs_dir / "pack_health.log", encoding="utf-8")
        pack_file_handler.setLevel(logging.WARNING)
        pack_file_handler.setFormatter(formatter)
        pack_logger.addHandler(pack_file_handler)

        card_logger = logging.getLogger("card_health")
        card_logger.setLevel(logging.WARNING)
        card_file_handler = logging.FileHandler(logs_dir / "card_health.log", encoding="utf-8")
        card_file_handler.setLevel(logging.WARNING)
        card_file_handler.setFormatter(formatter)
        card_logger.addHandler(card_file_handler)

    # Disable SQLAlchemy logs when DB_ECHO=False.
    if not Config.DB_ECHO:
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)
    
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)

    # Clear uvicorn handlers and set propagation.
    for logger_name in ['uvicorn', 'uvicorn.access', 'uvicorn.error']:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    
    _logging_configured = True

setup_logging()
logger = logging.getLogger(__name__)

# Startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    # STARTUP
    logger.info("Hodleague starting up...")

    try:
        await init_database()
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error("Database initialization failed: %s", e, exc_info=True)

    try:
        await scheduler_service.start()
        logger.info("Price monitoring scheduler started")
    except Exception as e:
        logger.error("Failed to start scheduler: %s", e, exc_info=True)

    logger.info("Application startup complete")
    
    yield

    # SHUTDOWN
    logger.info("Hodleague shutting down...")

    try:
        await scheduler_service.stop()
        logger.info("Price monitoring scheduler stopped")
    except Exception as e:
        logger.error("Error stopping scheduler: %s", e, exc_info=True)

    try:
        await close_database()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error("Error closing database: %s", e, exc_info=True)

    logger.info("Application shutdown complete")


security = HTTPBasic()
def verify_swagger_access(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify Swagger access in production."""
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"), 
        Config.SWAGGER_USERNAME.encode("utf8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        Config.SWAGGER_PASSWORD.encode("utf8")
    )
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True
def get_swagger_dependency():
    """Return dependency based on environment (auth required in production only)."""
    if Config.ENVIRONMENT == "production":
        return Depends(verify_swagger_access)
    return None


app = FastAPI(
    title="Hodleague API",
    description="API for fantasy cryptocurrency trading game", 
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routers
app.include_router(api_router, prefix="/api")
app.include_router(nft_router)  # /nft/cards/{id} for ERC-721 tokenURI
app.include_router(admin_router)

# ============ PROTECTED DOCS ENDPOINTS ============

@limiter.exempt
@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(authorized: bool = get_swagger_dependency()):
    """Protected OpenAPI schema"""
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
@limiter.exempt
@app.get("/swagger", include_in_schema=False)
async def get_swagger_documentation(authorized: bool = get_swagger_dependency()):
    """Protected Swagger UI"""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - Swagger UI"
    )
@limiter.exempt
@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(authorized: bool = get_swagger_dependency()):
    """Protected ReDoc UI"""
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - ReDoc"
    )

from fastapi.responses import HTMLResponse
from pathlib import Path

@limiter.exempt
@app.get("/panel/bulk-upload", response_class=HTMLResponse)
async def bulk_upload_page(authorized: bool = get_swagger_dependency()):
    """Bulk template upload page."""
    html_path = Path(__file__).parent / "static" / "bulk_upload.html"
    if html_path.exists():
        return html_path.read_text(encoding='utf-8')
    raise HTTPException(404, "Page not found")
# ============ MAIN ENDPOINTS ============

# Health check endpoint (exempt: load balancers / k8s probe)
@limiter.exempt
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    from models.database import check_database_connection, get_database_info
    
    db_healthy = await check_database_connection()
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
