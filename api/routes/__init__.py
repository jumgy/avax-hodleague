# api/routes/__init__.py
from fastapi import APIRouter
from .tournaments import router as tournaments_router
from .auth import router as auth_router
from .users import router as users_router
from .cards import router as cards_router
from .packs import router as packs_router
from .tokens import router as tokens_router
from .alpha_test import router as alpha_test_router

# Create main router that combines all route modules
router = APIRouter()

# PUBLIC API - для игроков
router.include_router(auth_router, tags=["Game - Auth"])
router.include_router(alpha_test_router, tags=["Game - Alpha Test"])
router.include_router(tournaments_router, tags=["Game - Tournaments"])
router.include_router(packs_router, tags=["Game - Packs"])
router.include_router(users_router, tags=["Game - Users"])
router.include_router(cards_router, tags=["Game - Cards"])
router.include_router(tokens_router, tags=["Game - Tokens"])



# Export router for main.py
__all__ = ["router"]