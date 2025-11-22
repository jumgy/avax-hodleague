# api/routes/__init__.py
from fastapi import APIRouter
from .tokens import router as tokens_router
from .sessions import router as sessions_router
from .tournaments import router as tournaments_router
from .admin import admin_router

# Create main router that combines all route modules
router = APIRouter()

# Include all route modules
router.include_router(tokens_router, tags=["Tokens"])
router.include_router(sessions_router, tags=["Sessions"])  
router.include_router(tournaments_router, tags=["Tournaments"])

# Include admin routes
router.include_router(admin_router, tags=["Administration"])

# Export router for main.py
__all__ = ["router"]