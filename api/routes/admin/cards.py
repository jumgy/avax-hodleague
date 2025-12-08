from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from typing import List, Optional
from pydantic import BaseModel, validator
from datetime import datetime

from models.database import get_sync_db
from models.card_models import Card
from models.token_models import Token
from models.rarity_models import Rarity
from .auth import verify_admin_token

VALID_DESIGN_TYPES = ["classic", "neon", "retro", "galaxy", "minimalist", "cyberpunk"]

class CardCreate(BaseModel):
    token_id: int
    rarity_id: int
    design_type: str
    background_image_url: str
    is_active: bool = True

    @validator('token_id')
    def validate_token_id(cls, v):
        if v is None or v <= 0:
            raise ValueError('Token ID is required and must be positive')
        return v

    @validator('rarity_id')
    def validate_rarity_id(cls, v):
        if v is None or v <= 0:
            raise ValueError('Rarity ID is required and must be positive')
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
    rarity_id: Optional[int] = None
    design_type: Optional[str] = None
    background_image_url: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('token_id')
    def validate_token_id(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Token ID must be positive')
        return v

    @validator('rarity_id')
    def validate_rarity_id(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Rarity ID must be positive')
        return v

    @validator('design_type')
    def validate_design_type(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Design type cannot be empty')
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
    rarity_id: int
    design_type: str
    background_image_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    rarity_name: Optional[str] = None
    rarity_color: Optional[str] = None

    class Config:
        from_attributes = True

class PaginatedCardsResponse(BaseModel):
    items: List[CardResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/management/cards", tags=["Admin - Cards"])

@router.get("/", response_model=PaginatedCardsResponse)
async def get_all_cards(
    # Пагинация
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    
    # Фильтрация по основным полям
    id: Optional[int] = Query(None, description="Filter by card ID"),
    token_id: Optional[int] = Query(None, description="Filter by token ID"),
    rarity_id: Optional[int] = Query(None, description="Filter by rarity ID"),
    design_type: Optional[str] = Query(None, description="Filter by design type (partial match)"),
    background_image_url: Optional[str] = Query(None, description="Filter by background image URL (partial match)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    
    # Диапазоны дат
    created_from: Optional[datetime] = Query(None, description="Filter cards created after this date"),
    created_to: Optional[datetime] = Query(None, description="Filter cards created before this date"),
    updated_from: Optional[datetime] = Query(None, description="Filter cards updated after this date"),
    updated_to: Optional[datetime] = Query(None, description="Filter cards updated before this date"),
    
    # Фильтрация по связанным данным
    token_name: Optional[str] = Query(None, description="Filter by token name (partial match)"),
    token_symbol: Optional[str] = Query(None, description="Filter by token symbol (partial match)"),
    rarity_name: Optional[str] = Query(None, description="Filter by rarity name (partial match)"),
    
    # Сортировка
    sort_by: str = Query("created_at", regex="^(id|token_id|rarity_id|design_type|is_active|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все карточки для управления (с фильтрацией, сортировкой, пагинацией)
    Использует эффективную загрузку связанных данных без N+1 проблемы
    """
    
    # Базовый запрос с эффективной загрузкой связанных данных
    query = db.query(Card).options(
        joinedload(Card.token),
        joinedload(Card.rarity)
    )
    
    # Применяем фильтры к основной таблице
    if id is not None:
        query = query.filter(Card.id == id)
    
    if token_id is not None:
        query = query.filter(Card.token_id == token_id)
    
    if rarity_id is not None:
        query = query.filter(Card.rarity_id == rarity_id)
    
    if design_type:
        query = query.filter(Card.design_type.ilike(f"%{design_type.strip()}%"))
    
    if background_image_url:
        query = query.filter(Card.background_image_url.ilike(f"%{background_image_url.strip()}%"))
    
    if is_active is not None:
        query = query.filter(Card.is_active == is_active)
    
    # Фильтры по датам
    if created_from:
        query = query.filter(Card.created_at >= created_from)
    if created_to:
        query = query.filter(Card.created_at <= created_to)
    if updated_from:
        query = query.filter(Card.updated_at >= updated_from)
    if updated_to:
        query = query.filter(Card.updated_at <= updated_to)
    
    # Фильтры по связанным данным (избегаем дублирующих JOIN-ов)
    needs_token_join = bool(token_name or token_symbol)
    needs_rarity_join = bool(rarity_name)
    
    if needs_token_join:
        if token_name:
            query = query.filter(Token.name.ilike(f"%{token_name.strip()}%"))
        if token_symbol:
            query = query.filter(Token.symbol.ilike(f"%{token_symbol.strip()}%"))
    
    if needs_rarity_join:
        query = query.filter(Rarity.name.ilike(f"%{rarity_name.strip()}%"))
    
    # Подсчитываем общее количество с учетом всех фильтров
    total = query.count()
    
    # Применяем сортировку
    sort_column = getattr(Card, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    cards = query.offset(skip).limit(limit).all()
    
    # Формируем результат (связанные данные уже загружены благодаря joinedload)
    result = []
    for card in cards:
        card_data = CardResponse.model_validate(card)
        
        # Добавляем данные связанных объектов
        if card.token:
            card_data.token_name = card.token.name
            card_data.token_symbol = card.token.symbol
        
        if card.rarity:
            card_data.rarity_name = card.rarity.name
            card_data.rarity_color = card.rarity.color
        
        result.append(card_data)
    
    return PaginatedCardsResponse(
        items=result,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретную карточку по ID с связанными данными"""
    
    card = db.query(Card).options(
        joinedload(Card.token),
        joinedload(Card.rarity)
    ).filter(Card.id == card_id).first()
    
    if not card:
        raise HTTPException(
            status_code=404, 
            detail=f"Card with ID {card_id} not found"
        )
    
    # Формируем ответ с связанными данными
    card_data = CardResponse.model_validate(card)
    
    if card.token:
        card_data.token_name = card.token.name
        card_data.token_symbol = card.token.symbol
    
    if card.rarity:
        card_data.rarity_name = card.rarity.name
        card_data.rarity_color = card.rarity.color
    
    return card_data

@router.post("/", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(
    card_data: CardCreate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Создать новую карточку с проверкой активности связанных сущностей и уникальности"""
    
    # Проверяем что токен существует и активен
    token = db.query(Token).filter(
        Token.id == card_data.token_id,
        Token.is_active == True
    ).first()
    if not token:
        raise HTTPException(
            status_code=400,
            detail=f"Active token with ID {card_data.token_id} not found. "
                   "Token may be inactive or does not exist."
        )
    
    # Проверяем что редкость существует и активна
    rarity = db.query(Rarity).filter(
        Rarity.id == card_data.rarity_id,
        Rarity.is_active == True
    ).first()
    if not rarity:
        raise HTTPException(
            status_code=400,
            detail=f"Active rarity with ID {card_data.rarity_id} not found. "
                   "Rarity may be inactive or does not exist."
        )
    
    # Проверяем уникальность комбинации token_id + rarity_id + design_type
    existing_card = db.query(Card).filter(
        Card.token_id == card_data.token_id,
        Card.rarity_id == card_data.rarity_id,
        Card.design_type == card_data.design_type,
        Card.is_active == True
    ).first()
    if existing_card:
        raise HTTPException(
            status_code=400,
            detail=f"Active card with token ID {card_data.token_id}, "
                   f"rarity ID {card_data.rarity_id}, and design type "
                   f"'{card_data.design_type}' already exists (Card ID: {existing_card.id})"
        )
    
    try:
        # Создаем карточку
        new_card = Card(**card_data.dict())
        new_card.created_at = datetime.utcnow()
        new_card.updated_at = datetime.utcnow()
        
        db.add(new_card)
        db.commit()
        db.refresh(new_card)
        
        # Формируем ответ с связанными данными
        card_response = CardResponse.model_validate(new_card)
        card_response.token_name = token.name
        card_response.token_symbol = token.symbol
        card_response.rarity_name = rarity.name
        card_response.rarity_color = rarity.color
        
        return card_response
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create card: {str(e)}"
        )

@router.put("/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: int,
    card_data: CardUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить существующую карточку с проверкой активности связанных сущностей и уникальности"""
    
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(
            status_code=404, 
            detail=f"Card with ID {card_id} not found"
        )
    
    # Проверяем токен если он обновляется
    if card_data.token_id is not None and card_data.token_id != card.token_id:
        token = db.query(Token).filter(
            Token.id == card_data.token_id,
            Token.is_active == True
        ).first()
        if not token:
            raise HTTPException(
                status_code=400,
                detail=f"Active token with ID {card_data.token_id} not found. "
                       "Token may be inactive or does not exist."
            )
    
    # Проверяем редкость если она обновляется
    if card_data.rarity_id is not None and card_data.rarity_id != card.rarity_id:
        rarity = db.query(Rarity).filter(
            Rarity.id == card_data.rarity_id,
            Rarity.is_active == True
        ).first()
        if not rarity:
            raise HTTPException(
                status_code=400,
                detail=f"Active rarity with ID {card_data.rarity_id} not found. "
                       "Rarity may be inactive or does not exist."
            )
    
    # Проверяем уникальность новой комбинации если изменяются ключевые поля
    if any([card_data.token_id, card_data.rarity_id, card_data.design_type]):
        check_token_id = card_data.token_id if card_data.token_id is not None else card.token_id
        check_rarity_id = card_data.rarity_id if card_data.rarity_id is not None else card.rarity_id
        check_design_type = card_data.design_type if card_data.design_type is not None else card.design_type
        
        existing_card = db.query(Card).filter(
            Card.id != card_id,  # Исключаем текущую карточку
            Card.token_id == check_token_id,
            Card.rarity_id == check_rarity_id,
            Card.design_type == check_design_type,
            Card.is_active == True
        ).first()
        
        if existing_card:
            raise HTTPException(
                status_code=400,
                detail=f"Another active card with token ID {check_token_id}, "
                       f"rarity ID {check_rarity_id}, and design type "
                       f"'{check_design_type}' already exists (Card ID: {existing_card.id})"
            )
    
    try:
        # Обновляем поля
        update_data = card_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(card, field, value)
        
        card.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(card)
        
        # Возвращаем обновленную карту с связанными данными
        return await get_card(card_id, db, admin)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update card: {str(e)}"
        )

@router.get("/reference/options")
async def get_card_options(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить доступные опции для создания карточек"""
    
    try:
        # Получаем активные токены
        tokens = db.query(Token).filter(Token.is_active == True).order_by(Token.name).all()
        
        # Получаем активные редкости
        rarities = db.query(Rarity).filter(Rarity.is_active == True).order_by(Rarity.name).all()
        
        return {
            "design_types": VALID_DESIGN_TYPES,
            "available_tokens": [
                {"id": t.id, "name": t.name, "symbol": t.symbol}
                for t in tokens
            ],
            "available_rarities": [
                {"id": r.id, "name": r.name, "color": r.color, "score_bonus": r.score_bonus}
                for r in rarities
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch card options: {str(e)}"
        )

@router.get("/stats/summary")
async def get_cards_stats(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику карточек"""
    
    try:
        total_cards = db.query(Card).count()
        active_cards = db.query(Card).filter(Card.is_active == True).count()
        
        # Статистика по редкостям (только активные карточки)
        rarity_stats = db.query(Card.rarity_id, Rarity.name)\
            .join(Rarity, Card.rarity_id == Rarity.id)\
            .filter(Card.is_active == True)\
            .all()
        
        rarity_counts = {}
        for card_rarity_id, rarity_name in rarity_stats:
            rarity_counts[rarity_name] = rarity_counts.get(rarity_name, 0) + 1
        
        # Статистика по токенам (только активные карточки)
        token_stats = db.query(Card.token_id, Token.symbol)\
            .join(Token, Card.token_id == Token.id)\
            .filter(Card.is_active == True)\
            .all()
        
        token_counts = {}
        for card_token_id, token_symbol in token_stats:
            token_counts[token_symbol] = token_counts.get(token_symbol, 0) + 1
        
        # Статистика по типам дизайна
        design_stats = db.query(Card.design_type)\
            .filter(Card.is_active == True)\
            .all()
        
        design_counts = {}
        for (design_type,) in design_stats:
            design_counts[design_type] = design_counts.get(design_type, 0) + 1
        
        return {
            "total_cards": total_cards,
            "active_cards": active_cards,
            "inactive_cards": total_cards - active_cards,
            "cards_by_rarity": rarity_counts,
            "cards_by_token": token_counts,
            "cards_by_design": design_counts
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch card statistics: {str(e)}"
        )