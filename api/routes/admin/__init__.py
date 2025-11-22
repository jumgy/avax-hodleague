from fastapi import APIRouter
from .auth import router as auth_router

# Create admin router that combines all admin modules
admin_router = APIRouter()

# Include all admin route modules  
admin_router.include_router(auth_router, tags=["Admin Auth"])

# Export router
__all__ = ["admin_router"]