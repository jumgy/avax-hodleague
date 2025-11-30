# api/routes/admin/tokens.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator
from datetime import datetime

from models.database import get_sync_db
from models.token_models import Token
from .auth import verify_admin_token
from services.scheduler_service import scheduler_service

# Pydantic models
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
    
    class Config:
        from_attributes = True

# Router
router = APIRouter(prefix="/panel/tokens")

@router.get("/", response_model=List[TokenResponse])
async def get_all_tokens(
    active_only: bool = Query(False, description="Filter only active tokens"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get all tokens for panel"""
    query = db.query(Token)
    if active_only:
        query = query.filter(Token.is_active == True)
    
    tokens = query.order_by(Token.weight.desc()).all()
    return tokens

@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get specific token by ID"""
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
    """Create new token"""
    # Check if symbol already exists
    existing = db.query(Token).filter(Token.symbol == token_data.symbol).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Token with symbol '{token_data.symbol}' already exists"
        )
    
    # Create new token
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
    """Update existing token"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Check symbol uniqueness if being updated
    if token_data.symbol and token_data.symbol != token.symbol:
        existing = db.query(Token).filter(Token.symbol == token_data.symbol).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Token with symbol '{token_data.symbol}' already exists"
            )
    
    # Update fields
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
    """Delete token and all related cards (soft delete by setting is_active=False)"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Deactivate token
    token.is_active = False
    token.updated_at = datetime.utcnow()
    
    #Деактивируем все карточки связанные с этим токеном
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
    """Get price monitoring scheduler status (Admin only)"""
    return scheduler_service.get_status()

@router.post("/scheduler/trigger", tags=["Scheduler Management"])
async def trigger_price_monitoring(
    admin: dict = Depends(verify_admin_token)
):
    """Manually trigger price monitoring (Admin only)"""
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