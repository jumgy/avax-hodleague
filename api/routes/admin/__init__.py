# api/routes/admin/__init__.py
from fastapi import APIRouter
from .auth import router as auth_router
from .tokens import router as tokens_router
from .cards import router as cards_router

# Create admin router
admin_router = APIRouter()

# Include all admin route modules с отдельными тегами
admin_router.include_router(auth_router, tags=["Admin - Auth"])
admin_router.include_router(tokens_router, tags=["Admin - Tokens"])
admin_router.include_router(cards_router, tags=["Admin - Cards"])

# Export router
__all__ = ["admin_router"]