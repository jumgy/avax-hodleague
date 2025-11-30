# api/routes/admin/__init__.py
from fastapi import APIRouter
from .auth import router as auth_router
from .tokens import router as tokens_router
from .cards import router as cards_router
from .tournaments import router as tournaments_router
from .users import router as users_router 

# Create admin router
admin_router = APIRouter()

# Include all admin route modules с отдельными тегами
admin_router.include_router(auth_router, tags=["Admin - Auth"])
admin_router.include_router(tokens_router, tags=["Admin - Tokens"])
admin_router.include_router(cards_router, tags=["Admin - Cards"])
admin_router.include_router(tournaments_router, tags=["Admin - Tournaments"])
admin_router.include_router(users_router, tags=["Admin - Users"])

# Export router
__all__ = ["admin_router"]