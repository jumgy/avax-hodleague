# api/routes/packs.py

from fastapi import APIRouter, HTTPException, Request, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from models.database import get_async_db
from models.pack_models import PackType
from services.pack_opening_service import pack_opening_service
from api.routes.auth import verify_jwt_dependency
from utils.rate_limit import limiter
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ==================== Pydantic Schemas ====================

class PackTypeDetail(BaseModel):
    pack_type_id: int
    name: str
    description: str
    image_url: str
    header_image_url: str
    cards_per_pack: int
    price: float
    currency: str
    supply: Optional[int]
    available_from: Optional[str]
    available_until: Optional[str]
    is_active: bool
    count: int  # Количество у пользователя

class AvailablePacksResponse(BaseModel):
    available_packs: int
    pack_types: List[PackTypeDetail]

class OpenPackRequest(BaseModel):
    pack_type_id: Optional[int] = None

class CardReceived(BaseModel):
    user_card_id: int
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    rarity_name: str
    rarity_color: str
    design_type: str
    rendered_image_url: str

class OpenPackResponse(BaseModel):
    pack_opening_id: int
    pack_type_name: str
    opened_at: str
    cards_received: List[CardReceived]

class PackHistoryItem(BaseModel):
    pack_opening_id: int
    pack_type_name: str
    opened_at: str
    cards_count: int
    cards_received: List[CardReceived]

class PackHistoryResponse(BaseModel):
    total: int
    openings: List[PackHistoryItem]

# ==================== Routes ====================

@router.get(
    "/packs/available",
    response_model=AvailablePacksResponse,
    summary="Get available packs",
    description="Get number of unopened packs for authenticated user with full pack details"
)
async def get_available_packs(
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get available packs for current user with full pack type information
    Requires JWT authentication
    """
    try:
        user_id = current_user["user_id"]
        
        # Get pack counts
        availability = await pack_opening_service.check_pack_availability(
            user_id=user_id,
            pack_type_id=None,
            db=db
        )
        
        # Get full pack type details
        pack_type_ids = list(availability["by_type"].keys())
        
        if not pack_type_ids:
            return AvailablePacksResponse(
                available_packs=0,
                pack_types=[]
            )
        
        # Fetch pack types from DB
        result = await db.execute(
            select(PackType).where(
                PackType.id.in_(pack_type_ids),
                PackType.is_active == True
            )
        )
        pack_types = result.scalars().all()
        
        # Build response with full details
        pack_details = []
        for pack_type in pack_types:
            count = availability["by_type"].get(pack_type.id, 0)
            
            pack_details.append(PackTypeDetail(
                pack_type_id=pack_type.id,
                name=pack_type.name,
                description=pack_type.description,
                image_url=pack_type.image_url,
                header_image_url=pack_type.header_image_url,
                cards_per_pack=pack_type.cards_per_pack,
                price=float(pack_type.price),
                currency=pack_type.currency,
                supply=pack_type.supply,
                available_from=pack_type.available_from.isoformat() if pack_type.available_from else None,
                available_until=pack_type.available_until.isoformat() if pack_type.available_until else None,
                is_active=pack_type.is_active,
                count=count
            ))
        
        # Sort by pack_type_id
        pack_details.sort(key=lambda x: x.pack_type_id)
        
        return AvailablePacksResponse(
            available_packs=availability["total"],
            pack_types=pack_details
        )
        
    except Exception as e:
        logger.error(f"Error getting available packs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available packs"
        )


@router.post(
    "/packs/open",
    response_model=OpenPackResponse,
    summary="Open a pack",
    description="Open an unopened pack and receive cards",
)
@limiter.limit("30/minute")
async def open_pack(
    request: Request,
    body: OpenPackRequest,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Open a pack and receive cards
    Requires JWT authentication
    
    - **pack_type_id**: Optional specific pack type to open (if None, opens first available)
    """
    try:
        user_id = current_user["user_id"]
        
        result = await pack_opening_service.open_pack(
            user_id=user_id,
            pack_type_id=body.pack_type_id,
            db=db
        )
        
        await db.commit()
        
        return OpenPackResponse(**result)
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error opening pack: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to open pack"
        )
    
@router.get(
    "/packs/openings/{pack_opening_id}",
    response_model=OpenPackResponse,
    summary="Get specific pack opening",
    description="Get details of a specific pack opening by ID"
)
async def get_pack_opening(
    pack_opening_id: int,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get specific pack opening details with cards received
    Requires JWT authentication
    - **pack_opening_id**: ID of the pack opening to retrieve
    """
    try:
        user_id = current_user["user_id"]
        
        result = await pack_opening_service.get_pack_opening_by_id(
            pack_opening_id=pack_opening_id,
            user_id=user_id,
            db=db
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pack opening not found or access denied"
            )
        
        return OpenPackResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pack opening {pack_opening_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pack opening"
        )


@router.get(
    "/packs/history",
    response_model=PackHistoryResponse,
    summary="Get pack opening history",
    description="Get history of all opened packs for authenticated user with cards received"
)
async def get_pack_history(
    limit: int = Query(20, ge=1, le=100, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get pack opening history
    Requires JWT authentication
    
    - **limit**: Number of records (1-100)
    - **offset**: Pagination offset
    """
    try:
        user_id = current_user["user_id"]
        
        history = await pack_opening_service.get_pack_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            db=db
        )
        
        return PackHistoryResponse(**history)
        
    except Exception as e:
        logger.error(f"Error getting pack history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pack history"
        )