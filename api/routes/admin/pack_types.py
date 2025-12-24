from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Any
from pydantic import BaseModel, validator, HttpUrl, ConfigDict
from datetime import datetime
from decimal import Decimal
import re

from models.database import get_async_db
from models.pack_models import PackType
from models.user_pack_models import UserPack
from .auth import verify_admin_token

class PackTypeCreate(BaseModel):
    name: str
    description: str
    image_url: HttpUrl
    header_image_url: HttpUrl
    cards_per_pack: int = 5
    price: Decimal = Decimal("0.00")
    currency: str
    supply: Optional[int] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    guaranteed_slots: Optional[Any] = None
    is_active: bool = True

    @validator('name')
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Name is required')
        if len(v) > 100:
            raise ValueError('Name max length is 100')
        if not re.match(r'^[\w\-\s]+$', v, re.UNICODE):
            raise ValueError("Name can only contain letters, numbers, spaces, hyphens, underscores")
        return v

    @validator('description')
    def validate_description(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Description is required")
        if len(v) > 2000:
            raise ValueError("Description max length is 2000")
        return v

    @validator('cards_per_pack')
    def validate_cards_per_pack(cls, v):
        if not (1 <= v <= 100):
            raise ValueError("cards_per_pack must be 1-100")
        return v

    @validator('price')
    def validate_price(cls, v):
        if v < 0 or v > Decimal("999999.99"):
            raise ValueError("Price must be >=0 and <=999999.99")
        return v

    @validator('currency')
    def validate_currency(cls, v):
        v = v.strip().upper()
        if not re.match(r'^[A-Z]{3,20}$', v):
            raise ValueError('Currency must be 3-20 ASCII uppercase letters')
        return v

    @validator('available_until')
    def validate_available_until(cls, v, values):
        start = values.get('available_from')
        if v and start and v < start:
            raise ValueError('available_until must be after available_from')
        return v

    @validator('supply')
    def validate_supply(cls, v):
        if v is not None and v < 1:
            raise ValueError('supply must be >= 1')
        return v

    @validator('guaranteed_slots')
    def validate_slots(cls, v):
        if v is not None and not isinstance(v, (list, dict)):
            raise ValueError("guaranteed_slots must be JSON — object or list")
        return v

class PackTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[HttpUrl] = None
    header_image_url: Optional[HttpUrl] = None
    cards_per_pack: Optional[int] = None
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    supply: Optional[int] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    guaranteed_slots: Optional[Any] = None
    is_active: Optional[bool] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('Name is required')
            if len(v) > 100:
                raise ValueError('Name max length is 100')
            if not re.match(r'^[\w\-\s]+$', v, re.UNICODE):
                raise ValueError("Name can only contain letters, numbers, spaces, hyphens, underscores")
        return v

    @validator('description')
    def validate_description(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Description is required")
            if len(v) > 2000:
                raise ValueError("Description max length is 2000")
        return v

    @validator('cards_per_pack')
    def validate_cards_per_pack(cls, v):
        if v is not None and not (1 <= v <= 100):
            raise ValueError("cards_per_pack must be 1-100")
        return v

    @validator('price')
    def validate_price(cls, v):
        if v is not None and (v < 0 or v > Decimal("999999.99")):
            raise ValueError("Price must be >=0 and <=999999.99")
        return v

    @validator('currency')
    def validate_currency(cls, v):
        if v is not None:
            v = v.strip().upper()
            if not re.match(r'^[A-Z]{3,20}$', v):
                raise ValueError('Currency must be 3-20 ASCII uppercase letters')
        return v

    @validator('available_until')
    def validate_available_until(cls, v, values):
        start = values.get('available_from')
        if v is not None and start is not None and v < start:
            raise ValueError('available_until must be after available_from')
        return v

    @validator('supply')
    def validate_supply(cls, v):
        if v is not None and v < 1:
            raise ValueError('supply must be >= 1')
        return v

    @validator('guaranteed_slots')
    def validate_slots(cls, v):
        if v is not None and not isinstance(v, (list, dict)):
            raise ValueError("guaranteed_slots must be JSON — object or list")
        return v

class PackTypeResponse(BaseModel):
    id: int
    name: str
    description: str
    image_url: str
    header_image_url: str
    cards_per_pack: int
    price: Decimal
    currency: str
    supply: Optional[int]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    guaranteed_slots: Optional[Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedPackTypeResponse(BaseModel):
    items: List[PackTypeResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

# --- Router ---

router = APIRouter(prefix="/panel/pack-types")

@router.get("/", response_model=PaginatedPackTypeResponse)
async def get_pack_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    # Фильтрация по всем возможным полям и диапазонам
    id: Optional[int] = Query(None),
    name: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    cards_per_pack: Optional[int] = Query(None),
    cards_per_pack_from: Optional[int] = Query(None),
    cards_per_pack_to: Optional[int] = Query(None),
    price_from: Optional[Decimal] = Query(None),
    price_to: Optional[Decimal] = Query(None),
    currency: Optional[str] = Query(None),
    supply_from: Optional[int] = Query(None),
    supply_to: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    available_from_after: Optional[datetime] = Query(None),
    available_from_before: Optional[datetime] = Query(None),
    available_until_after: Optional[datetime] = Query(None),
    available_until_before: Optional[datetime] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    updated_from: Optional[datetime] = Query(None),
    updated_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at", regex="^(id|name|cards_per_pack|price|supply|created_at|updated_at|available_from)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все типы паков с фильтрацией, сортировкой и пагинацией
    """
    
    # Базовый запрос
    query = select(PackType)
    
    # Применяем фильтры
    if id is not None:
        query = query.where(PackType.id == id)
    
    if name:
        query = query.where(PackType.name.ilike(f"%{name}%"))
    
    if description:
        query = query.where(PackType.description.ilike(f"%{description}%"))
    
    if cards_per_pack is not None:
        query = query.where(PackType.cards_per_pack == cards_per_pack)
    
    if cards_per_pack_from is not None:
        query = query.where(PackType.cards_per_pack >= cards_per_pack_from)
    
    if cards_per_pack_to is not None:
        query = query.where(PackType.cards_per_pack <= cards_per_pack_to)
    
    if price_from is not None:
        query = query.where(PackType.price >= price_from)
    
    if price_to is not None:
        query = query.where(PackType.price <= price_to)
    
    if currency:
        query = query.where(PackType.currency == currency)
    
    if supply_from is not None:
        query = query.where(PackType.supply >= supply_from)
    
    if supply_to is not None:
        query = query.where(PackType.supply <= supply_to)
    
    if is_active is not None:
        query = query.where(PackType.is_active == is_active)
    
    if available_from_after:
        query = query.where(PackType.available_from >= available_from_after)
    
    if available_from_before:
        query = query.where(PackType.available_from <= available_from_before)
    
    if available_until_after:
        query = query.where(PackType.available_until >= available_until_after)
    
    if available_until_before:
        query = query.where(PackType.available_until <= available_until_before)
    
    if created_from:
        query = query.where(PackType.created_at >= created_from)
    
    if created_to:
        query = query.where(PackType.created_at <= created_to)
    
    if updated_from:
        query = query.where(PackType.updated_at >= updated_from)
    
    if updated_to:
        query = query.where(PackType.updated_at <= updated_to)
    
    # Подсчитываем общее количество с учетом всех фильтров
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(PackType, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return PaginatedPackTypeResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{pack_type_id}", response_model=PackTypeResponse)
async def get_pack_type(
    pack_type_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретный тип пака по ID"""
    
    query = select(PackType).where(PackType.id == pack_type_id)
    result = await db.execute(query)
    pack = result.scalar_one_or_none()
    
    if not pack:
        raise HTTPException(status_code=404, detail="Pack type not found")
    
    return pack

@router.post("/", response_model=PackTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_pack_type(
    data: PackTypeCreate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Создать новый тип пака с проверкой уникальности имени"""
    
    # Проверяем уникальность имени
    existing_query = select(PackType).where(PackType.name.ilike(data.name))
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Pack type name '{data.name}' already exists"
        )
    
    try:
        # Создаем новый тип пака
        new_pack = PackType(
            name=data.name,
            description=data.description,
            image_url=str(data.image_url),
            header_image_url=str(data.header_image_url),
            cards_per_pack=data.cards_per_pack,
            price=data.price,
            currency=data.currency,
            supply=data.supply,
            available_from=data.available_from,
            available_until=data.available_until,
            guaranteed_slots=data.guaranteed_slots,
            is_active=data.is_active
        )
        
        db.add(new_pack)
        await db.flush()
        await db.refresh(new_pack)
        
        return new_pack
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create pack type: {str(e)}"
        )

@router.put("/{pack_type_id}", response_model=PackTypeResponse)
async def update_pack_type(
    pack_type_id: int,
    data: PackTypeUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить существующий тип пака с проверкой ограничений"""
    
    # Получаем существующий пак
    query = select(PackType).where(PackType.id == pack_type_id)
    result = await db.execute(query)
    pack = result.scalar_one_or_none()
    
    if not pack:
        raise HTTPException(status_code=404, detail="Pack type not found")
    
    # Проверка дублирования имени
    if data.name and data.name.lower() != pack.name.lower():
        existing_query = select(PackType).where(PackType.name.ilike(data.name))
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Pack type name '{data.name}' already exists"
            )
    
    # Проверка supply если обновляется
    if data.supply is not None:
        # Проверяем сколько паков уже куплено/выдано
        count_query = select(func.count(UserPack.id)).where(
            UserPack.pack_type_id == pack_type_id
        )
        count_result = await db.execute(count_query)
        active_purchases = count_result.scalar()
        
        if active_purchases > data.supply:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot set supply below {active_purchases} (already purchased/issued)"
            )
    
    try:
        # Обновление полей
        update_data = data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(pack, field, value)
        
        pack.updated_at = datetime.utcnow()
        
        await db.flush()
        await db.refresh(pack)
        
        return pack
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update pack type: {str(e)}"
        )