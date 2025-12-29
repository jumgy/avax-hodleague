from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import joinedload
from typing import List, Optional
from pydantic import BaseModel, validator
from datetime import datetime

from models.database import get_async_db
from models.card_models import Card
from models.token_models import Token
from models.rarity_models import Rarity
from .auth import verify_admin_token

VALID_DESIGN_TYPES = ["classic", "neon", "retro", "galaxy", "minimalist", "cyberpunk"]

class CardCreate(BaseModel):
    token_id: int
    rarity_id: int
    design_type: str
    template_image_url: str
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

    @validator('template_image_url')
    def validate_template_image_url(cls, v):
        if not v or not v.strip():
            raise ValueError('Template image URL is required')
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Template image URL must start with http:// or https://')
        return v

class CardUpdate(BaseModel):
    token_id: Optional[int] = None
    rarity_id: Optional[int] = None
    design_type: Optional[str] = None
    template_image_url: Optional[str] = None
    is_active: Optional[bool] = None
    # background_image_url намеренно исключен - его заполняет только бэкэнд после рендера

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

    @validator('template_image_url')
    def validate_template_image_url(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Template image URL cannot be empty')
            v = v.strip()
            if not v.startswith(('http://', 'https://')):
                raise ValueError('Template image URL must start with http:// or https://')
            return v
        return v

class CardResponse(BaseModel):
    id: int
    token_id: int
    rarity_id: int
    design_type: str
    template_image_url: str
    background_image_url: Optional[str] = None
    last_rendered_at: Optional[datetime] = None
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
    template_image_url: Optional[str] = Query(None, description="Filter by template image URL (partial match)"),
    background_image_url: Optional[str] = Query(None, description="Filter by background image URL (partial match)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    has_rendered: Optional[bool] = Query(None, description="Filter by render status (has background_image_url)"),
    
    # Диапазоны дат
    created_from: Optional[datetime] = Query(None, description="Filter cards created after this date"),
    created_to: Optional[datetime] = Query(None, description="Filter cards created before this date"),
    updated_from: Optional[datetime] = Query(None, description="Filter cards updated after this date"),
    updated_to: Optional[datetime] = Query(None, description="Filter cards updated before this date"),
    rendered_from: Optional[datetime] = Query(None, description="Filter cards rendered after this date"),
    rendered_to: Optional[datetime] = Query(None, description="Filter cards rendered before this date"),
    
    # Фильтрация по связанным данным
    token_name: Optional[str] = Query(None, description="Filter by token name (partial match)"),
    token_symbol: Optional[str] = Query(None, description="Filter by token symbol (partial match)"),
    rarity_name: Optional[str] = Query(None, description="Filter by rarity name (partial match)"),
    
    # Сортировка
    sort_by: str = Query("created_at", regex="^(id|token_id|rarity_id|design_type|is_active|created_at|updated_at|last_rendered_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все карточки для управления (с фильтрацией, сортировкой, пагинацией)
    Использует эффективную загрузку связанных данных без N+1 проблемы
    """
    
    # Базовый запрос с эффективной загрузкой связанных данных
    query = select(Card).options(
        joinedload(Card.token),
        joinedload(Card.rarity)
    )
    
    # Применяем фильтры к основной таблице
    if id is not None:
        query = query.where(Card.id == id)
    
    if token_id is not None:
        query = query.where(Card.token_id == token_id)
    
    if rarity_id is not None:
        query = query.where(Card.rarity_id == rarity_id)
    
    if design_type:
        query = query.where(Card.design_type.ilike(f"%{design_type.strip()}%"))
    
    if template_image_url:
        query = query.where(Card.template_image_url.ilike(f"%{template_image_url.strip()}%"))
    
    if background_image_url:
        query = query.where(Card.background_image_url.ilike(f"%{background_image_url.strip()}%"))
    
    if is_active is not None:
        query = query.where(Card.is_active == is_active)
    
    # Фильтр по статусу рендера
    if has_rendered is not None:
        if has_rendered:
            query = query.where(Card.background_image_url.isnot(None))
        else:
            query = query.where(Card.background_image_url.is_(None))
    
    # Фильтры по датам
    if created_from:
        query = query.where(Card.created_at >= created_from)
    if created_to:
        query = query.where(Card.created_at <= created_to)
    if updated_from:
        query = query.where(Card.updated_at >= updated_from)
    if updated_to:
        query = query.where(Card.updated_at <= updated_to)
    if rendered_from:
        query = query.where(Card.last_rendered_at >= rendered_from)
    if rendered_to:
        query = query.where(Card.last_rendered_at <= rendered_to)
    
    # Фильтры по связанным данным
    if token_name or token_symbol:
        query = query.join(Token, Card.token_id == Token.id)
        if token_name:
            query = query.where(Token.name.ilike(f"%{token_name.strip()}%"))
        if token_symbol:
            query = query.where(Token.symbol.ilike(f"%{token_symbol.strip()}%"))
    
    if rarity_name:
        query = query.join(Rarity, Card.rarity_id == Rarity.id)
        query = query.where(Rarity.name.ilike(f"%{rarity_name.strip()}%"))
    
    # Подсчитываем общее количество с учетом всех фильтров
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(Card, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    cards = result.scalars().unique().all()
    
    # Формируем результат (связанные данные уже загружены благодаря joinedload)
    response_items = []
    for card in cards:
        card_data = CardResponse.model_validate(card)
        
        # Добавляем данные связанных объектов
        if card.token:
            card_data.token_name = card.token.name
            card_data.token_symbol = card.token.symbol
        
        if card.rarity:
            card_data.rarity_name = card.rarity.name
            card_data.rarity_color = card.rarity.color
        
        response_items.append(card_data)
    
    return PaginatedCardsResponse(
        items=response_items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретную карточку по ID с связанными данными"""
    
    query = select(Card).options(
        joinedload(Card.token),
        joinedload(Card.rarity)
    ).where(Card.id == card_id)
    
    result = await db.execute(query)
    card = result.scalar_one_or_none()
    
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
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Создать новую карточку с проверкой активности связанных сущностей и уникальности"""
    
    # Проверяем что токен существует и активен
    token_query = select(Token).where(
        Token.id == card_data.token_id,
        Token.is_active == True
    )
    token_result = await db.execute(token_query)
    token = token_result.scalar_one_or_none()
    
    if not token:
        raise HTTPException(
            status_code=400,
            detail=f"Active token with ID {card_data.token_id} not found. "
                   "Token may be inactive or does not exist."
        )
    
    # Проверяем что редкость существует и активна
    rarity_query = select(Rarity).where(
        Rarity.id == card_data.rarity_id,
        Rarity.is_active == True
    )
    rarity_result = await db.execute(rarity_query)
    rarity = rarity_result.scalar_one_or_none()
    
    if not rarity:
        raise HTTPException(
            status_code=400,
            detail=f"Active rarity with ID {card_data.rarity_id} not found. "
                   "Rarity may be inactive or does not exist."
        )
    
    # Проверяем уникальность комбинации token_id + rarity_id + design_type
    existing_query = select(Card).where(
        Card.token_id == card_data.token_id,
        Card.rarity_id == card_data.rarity_id,
        Card.design_type == card_data.design_type,
        Card.is_active == True
    )
    existing_result = await db.execute(existing_query)
    existing_card = existing_result.scalar_one_or_none()
    
    if existing_card:
        raise HTTPException(
            status_code=400,
            detail=f"Active card with token ID {card_data.token_id}, "
                   f"rarity ID {card_data.rarity_id}, and design type "
                   f"'{card_data.design_type}' already exists (Card ID: {existing_card.id})"
        )
    
    try:
        # Создаем карточку (background_image_url и last_rendered_at будут NULL)
        new_card = Card(**card_data.dict())
        new_card.created_at = datetime.utcnow()
        new_card.updated_at = datetime.utcnow()
        # background_image_url и last_rendered_at останутся None до рендера
        
        db.add(new_card)
        await db.flush()
        await db.refresh(new_card)
        
        # Формируем ответ с связанными данными
        card_response = CardResponse.model_validate(new_card)
        card_response.token_name = token.name
        card_response.token_symbol = token.symbol
        card_response.rarity_name = rarity.name
        card_response.rarity_color = rarity.color
        
        return card_response
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create card: {str(e)}"
        )

@router.put("/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: int,
    card_data: CardUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить существующую карточку с проверкой активности связанных сущностей и уникальности"""
    
    query = select(Card).where(Card.id == card_id)
    result = await db.execute(query)
    card = result.scalar_one_or_none()
    
    if not card:
        raise HTTPException(
            status_code=404, 
            detail=f"Card with ID {card_id} not found"
        )
    
    # Проверяем токен если он обновляется
    if card_data.token_id is not None and card_data.token_id != card.token_id:
        token_query = select(Token).where(
            Token.id == card_data.token_id,
            Token.is_active == True
        )
        token_result = await db.execute(token_query)
        token = token_result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=400,
                detail=f"Active token with ID {card_data.token_id} not found. "
                       "Token may be inactive or does not exist."
            )
    
    # Проверяем редкость если она обновляется
    if card_data.rarity_id is not None and card_data.rarity_id != card.rarity_id:
        rarity_query = select(Rarity).where(
            Rarity.id == card_data.rarity_id,
            Rarity.is_active == True
        )
        rarity_result = await db.execute(rarity_query)
        rarity = rarity_result.scalar_one_or_none()
        
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
        
        existing_query = select(Card).where(
            Card.id != card_id,
            Card.token_id == check_token_id,
            Card.rarity_id == check_rarity_id,
            Card.design_type == check_design_type,
            Card.is_active == True
        )
        existing_result = await db.execute(existing_query)
        existing_card = existing_result.scalar_one_or_none()
        
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
        
        # Если обновляется template_image_url, сбрасываем rendered данные
        if 'template_image_url' in update_data:
            card.background_image_url = None
            card.last_rendered_at = None
        
        await db.flush()
        await db.refresh(card)
        
        # Возвращаем обновленную карту с связанными данными
        return await get_card(card_id, db, admin)
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update card: {str(e)}"
        )

@router.get("/reference/options")
async def get_card_options(
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить доступные опции для создания карточек"""
    
    try:
        # Получаем активные токены
        tokens_query = select(Token).where(Token.is_active == True).order_by(Token.name)
        tokens_result = await db.execute(tokens_query)
        tokens = tokens_result.scalars().all()
        
        # Получаем активные редкости
        rarities_query = select(Rarity).where(Rarity.is_active == True).order_by(Rarity.name)
        rarities_result = await db.execute(rarities_query)
        rarities = rarities_result.scalars().all()
        
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
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику карточек"""
    
    try:
        # Общее количество карточек
        total_query = select(func.count(Card.id))
        total_result = await db.execute(total_query)
        total_cards = total_result.scalar()
        
        # Активные карточки
        active_query = select(func.count(Card.id)).where(Card.is_active == True)
        active_result = await db.execute(active_query)
        active_cards = active_result.scalar()
        
        # Карточки с отрендеренным background
        rendered_query = select(func.count(Card.id)).where(
            Card.is_active == True,
            Card.background_image_url.isnot(None)
        )
        rendered_result = await db.execute(rendered_query)
        rendered_cards = rendered_result.scalar()
        
        # Карточки без рендера
        not_rendered_query = select(func.count(Card.id)).where(
            Card.is_active == True,
            Card.background_image_url.is_(None)
        )
        not_rendered_result = await db.execute(not_rendered_query)
        not_rendered_cards = not_rendered_result.scalar()
        
        # Статистика по редкостям (только активные карточки)
        rarity_query = select(Card.rarity_id, Rarity.name)\
            .join(Rarity, Card.rarity_id == Rarity.id)\
            .where(Card.is_active == True)
        rarity_result = await db.execute(rarity_query)
        rarity_stats = rarity_result.all()
        
        rarity_counts = {}
        for card_rarity_id, rarity_name in rarity_stats:
            rarity_counts[rarity_name] = rarity_counts.get(rarity_name, 0) + 1
        
        # Статистика по токенам (только активные карточки)
        token_query = select(Card.token_id, Token.symbol)\
            .join(Token, Card.token_id == Token.id)\
            .where(Card.is_active == True)
        token_result = await db.execute(token_query)
        token_stats = token_result.all()
        
        token_counts = {}
        for card_token_id, token_symbol in token_stats:
            token_counts[token_symbol] = token_counts.get(token_symbol, 0) + 1
        
        # Статистика по типам дизайна
        design_query = select(Card.design_type).where(Card.is_active == True)
        design_result = await db.execute(design_query)
        design_stats = design_result.all()
        
        design_counts = {}
        for (design_type,) in design_stats:
            design_counts[design_type] = design_counts.get(design_type, 0) + 1
        
        return {
            "total_cards": total_cards,
            "active_cards": active_cards,
            "inactive_cards": total_cards - active_cards,
            "rendered_cards": rendered_cards,
            "not_rendered_cards": not_rendered_cards,
            "cards_by_rarity": rarity_counts,
            "cards_by_token": token_counts,
            "cards_by_design": design_counts
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch card statistics: {str(e)}"
        )