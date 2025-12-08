from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime
import re

from models.database import get_sync_db
from models.token_models import Token
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

router = APIRouter(prefix="/panel/tokens")

@router.get("/", response_model=PaginatedTokenResponse)
async def get_all_tokens(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    active_only: Optional[bool] = Query(None, description="Filter only active tokens"),
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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    query = db.query(Token)

    if id is not None:
        query = query.filter(Token.id == id)
    if active_only is True:
        query = query.filter(Token.is_active == True)
    elif active_only is False:
        query = query.filter(Token.is_active == False)
    if name:
        query = query.filter(Token.name.ilike(f"%{name}%"))
    if symbol:
        query = query.filter(Token.symbol.ilike(symbol.upper()))
    if weight_from is not None:
        query = query.filter(Token.weight >= weight_from)
    if weight_to is not None:
        query = query.filter(Token.weight <= weight_to)
    if created_from:
        query = query.filter(Token.created_at >= created_from)
    if created_to:
        query = query.filter(Token.created_at <= created_to)
    if updated_from:
        query = query.filter(Token.updated_at >= updated_from)
    if updated_to:
        query = query.filter(Token.updated_at <= updated_to)

    total = query.count()

    sort_column = getattr(Token, sort_by)
    query = query.order_by(sort_column.desc()) if sort_order == "desc" else query.order_by(sort_column.asc())

    tokens = query.offset(skip).limit(limit).all()

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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token

@router.post("/", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    token_data: TokenCreate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    existing = db.query(Token).filter(Token.symbol == token_data.symbol).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Token with symbol '{token_data.symbol}' already exists"
        )

    new_token = Token(**token_data.dict())
    db.add(new_token)
    db.commit()
    db.refresh(new_token)
    return new_token

@router.put("/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: int,
    token_data: TokenUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    if token_data.symbol and token_data.symbol != token.symbol:
        existing = db.query(Token).filter(Token.symbol == token_data.symbol).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Token with symbol '{token_data.symbol}' already exists"
            )

    update_data = token_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(token, field, value)

    token.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(token)
    return token

@router.delete("/{token_id}")
async def delete_token(
    token_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    token.is_active = False
    token.updated_at = datetime.utcnow()

    from models.card_models import Card
    affected_cards = db.query(Card).filter(
        Card.token_id == token_id,
        Card.is_active == True
    ).all()

    for card in affected_cards:
        card.is_active = False
        card.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": f"Token ID {token_id} has been deactivated",
        "deactivated_cards": len(affected_cards),
        "success": True
    }

@router.get("/scheduler/status", tags=["Scheduler Management"])
async def get_scheduler_status(
    admin: dict = Depends(verify_admin_token)
):
    return scheduler_service.get_status()

@router.post("/scheduler/trigger", tags=["Scheduler Management"])
async def trigger_price_monitoring(
    admin: dict = Depends(verify_admin_token)
):
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