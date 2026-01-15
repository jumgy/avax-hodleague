# api/routes/users.py

from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from models.database import get_async_db
from services.user_profile_service import user_profile_service
from api.routes.auth import verify_jwt_dependency
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class UserStats(BaseModel):
    total_cards: int
    tournaments_participated: int
    best_position: Optional[int]
    best_score: Optional[float]
    balances: Dict[str, float]

class UserCard(BaseModel):
    user_card_id: int
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    token_weight: int
    rarity_name: str
    rarity_color: str
    design_type: str
    rendered_image_url: str
    calculated_score: float
    current_price: Optional[float]
    market_cap: Optional[int]
    tournament_change: Optional[float]
    obtained_at: Optional[str]
    status: str

class UserProfileResponse(BaseModel):
    user_id: int
    wallet_address: str
    nickname: str
    avatar_url: str
    referral_route: str
    created_at: str
    stats: UserStats
    cards: Optional[List[UserCard]] = None


@router.get(
    "/users/me",
    response_model=UserProfileResponse,
    summary="Get my profile",
    description="Get authenticated user's profile. Requires JWT token. Use ?include_cards=true to include card collection."
)
async def get_my_profile(
    include_cards: bool = Query(False, description="Include user's card collection"),
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get authenticated user's own profile
    
    - **include_cards**: Optional flag to include cards collection
    - Requires JWT authentication
    """
    try:
        wallet_address = current_user["wallet_address"]
        
        # Find user
        user = await user_profile_service.get_user_by_wallet(wallet_address, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get user stats
        stats = await user_profile_service.get_user_stats(user.id, db)
        
        # Prepare response
        response_data = {
            "user_id": user.id,
            "wallet_address": user.wallet_address,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "referral_route": user.referral_route,
            "created_at": user.created_at.isoformat(),
            "stats": stats
        }
        
        # Include cards if requested
        if include_cards:
            cards = await user_profile_service.get_user_cards(user.id, db)
            response_data["cards"] = cards
        
        return UserProfileResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile for authenticated user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile"
        )


@router.get(
    "/users/{wallet_address}",
    response_model=UserProfileResponse,
    summary="Get user profile",
    description="Get public user profile by wallet address. Use ?include_cards=true to include user's card collection."
)
async def get_user_profile(
    wallet_address: str,
    include_cards: bool = Query(False, description="Include user's card collection"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user public profile by wallet address
    - **wallet_address**: Ethereum wallet address (0x...)
    - **include_cards**: Optional flag to include user's cards collection
    """
    try:
        # Find user
        user = await user_profile_service.get_user_by_wallet(wallet_address, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with wallet address {wallet_address} not found"
            )
        
        # Get user stats
        stats = await user_profile_service.get_user_stats(user.id, db)
        
        # Prepare response
        response_data = {
            "user_id": user.id,
            "wallet_address": user.wallet_address,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "referral_route": user.referral_route,
            "created_at": user.created_at.isoformat(),
            "stats": stats
        }
        
        # Include cards if requested
        if include_cards:
            cards = await user_profile_service.get_user_cards(user.id, db)
            response_data["cards"] = cards
        
        return UserProfileResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user profile for {wallet_address}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )