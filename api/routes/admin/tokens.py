from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime
import re

from models.database import get_async_db
from models.token_models import Token, TokenPrice
from .auth import verify_admin_token
from services.scheduler_service import scheduler_service

class TokenCreate(BaseModel):
    name: str
    symbol: str
    weight: int
    image_url: str
    is_active: bool = True

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Token name is required')
        if len(v.strip()) < 2:
            raise ValueError('Token name must be at least 2 characters')
        return v.strip()

    @validator('symbol')
    def validate_symbol(cls, v):
        if not v or not v.strip():
            raise ValueError('Token symbol is required')
        v = v.strip().upper()
        if len(v) < 1 or len(v) > 20:
            raise ValueError('Symbol must be between 1 and 20 characters')
        return v

    @validator('weight')
    def validate_weight(cls, v):
        if v is None:
            raise ValueError('Weight is required')
        if not 1 <= v <= 10:
            raise ValueError('Weight must be between 1 and 10')
        return v

    @validator('image_url')
    def validate_image_url(cls, v):
        if not v or not v.strip():
            raise ValueError('Image URL is required')
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Image URL must start with http:// or https://')
        return v

class TokenUpdate(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    weight: Optional[int] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Token name cannot be empty')
            if len(v.strip()) < 2:
                raise ValueError('Token name must be at least 2 characters')
            return v.strip()
        return v

    @validator('symbol')
    def validate_symbol(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Token symbol cannot be empty')
            v = v.strip().upper()
            if len(v) < 1 or len(v) > 20:
                raise ValueError('Symbol must be between 1 and 20 characters')
            return v
        return v

    @validator('weight')
    def validate_weight(cls, v):
        if v is not None and not 1 <= v <= 10:
            raise ValueError('Weight must be between 1 and 10')
        return v

    @validator('image_url')
    def validate_image_url(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Image URL cannot be empty')
            v = v.strip()
            if not v.startswith(('http://', 'https://')):
                raise ValueError('Image URL must start with http:// or https://')
            return v
        return v

class TokenResponse(BaseModel):
    id: int
    name: str
    symbol: str
    weight: int
    image_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedTokenResponse(BaseModel):
    items: List[TokenResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

class TokenPriceResponse(BaseModel):
    id: int
    token_id: int
    price: float
    market_cap: Optional[int] = None
    change_24h: Optional[float] = None
    sources_count: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedTokenPriceResponse(BaseModel):
    items: List[TokenPriceResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/panel/tokens")

@router.get("/", response_model=PaginatedTokenResponse)
async def get_all_tokens(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None, description="Filter by active status (true=active, false=inactive, null=all)"),
    name: Optional[str] = Query(None, description="Search by name"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    weight_from: Optional[int] = Query(None),
    weight_to: Optional[int] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    updated_from: Optional[datetime] = Query(None),
    updated_to: Optional[datetime] = Query(None),
    sort_by: str = Query("weight", regex="^(id|name|symbol|weight|image_url|is_active|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Get all tokens with filtering, sorting and pagination.
    """
    
    query = select(Token)

    # Apply filters
    if id is not None:
        query = query.where(Token.id == id)
    
    if is_active is not None:
        query = query.where(Token.is_active == is_active)
    
    if name:
        query = query.where(Token.name.ilike(f"%{name}%"))
    
    if symbol:
        query = query.where(Token.symbol.ilike(symbol.upper()))
    
    if weight_from is not None:
        query = query.where(Token.weight >= weight_from)
    
    if weight_to is not None:
        query = query.where(Token.weight <= weight_to)
    
    if created_from:
        query = query.where(Token.created_at >= created_from)
    
    if created_to:
        query = query.where(Token.created_at <= created_to)
    
    if updated_from:
        query = query.where(Token.updated_at >= updated_from)
    
    if updated_to:
        query = query.where(Token.updated_at <= updated_to)
    
    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply sort
    sort_column = getattr(Token, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Paginate and execute
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    tokens = result.scalars().all()
    
    return PaginatedTokenResponse(
        items=tokens,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get token by ID."""
    
    query = select(Token).where(Token.id == token_id)
    result = await db.execute(query)
    token = result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    return token

@router.get("/{token_id}/prices", response_model=PaginatedTokenPriceResponse)
async def get_token_prices(
    token_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    price_from: Optional[float] = Query(None, ge=0),
    price_to: Optional[float] = Query(None, ge=0),
    timestamp_from: Optional[datetime] = Query(None),
    timestamp_to: Optional[datetime] = Query(None),
    sort_by: str = Query("timestamp", regex="^(id|price|market_cap|change_24h|timestamp)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get token price history."""
    
    # Ensure token exists
    token_query = select(Token).where(Token.id == token_id)
    token_result = await db.execute(token_query)
    token = token_result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Base price query
    query = select(TokenPrice).where(TokenPrice.token_id == token_id)
    
    # Apply filters
    if price_from is not None:
        query = query.where(TokenPrice.price >= price_from)
    
    if price_to is not None:
        query = query.where(TokenPrice.price <= price_to)
    
    if timestamp_from:
        query = query.where(TokenPrice.timestamp >= timestamp_from)
    
    if timestamp_to:
        query = query.where(TokenPrice.timestamp <= timestamp_to)
    
    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply sort
    sort_column = getattr(TokenPrice, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Paginate and execute
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    prices = result.scalars().all()
    
    return PaginatedTokenPriceResponse(
        items=prices,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.post("/", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    token_data: TokenCreate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Create new token with symbol uniqueness check."""
    
    # Check symbol uniqueness
    existing_query = select(Token).where(Token.symbol == token_data.symbol)
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Token with symbol '{token_data.symbol}' already exists"
        )
    
    try:
        # Create token
        new_token = Token(**token_data.dict())
        
        db.add(new_token)
        await db.flush()
        await db.refresh(new_token)
        
        return new_token
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create token: {str(e)}"
        )

@router.put("/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: int,
    token_data: TokenUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Update existing token with constraint checks."""
    
    # Load existing token
    query = select(Token).where(Token.id == token_id)
    result = await db.execute(query)
    token = result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Check symbol uniqueness if changed
    if token_data.symbol and token_data.symbol != token.symbol:
        existing_query = select(Token).where(Token.symbol == token_data.symbol)
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Token with symbol '{token_data.symbol}' already exists"
            )
    
    try:
        # Apply updates
        update_data = token_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(token, field, value)
        
        token.updated_at = datetime.utcnow()
        
        await db.flush()
        await db.refresh(token)
        
        return token
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update token: {str(e)}"
        )

@router.delete("/{token_id}")
async def delete_token(
    token_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Deactivate token and related cards."""
    
    # Load token
    token_query = select(Token).where(Token.id == token_id)
    token_result = await db.execute(token_query)
    token = token_result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    try:
        # Deactivate token
        token.is_active = False
        token.updated_at = datetime.utcnow()
        
        # Deactivate all related active cards
        from models.card_models import Card
        
        affected_cards_query = select(Card).where(
            Card.token_id == token_id,
            Card.is_active == True
        )
        affected_cards_result = await db.execute(affected_cards_query)
        affected_cards = affected_cards_result.scalars().all()
        
        for card in affected_cards:
            card.is_active = False
            card.updated_at = datetime.utcnow()
        
        await db.flush()
        
        return {
            "message": f"Token ID {token_id} has been deactivated",
            "deactivated_cards": len(affected_cards),
            "success": True
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete token: {str(e)}"
        )

@router.get("/scheduler/status", tags=["Scheduler Management"])
async def get_scheduler_status(
    admin: dict = Depends(verify_admin_token)
):
    """Get price monitoring scheduler status."""
    return scheduler_service.get_status()

@router.post("/scheduler/trigger", tags=["Scheduler Management"])
async def trigger_price_monitoring(
    admin: dict = Depends(verify_admin_token)
):
    """Manually trigger token price monitoring."""
    try:
        await scheduler_service.run_price_monitor_now()
        return {
            "message": "Price monitoring triggered successfully",
            "status": "completed",
            "triggered_by": admin.get("username", "admin")
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger price monitoring: {str(e)}"
        )