from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime
import re

from models.database import get_async_db
from models.rarity_models import Rarity
from models.card_models import Card
from .auth import verify_admin_token

class RarityCreate(BaseModel):
    name: str
    description: str
    score_bonus: int = 0
    color: str = '#000000'
    is_active: bool = True

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Name is required')
        if len(v.strip()) > 20:
            raise ValueError('Name cannot exceed 20 characters')
        if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-_]+$', v.strip()):
            raise ValueError('Name can only contain letters, numbers, spaces, hyphens and underscores')
        return v.strip()

    @validator('description')
    def validate_description(cls, v):
        if not v or not v.strip():
            raise ValueError('Description is required')
        if len(v.strip()) > 500:
            raise ValueError('Description cannot exceed 500 characters')
        return v.strip()

    @validator('score_bonus')
    def validate_score_bonus(cls, v):
        if v is None:
            return 0
        if v < 0:
            raise ValueError('Score bonus cannot be negative')
        if v > 10000:
            raise ValueError('Score bonus cannot exceed 10000')
        return v

    @validator('color')
    def validate_color(cls, v):
        if not v:
            return '#000000'
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Color must be a valid HEX color format (e.g., #FF0000)')
        return v.upper()

class RarityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    score_bonus: Optional[int] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Name cannot be empty')
            if len(v.strip()) > 20:
                raise ValueError('Name cannot exceed 20 characters')
            if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-_]+$', v.strip()):
                raise ValueError('Name can only contain letters, numbers, spaces, hyphens and underscores')
            return v.strip()
        return v

    @validator('description')
    def validate_description(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Description cannot be empty')
            if len(v.strip()) > 500:
                raise ValueError('Description cannot exceed 500 characters')
            return v.strip()
        return v

    @validator('score_bonus')
    def validate_score_bonus(cls, v):
        if v is not None:
            if v < 0:
                raise ValueError('Score bonus cannot be negative')
            if v > 10000:
                raise ValueError('Score bonus cannot exceed 10000')
        return v

    @validator('color')
    def validate_color(cls, v):
        if v is not None:
            if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
                raise ValueError('Color must be a valid HEX color format (e.g., #FF0000)')
            return v.upper()
        return v

class RarityResponse(BaseModel):
    id: int
    name: str
    description: str
    score_bonus: int
    color: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedRarityResponse(BaseModel):
    items: List[RarityResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

# --- Router ---

router = APIRouter(prefix="/panel/rarities")

@router.get("/", response_model=PaginatedRarityResponse)
async def get_all_rarities(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None, description="Filter by active status (true=active, false=inactive, null=all)"),
    name: Optional[str] = Query(None, description="Search by name (case insensitive)"),
    description: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    score_bonus_from: Optional[int] = Query(None),
    score_bonus_to: Optional[int] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    updated_from: Optional[datetime] = Query(None),
    updated_to: Optional[datetime] = Query(None),
    sort_by: str = Query("name", regex="^(id|name|score_bonus|color|created_at|updated_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все редкости с фильтрацией, сортировкой и пагинацией
    """
    
    # Базовый запрос
    query = select(Rarity)
    
    # Применяем фильтры
    if id is not None:
        query = query.where(Rarity.id == id)
    
    if is_active is not None:
        query = query.where(Rarity.is_active == is_active)
    
    if name:
        query = query.where(Rarity.name.ilike(f"%{name}%"))
    
    if description:
        query = query.where(Rarity.description.ilike(f"%{description}%"))
    
    if color:
        query = query.where(Rarity.color == color.upper())
    
    if score_bonus_from is not None:
        query = query.where(Rarity.score_bonus >= score_bonus_from)
    
    if score_bonus_to is not None:
        query = query.where(Rarity.score_bonus <= score_bonus_to)
    
    if created_from:
        query = query.where(Rarity.created_at >= created_from)
    
    if created_to:
        query = query.where(Rarity.created_at <= created_to)
    
    if updated_from:
        query = query.where(Rarity.updated_at >= updated_from)
    
    if updated_to:
        query = query.where(Rarity.updated_at <= updated_to)
    
    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(Rarity, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    rarities = result.scalars().all()
    
    return PaginatedRarityResponse(
        items=rarities,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{rarity_id}", response_model=RarityResponse)
async def get_rarity(
    rarity_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретную редкость по ID"""
    
    query = select(Rarity).where(Rarity.id == rarity_id)
    result = await db.execute(query)
    rarity = result.scalar_one_or_none()
    
    if not rarity:
        raise HTTPException(status_code=404, detail="Rarity not found")
    
    return rarity

@router.post("/", response_model=RarityResponse, status_code=status.HTTP_201_CREATED)
async def create_rarity(
    rarity_data: RarityCreate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Создать новую редкость с проверкой уникальности имени"""
    
    # Проверяем уникальность имени
    existing_query = select(Rarity).where(Rarity.name.ilike(rarity_data.name))
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Rarity with name '{rarity_data.name}' already exists"
        )
    
    try:
        # Создаем новую редкость
        new_rarity = Rarity(
            name=rarity_data.name,
            description=rarity_data.description,
            score_bonus=rarity_data.score_bonus,
            color=rarity_data.color,
            is_active=rarity_data.is_active
        )
        
        db.add(new_rarity)
        await db.flush()
        await db.refresh(new_rarity)
        
        return new_rarity
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create rarity: {str(e)}"
        )

@router.put("/{rarity_id}", response_model=RarityResponse)
async def update_rarity(
    rarity_id: int,
    rarity_data: RarityUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить существующую редкость с проверкой ограничений"""
    
    # Получаем существующую редкость
    query = select(Rarity).where(Rarity.id == rarity_id)
    result = await db.execute(query)
    rarity = result.scalar_one_or_none()
    
    if not rarity:
        raise HTTPException(status_code=404, detail="Rarity not found")
    
    # Проверка уникальности имени если оно меняется
    if rarity_data.name and rarity_data.name.lower() != rarity.name.lower():
        existing_query = select(Rarity).where(Rarity.name.ilike(rarity_data.name))
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Rarity with name '{rarity_data.name}' already exists"
            )
    
    # Проверка при деактивации - нельзя деактивировать если есть активные карты
    if rarity_data.is_active is False and rarity.is_active:
        active_cards_query = select(func.count(Card.id)).where(
            Card.rarity_id == rarity_id,
            Card.is_active == True
        )
        active_cards_result = await db.execute(active_cards_query)
        active_cards_count = active_cards_result.scalar()
        
        if active_cards_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot deactivate rarity '{rarity.name}'. It is currently used by {active_cards_count} active card(s). Please deactivate or change rarity of all cards first."
            )
    
    try:
        # Обновляем поля
        update_data = rarity_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(rarity, field, value)
        
        rarity.updated_at = datetime.utcnow()
        
        await db.flush()
        await db.refresh(rarity)
        
        return rarity
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update rarity: {str(e)}"
        )

@router.get("/stats/summary")
async def get_rarities_summary(
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику редкостей"""
    
    try:
        # Общее количество редкостей
        total_query = select(func.count(Rarity.id))
        total_result = await db.execute(total_query)
        total_rarities = total_result.scalar()
        
        # Активные редкости
        active_query = select(func.count(Rarity.id)).where(Rarity.is_active == True)
        active_result = await db.execute(active_query)
        active_rarities = active_result.scalar()
        
        inactive_rarities = total_rarities - active_rarities
        
        # Статистика по score_bonus
        score_stats_query = select(
            func.avg(Rarity.score_bonus).label('avg_score'),
            func.max(Rarity.score_bonus).label('max_score')
        ).where(Rarity.is_active == True)
        score_stats_result = await db.execute(score_stats_query)
        score_stats = score_stats_result.one()
        
        avg_score_bonus = float(score_stats.avg_score) if score_stats.avg_score else 0
        max_score_bonus = score_stats.max_score if score_stats.max_score else 0
        
        # Недавно созданные редкости
        recent_query = select(Rarity).order_by(Rarity.created_at.desc()).limit(5)
        recent_result = await db.execute(recent_query)
        recent_rarities = recent_result.scalars().all()
        
        return {
            "total_rarities": total_rarities,
            "active_rarities": active_rarities,
            "inactive_rarities": inactive_rarities,
            "score_bonus_stats": {
                "average": round(avg_score_bonus, 2),
                "maximum": max_score_bonus
            },
            "recent_rarities": [
                {
                    "id": r.id,
                    "name": r.name,
                    "score_bonus": r.score_bonus,
                    "color": r.color,
                    "is_active": r.is_active,
                    "created_at": r.created_at
                } for r in recent_rarities
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch rarities summary: {str(e)}"
        )