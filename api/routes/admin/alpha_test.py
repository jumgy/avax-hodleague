from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import List, Optional
from pydantic import BaseModel, field_validator, ConfigDict
from datetime import datetime, timedelta
from models.database import get_async_db
from models.alpha_test_models import AlphaTestAccess
from .auth import verify_admin_token


class AlphaTestAccessCreate(BaseModel):
    wallet_address: str
    
    @field_validator('wallet_address')
    @classmethod
    def validate_wallet_address(cls, v):
        v = v.strip().lower()
        if not v.startswith('0x'):
            raise ValueError('Wallet address must start with 0x')
        if len(v) != 42:
            raise ValueError('Wallet address must be 42 characters (0x + 40 hex)')
        # Проверка на hex символы
        try:
            int(v[2:], 16)
        except ValueError:
            raise ValueError('Invalid hexadecimal characters in wallet address')
        return v


class AlphaTestAccessResponse(BaseModel):
    id: int
    wallet_address: str
    created_at: datetime
    wallet_short: str
    days_since_added: int
    
    model_config = ConfigDict(from_attributes=True)


class PaginatedAlphaTestResponse(BaseModel):
    items: List[AlphaTestAccessResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool


router = APIRouter(prefix="/panel/alpha-test")


@router.get("/", response_model=PaginatedAlphaTestResponse)
async def get_all_alpha_test_access(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    wallet_address: Optional[str] = Query(None, description="Search by wallet address"),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    days_added_from: Optional[int] = Query(None, description="Filter addresses added at least X days ago"),
    days_added_to: Optional[int] = Query(None, description="Filter addresses added at most X days ago"),
    sort_by: str = Query("created_at", regex="^(id|wallet_address|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить все адреса в whitelist альфа-теста"""
    
    # Базовый запрос
    query = select(AlphaTestAccess)
    
    # Применяем фильтры
    if id is not None:
        query = query.where(AlphaTestAccess.id == id)
    
    if wallet_address:
        query = query.where(AlphaTestAccess.wallet_address.ilike(f"%{wallet_address.lower()}%"))
    
    if created_from:
        query = query.where(AlphaTestAccess.created_at >= created_from)
    
    if created_to:
        query = query.where(AlphaTestAccess.created_at <= created_to)
    
    if days_added_from is not None:
        cutoff_date = datetime.utcnow() - timedelta(days=days_added_from)
        query = query.where(AlphaTestAccess.created_at <= cutoff_date)
    
    if days_added_to is not None:
        cutoff_date = datetime.utcnow() - timedelta(days=days_added_to)
        query = query.where(AlphaTestAccess.created_at >= cutoff_date)
    
    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(AlphaTestAccess, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    addresses = result.scalars().all()
    
    # Формируем результат
    items = []
    for address in addresses:
        days_since_added = (datetime.utcnow() - address.created_at).days
        address_dict = {
            "id": address.id,
            "wallet_address": address.wallet_address,
            "created_at": address.created_at,
            "wallet_short": f"{address.wallet_address[:6]}...{address.wallet_address[-4:]}",
            "days_since_added": days_since_added
        }
        items.append(AlphaTestAccessResponse(**address_dict))
    
    return PaginatedAlphaTestResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )


@router.get("/{access_id}", response_model=AlphaTestAccessResponse)
async def get_alpha_test_access(
    access_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретный адрес по ID"""
    query = select(AlphaTestAccess).where(AlphaTestAccess.id == access_id)
    result = await db.execute(query)
    address = result.scalar_one_or_none()
    
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    days_since_added = (datetime.utcnow() - address.created_at).days
    address_dict = {
        "id": address.id,
        "wallet_address": address.wallet_address,
        "created_at": address.created_at,
        "wallet_short": f"{address.wallet_address[:6]}...{address.wallet_address[-4:]}",
        "days_since_added": days_since_added
    }
    
    return AlphaTestAccessResponse(**address_dict)


@router.post("/", response_model=AlphaTestAccessResponse, status_code=status.HTTP_201_CREATED)
async def add_alpha_test_access(
    access_data: AlphaTestAccessCreate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Добавить новый адрес в whitelist"""
    
    # Проверяем, не существует ли уже такой адрес
    existing_query = select(AlphaTestAccess).where(
        AlphaTestAccess.wallet_address == access_data.wallet_address
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Wallet address '{access_data.wallet_address}' already in whitelist"
        )
    
    # Создаём новую запись
    new_access = AlphaTestAccess(
        wallet_address=access_data.wallet_address,
        created_at=datetime.utcnow()
    )
    
    db.add(new_access)
    await db.commit()
    await db.refresh(new_access)
    
    address_dict = {
        "id": new_access.id,
        "wallet_address": new_access.wallet_address,
        "created_at": new_access.created_at,
        "wallet_short": f"{new_access.wallet_address[:6]}...{new_access.wallet_address[-4:]}",
        "days_since_added": 0
    }
    
    return AlphaTestAccessResponse(**address_dict)


@router.delete("/{access_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alpha_test_access(
    access_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Удалить адрес из whitelist"""
    query = select(AlphaTestAccess).where(AlphaTestAccess.id == access_id)
    result = await db.execute(query)
    address = result.scalar_one_or_none()
    
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    await db.delete(address)
    await db.commit()
    
    return None


@router.get("/stats/summary")
async def get_alpha_test_summary(
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику по whitelist"""
    
    # Общее количество адресов
    total_query = select(func.count()).select_from(AlphaTestAccess)
    total_result = await db.execute(total_query)
    total_addresses = total_result.scalar()
    
    # Добавлено за последнюю неделю
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_query = select(func.count()).select_from(AlphaTestAccess).where(
        AlphaTestAccess.created_at >= week_ago
    )
    week_result = await db.execute(week_query)
    recent_additions = week_result.scalar()
    
    # Добавлено за последние 24 часа
    day_ago = datetime.utcnow() - timedelta(days=1)
    day_query = select(func.count()).select_from(AlphaTestAccess).where(
        AlphaTestAccess.created_at >= day_ago
    )
    day_result = await db.execute(day_query)
    daily_additions = day_result.scalar()
    
    return {
        "total_addresses": total_addresses,
        "recent_additions_7d": recent_additions,
        "recent_additions_24h": daily_additions
    }


@router.post("/bulk", response_model=dict)
async def bulk_add_alpha_test_access(
    wallet_addresses: List[str],
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Добавить несколько адресов в whitelist за раз"""
    
    added = []
    skipped = []
    errors = []
    
    for wallet in wallet_addresses:
        try:
            # Валидация
            wallet = wallet.strip().lower()
            if not wallet.startswith('0x') or len(wallet) != 42:
                errors.append({"wallet": wallet, "reason": "Invalid format"})
                continue
            
            # Проверяем существование
            existing_query = select(AlphaTestAccess).where(
                AlphaTestAccess.wallet_address == wallet
            )
            existing_result = await db.execute(existing_query)
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                skipped.append(wallet)
                continue
            
            # Добавляем
            new_access = AlphaTestAccess(
                wallet_address=wallet,
                created_at=datetime.utcnow()
            )
            db.add(new_access)
            added.append(wallet)
            
        except Exception as e:
            errors.append({"wallet": wallet, "reason": str(e)})
    
    await db.commit()
    
    return {
        "added": len(added),
        "skipped": len(skipped),
        "errors": len(errors),
        "added_addresses": added,
        "skipped_addresses": skipped,
        "error_details": errors
    }