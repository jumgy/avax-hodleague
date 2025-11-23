# api/routes/admin/cards.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator
from datetime import datetime

from models.database import get_sync_db
from models.card_models import Card
from models.token_models import Token
from .auth import verify_admin_token

# Допустимые значения
VALID_RARITIES = ["common", "rare", "epic", "legendary"]
VALID_DESIGN_TYPES = ["classic", "neon", "retro", "galaxy", "minimalist", "cyberpunk"]

# Pydantic models
class CardCreate(BaseModel):
    token_id: int
    rarity: str
    design_type: str
    background_image_url: str
    is_active: bool = True
    
    @validator('token_id')
    def validate_token_id(cls, v):
        if v is None or v <= 0:
            raise ValueError('Token ID is required and must be positive')
        return v
    
    @validator('rarity')
    def validate_rarity(cls, v):
        if not v or not v.strip():
            raise ValueError('Rarity is required')
        v = v.strip().lower()
        if v not in VALID_RARITIES:
            raise ValueError(f'Rarity must be one of: {", ".join(VALID_RARITIES)}')
        return v
    
    @validator('design_type')
    def validate_design_type(cls, v):
        if not v or not v.strip():
            raise ValueError('Design type is required')
        v = v.strip().lower()
        if v not in VALID_DESIGN_TYPES:
            raise ValueError(f'Design type must be one of: {", ".join(VALID_DESIGN_TYPES)}')
        return v
    
    @validator('background_image_url')
    def validate_background_image_url(cls, v):
        if not v or not v.strip():
            raise ValueError('Background image URL is required')
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Background image URL must start with http:// or https://')
        return v

class CardUpdate(BaseModel):
    token_id: Optional[int] = None
    rarity: Optional[str] = None
    design_type: Optional[str] = None
    background_image_url: Optional[str] = None
    is_active: Optional[bool] = None
    
    @validator('token_id')
    def validate_token_id(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Token ID must be positive')
        return v
    
    @validator('rarity')
    def validate_rarity(cls, v):
        if v is not None:
            v = v.strip().lower()
            if v not in VALID_RARITIES:
                raise ValueError(f'Rarity must be one of: {", ".join(VALID_RARITIES)}')
            return v
        return v
    
    @validator('design_type')
    def validate_design_type(cls, v):
        if v is not None:
            v = v.strip().lower()
            if v not in VALID_DESIGN_TYPES:
                raise ValueError(f'Design type must be one of: {", ".join(VALID_DESIGN_TYPES)}')
            return v
        return v
    
    @validator('background_image_url')
    def validate_background_image_url(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Background image URL cannot be empty')
            v = v.strip()
            if not v.startswith(('http://', 'https://')):
                raise ValueError('Background image URL must start with http:// or https://')
            return v
        return v

class CardResponse(BaseModel):
    id: int
    token_id: int
    rarity: str
    design_type: str
    background_image_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Добавляем инфо о токене
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    
    class Config:
        from_attributes = True

# Router
router = APIRouter(prefix="/management/cards", tags=["Admin - Cards"])

@router.get("/", response_model=List[CardResponse])
async def get_all_cards(
    active_only: bool = Query(False, description="Filter only active cards"),
    token_id: Optional[int] = Query(None, description="Filter by specific token"),
    rarity: Optional[str] = Query(None, description="Filter by rarity"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get all cards for management"""
    query = db.query(Card).join(Token)  # Join для получения инфо о токене
    
    if active_only:
        query = query.filter(Card.is_active == True)
    
    if token_id:
        query = query.filter(Card.token_id == token_id)
    
    if rarity:
        query = query.filter(Card.rarity == rarity.lower())
    
    cards = query.order_by(Card.created_at.desc()).all()
    
    # Добавляем инфо о токенах
    result = []
    for card in cards:
        token = db.query(Token).filter(Token.id == card.token_id).first()
        card_data = CardResponse.from_orm(card)
        if token:
            card_data.token_name = token.name
            card_data.token_symbol = token.symbol
        result.append(card_data)
    
    return result

@router.get("/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get specific card by ID"""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # Добавляем инфо о токене
    token = db.query(Token).filter(Token.id == card.token_id).first()
    card_data = CardResponse.from_orm(card)
    if token:
        card_data.token_name = token.name
        card_data.token_symbol = token.symbol
    
    return card_data

@router.post("/", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(
    card_data: CardCreate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Create new card"""
    # Проверяем что токен существует
    token = db.query(Token).filter(Token.id == card_data.token_id).first()
    if not token:
        raise HTTPException(
            status_code=400,
            detail=f"Token with ID {card_data.token_id} not found"
        )
    
    # Создаем карточку
    new_card = Card(**card_data.dict())
    db.add(new_card)
    db.commit()
    db.refresh(new_card)
    
    # Добавляем инфо о токене в ответ
    card_response = CardResponse.from_orm(new_card)
    card_response.token_name = token.name
    card_response.token_symbol = token.symbol
    
    return card_response

@router.put("/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: int,
    card_data: CardUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Update existing card"""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # Проверяем токен если он обновляется
    if card_data.token_id and card_data.token_id != card.token_id:
        token = db.query(Token).filter(Token.id == card_data.token_id).first()
        if not token:
            raise HTTPException(
                status_code=400,
                detail=f"Token with ID {card_data.token_id} not found"
            )
    
    # Обновляем поля
    update_data = card_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(card, field, value)
    
    card.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(card)
    
    # Добавляем инфо о токене
    token = db.query(Token).filter(Token.id == card.token_id).first()
    card_response = CardResponse.from_orm(card)
    if token:
        card_response.token_name = token.name
        card_response.token_symbol = token.symbol
    
    return card_response

@router.delete("/{card_id}")
async def delete_card(
    card_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Delete card (soft delete by setting is_active=False)"""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # Soft delete
    card.is_active = False
    card.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Card ID {card_id} has been deactivated", "success": True}

@router.post("/{card_id}/activate")
async def activate_card(
    card_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Activate deactivated card"""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    card.is_active = True
    card.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Card ID {card_id} has been activated", "success": True}

@router.get("/reference/options")
async def get_card_options(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get available options for card creation"""
    # Получаем список активных токенов
    tokens = db.query(Token).filter(Token.is_active == True).all()
    
    return {
        "rarities": VALID_RARITIES,
        "design_types": VALID_DESIGN_TYPES,
        "available_tokens": [
            {"id": t.id, "name": t.name, "symbol": t.symbol}
            for t in tokens
        ]
    }