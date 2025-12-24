from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from decimal import Decimal
from datetime import datetime
import re

from models.database import get_async_db
from models.reward_models import RewardType, RewardCategory
from .auth import verify_admin_token

# --- Pydantic models (БЕЗ ИЗМЕНЕНИЙ) ---

class RewardTypeCreate(BaseModel):
    name: str
    description: str
    reward_category: str
    default_amount: Decimal = Decimal("0.0")
    currency_type: str
    is_claimable: bool = True
    expires_after_days: Optional[int] = None
    is_active: bool = True

    @validator('name')
    def name_valid(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 100:
            raise ValueError("Name max length is 100")
        if not re.match(r"^[\w\s\-\_]+$", v, re.UNICODE):
            raise ValueError("Name can only contain letters, numbers, spaces, hyphens, underscores")
        return v

    @validator('description')
    def desc_valid(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Description is required")
        if len(v) > 2000:
            raise ValueError("Description max length is 2000")
        return v

    @validator('reward_category')
    def reward_category_valid(cls, v):
        if not RewardCategory.is_valid(v):
            raise ValueError(f"Reward category must be one of: {RewardCategory.ALL_CATEGORIES}")
        return v

    @validator('currency_type')
    def currency_type_valid(cls, v):
        v = v.strip().upper()
        if not 3 <= len(v) <= 20 or not re.match(r"^[A-Z_]+$", v):
            raise ValueError("Currency type must be 3-20 uppercase ASCII letters or underscores")
        return v

    @validator('default_amount')
    def default_amount_valid(cls, v):
        if v < 0 or v > Decimal("999999999999.99999999"):
            raise ValueError("Default amount must be >=0 and <=999999999999.99999999")
        return v

    @validator('expires_after_days')
    def expires_valid(cls, v):
        if v is not None and v < 1:
            raise ValueError("expires_after_days, if set, must be >=1")
        return v

class RewardTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    reward_category: Optional[str] = None
    default_amount: Optional[Decimal] = None
    currency_type: Optional[str] = None
    is_claimable: Optional[bool] = None
    expires_after_days: Optional[int] = None
    is_active: Optional[bool] = None

    @validator('name')
    def name_valid(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Name is required")
            if len(v) > 100:
                raise ValueError("Name max length is 100")
            if not re.match(r"^[\w\s\-\_]+$", v, re.UNICODE):
                raise ValueError("Name can only contain letters, numbers, spaces, hyphens, underscores")
        return v

    @validator('description')
    def desc_valid(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Description is required")
            if len(v) > 2000:
                raise ValueError("Description max length is 2000")
        return v

    @validator('reward_category')
    def reward_category_valid(cls, v):
        if v is not None and not RewardCategory.is_valid(v):
            raise ValueError(f"Reward category must be one of: {RewardCategory.ALL_CATEGORIES}")
        return v

    @validator('currency_type')
    def currency_type_valid(cls, v):
        if v is not None:
            v = v.strip().upper()
            if not 3 <= len(v) <= 20 or not re.match(r"^[A-Z_]+$", v):
                raise ValueError("Currency type must be 3-20 uppercase ASCII letters or underscores")
        return v

    @validator('default_amount')
    def default_amount_valid(cls, v):
        if v is not None and (v < 0 or v > Decimal("999999999999.99999999")):
            raise ValueError("Default amount must be >=0 and <=999999999999.99999999")
        return v

    @validator('expires_after_days')
    def expires_valid(cls, v):
        if v is not None and v < 1:
            raise ValueError("expires_after_days, if set, must be >=1")
        return v

class RewardTypeResponse(BaseModel):
    id: int
    name: str
    description: str
    reward_category: str
    default_amount: Decimal
    currency_type: str
    is_claimable: bool
    expires_after_days: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedRewardTypeResponse(BaseModel):
    items: List[RewardTypeResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

# --- Router ---

router = APIRouter(prefix="/panel/reward-types")

@router.get("/", response_model=PaginatedRewardTypeResponse)
async def get_reward_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None, description="Filter only active reward types"),
    name: Optional[str] = Query(None, description="Search by name"),
    reward_category: Optional[str] = Query(None, description="Filter by category"),
    currency_type: Optional[str] = Query(None),
    default_amount_from: Optional[Decimal] = Query(None),
    default_amount_to: Optional[Decimal] = Query(None),
    expires_after_days_from: Optional[int] = Query(None),
    expires_after_days_to: Optional[int] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    updated_from: Optional[datetime] = Query(None),
    updated_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at", regex="^(id|name|description|reward_category|default_amount|currency_type|is_claimable|expires_after_days|is_active|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все типы наград с фильтрацией, сортировкой и пагинацией
    """
    
    # Базовый запрос
    query = select(RewardType)
    
    # Применяем фильтры
    if id is not None:
        query = query.where(RewardType.id == id)
    
    if is_active is not None:
        query = query.where(RewardType.is_active == is_active)
    
    if name:
        query = query.where(RewardType.name.ilike(f"%{name}%"))
    
    if reward_category:
        query = query.where(RewardType.reward_category == reward_category)
    
    if currency_type:
        query = query.where(RewardType.currency_type == currency_type.upper())
    
    if default_amount_from is not None:
        query = query.where(RewardType.default_amount >= default_amount_from)
    
    if default_amount_to is not None:
        query = query.where(RewardType.default_amount <= default_amount_to)
    
    if expires_after_days_from is not None:
        query = query.where(RewardType.expires_after_days >= expires_after_days_from)
    
    if expires_after_days_to is not None:
        query = query.where(RewardType.expires_after_days <= expires_after_days_to)
    
    if created_from:
        query = query.where(RewardType.created_at >= created_from)
    
    if created_to:
        query = query.where(RewardType.created_at <= created_to)
    
    if updated_from:
        query = query.where(RewardType.updated_at >= updated_from)
    
    if updated_to:
        query = query.where(RewardType.updated_at <= updated_to)
    
    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(RewardType, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return PaginatedRewardTypeResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{reward_type_id}", response_model=RewardTypeResponse)
async def get_reward_type(
    reward_type_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретный тип награды по ID"""
    
    query = select(RewardType).where(RewardType.id == reward_type_id)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="Reward type not found")
    
    return obj

@router.post("/", response_model=RewardTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_reward_type(
    data: RewardTypeCreate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Создать новый тип награды с проверкой уникальности имени"""
    
    # Проверяем уникальность имени
    existing_query = select(RewardType).where(RewardType.name.ilike(data.name))
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Reward type name '{data.name}' already exists"
        )
    
    try:
        # Создаем новый тип награды
        obj = RewardType(
            name=data.name,
            description=data.description,
            reward_category=data.reward_category,
            default_amount=data.default_amount,
            currency_type=data.currency_type,
            is_claimable=data.is_claimable,
            expires_after_days=data.expires_after_days,
            is_active=data.is_active,
        )
        
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        
        return obj
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create reward type: {str(e)}"
        )

@router.put("/{reward_type_id}", response_model=RewardTypeResponse)
async def update_reward_type(
    reward_type_id: int,
    data: RewardTypeUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить существующий тип награды с проверкой ограничений"""
    
    # Получаем существующий тип награды
    query = select(RewardType).where(RewardType.id == reward_type_id)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="Reward type not found")
    
    # Проверка уникальности имени если оно меняется
    if data.name and data.name.lower() != obj.name.lower():
        existing_query = select(RewardType).where(RewardType.name.ilike(data.name))
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Reward type name '{data.name}' already exists"
            )
    
    try:
        # Обновляем поля
        update_data = data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(obj, field, value)
        
        obj.updated_at = datetime.utcnow()
        
        await db.flush()
        await db.refresh(obj)
        
        return obj
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update reward type: {str(e)}"
        )