# api/routes/admin/__init__.py
from fastapi import APIRouter
from .auth import router as auth_router
from .tokens import router as tokens_router
from .cards import router as cards_router
from .rarities import router as rarities_router
from .pack_types import router as pack_types_router
from .drop_rates import router as drop_rates_router
from .tournaments import router as tournaments_router
from .prizes import router as prizes_router
from .users import router as users_router 
from .user_cards import router as user_cards_router
from .user_packs import router as user_packs_router
from .tournament_details import router as tournament_details_router
from .reward import router as reward_router


# Create admin router
admin_router = APIRouter()

# Include all admin route modules с отдельными тегами
admin_router.include_router(auth_router, tags=["Admin - Auth"])
admin_router.include_router(tokens_router, tags=["Admin - Tokens"])
admin_router.include_router(cards_router, tags=["Admin - Cards"])
admin_router.include_router(rarities_router, tags=["Admin - Rarities"])
admin_router.include_router(reward_router, tags=["Admin - Rewards"])
admin_router.include_router(pack_types_router, tags=["Admin - Pack types"])
admin_router.include_router(drop_rates_router, tags=["Admin - Drop rates"])
admin_router.include_router(tournaments_router, tags=["Admin - Tournaments"])
admin_router.include_router(tournament_details_router, tags=["Admin - Tournament details"])
admin_router.include_router(prizes_router, tags=["Admin - Prizes"])

admin_router.include_router(users_router, tags=["Admin - Users"])
admin_router.include_router(user_cards_router, tags=["Admin - User Cards"])
admin_router.include_router(user_packs_router, tags=["Admin - User Packs"])


# Export router
__all__ = ["admin_router"]