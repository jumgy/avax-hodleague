# api/routes/__init__.py
from fastapi import APIRouter
from .tokens import router as tokens_router
from .sessions import router as sessions_router
from .tournaments import router as tournaments_router
from .admin import admin_router

# Create main router that combines all route modules
router = APIRouter()

# PUBLIC API - для игроков
router.include_router(tokens_router, tags=["Game - Tokens"])
router.include_router(sessions_router, tags=["Game - Sessions"])  
router.include_router(tournaments_router, tags=["Game - Tournaments"])

# ADMIN API - теги уже внутри admin_router
router.include_router(admin_router)

# Export router for main.py
__all__ = ["router"]