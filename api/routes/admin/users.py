from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime, timedelta

from models.database import get_async_db
from models.user_models import User
from .auth import verify_admin_token

class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    referral_route: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('nickname')
    def validate_nickname(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2 or len(v) > 50:
                raise ValueError('Nickname must be between 2 and 50 characters')
        return v

    @validator('referral_route')
    def validate_referral_route(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 4 or len(v) > 20:
                raise ValueError('Referral route must be between 4 and 20 characters')
        return v

    @validator('avatar_url')
    def validate_avatar_url(cls, v):
        if v is not None:
            v = v.strip()
            if not v.startswith(('http://', 'https://')):
                raise ValueError('Avatar URL must start with http:// or https://')
        return v

class UserResponse(BaseModel):
    id: int
    wallet_address: str
    nickname: str
    referral_route: str
    avatar_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    wallet_short: str
    days_since_registration: int

    model_config = ConfigDict(from_attributes=True)

class PaginatedUserResponse(BaseModel):
    items: List[UserResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/panel/users")

@router.get("/", response_model=PaginatedUserResponse)
async def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None, description="Filter by active status (true=active, false=inactive, null=all)"),
    search: Optional[str] = Query(None, description="Search by nickname, wallet address, or referral route"),
    wallet_address: Optional[str] = Query(None, description="Filter by wallet address"),
    nickname: Optional[str] = Query(None, description="Search by nickname"),
    referral_route: Optional[str] = Query(None, description="Search by referral route"),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    updated_from: Optional[datetime] = Query(None),
    updated_to: Optional[datetime] = Query(None),
    days_registered_from: Optional[int] = Query(None, description="Filter users registered at least X days ago"),
    days_registered_to: Optional[int] = Query(None, description="Filter users registered at most X days ago"),
    sort_by: str = Query("created_at", regex="^(id|wallet_address|nickname|referral_route|is_active|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить всех пользователей с фильтрацией, сортировкой и пагинацией"""
    # Базовый запрос
    query = select(User)

    # Применяем фильтры
    if id is not None:
        query = query.where(User.id == id)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(
            or_(
                User.nickname.ilike(search_term),
                User.wallet_address.ilike(search_term),
                User.referral_route.ilike(search_term)
            )
        )
    if wallet_address:
        query = query.where(User.wallet_address.ilike(f"%{wallet_address}%"))
    if nickname:
        query = query.where(User.nickname.ilike(f"%{nickname}%"))
    if referral_route:
        query = query.where(User.referral_route.ilike(f"%{referral_route}%"))
    if created_from:
        query = query.where(User.created_at >= created_from)
    if created_to:
        query = query.where(User.created_at <= created_to)
    if updated_from:
        query = query.where(User.updated_at >= updated_from)
    if updated_to:
        query = query.where(User.updated_at <= updated_to)
    if days_registered_from is not None:
        cutoff_date = datetime.utcnow() - timedelta(days=days_registered_from)
        query = query.where(User.created_at <= cutoff_date)
    if days_registered_to is not None:
        cutoff_date = datetime.utcnow() - timedelta(days=days_registered_to)
        query = query.where(User.created_at >= cutoff_date)

    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Применяем сортировку
    sort_column = getattr(User, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    # Формируем результат
    items = []
    for user in users:
        days_since_registration = (datetime.utcnow() - user.created_at).days
        user_dict = {
            "id": user.id,
            "wallet_address": user.wallet_address,
            "nickname": user.nickname,
            "referral_route": user.referral_route,
            "avatar_url": user.avatar_url,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "wallet_short": f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}",
            "days_since_registration": days_since_registration
        }
        items.append(UserResponse(**user_dict))

    return PaginatedUserResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретного пользователя по ID"""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    days_since_registration = (datetime.utcnow() - user.created_at).days
    user_dict = {
        "id": user.id,
        "wallet_address": user.wallet_address,
        "nickname": user.nickname,
        "referral_route": user.referral_route,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "wallet_short": f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}",
        "days_since_registration": days_since_registration
    }

    return UserResponse(**user_dict)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить пользователя"""
    # Получаем пользователя
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Проверяем уникальность nickname
    if user_data.nickname and user_data.nickname != user.nickname:
        existing_query = select(User).where(User.nickname == user_data.nickname)
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"User with nickname '{user_data.nickname}' already exists"
            )

    # Проверяем уникальность referral_route
    if user_data.referral_route and user_data.referral_route != user.referral_route:
        existing_query = select(User).where(User.referral_route == user_data.referral_route)
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Referral route '{user_data.referral_route}' already exists"
            )

    # Применяем обновления
    update_data = user_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)

    days_since_registration = (datetime.utcnow() - user.created_at).days
    user_dict = {
        "id": user.id,
        "wallet_address": user.wallet_address,
        "nickname": user.nickname,
        "referral_route": user.referral_route,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "wallet_short": f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}",
        "days_since_registration": days_since_registration
    }

    return UserResponse(**user_dict)

@router.get("/stats/summary")
async def get_users_summary(
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику по пользователям"""
    # Общее количество пользователей
    total_query = select(func.count()).select_from(User)
    total_result = await db.execute(total_query)
    total_users = total_result.scalar()

    # Активные пользователи
    active_query = select(func.count()).select_from(User).where(User.is_active == True)
    active_result = await db.execute(active_query)
    active_users = active_result.scalar()

    inactive_users = total_users - active_users

    # Регистрации за последнюю неделю
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_query = select(func.count()).select_from(User).where(User.created_at >= week_ago)
    week_result = await db.execute(week_query)
    recent_registrations = week_result.scalar()

    # Регистрации за последние 24 часа
    day_ago = datetime.utcnow() - timedelta(days=1)
    day_query = select(func.count()).select_from(User).where(User.created_at >= day_ago)
    day_result = await db.execute(day_query)
    daily_registrations = day_result.scalar()

    # Популярные префиксы никнеймов (сырой SQL запрос)
    popular_prefixes_result = await db.execute(text("""
        SELECT LEFT(nickname, 3) as prefix, COUNT(*) as count 
        FROM users 
        WHERE is_active = true 
        GROUP BY LEFT(nickname, 3) 
        ORDER BY count DESC 
        LIMIT 5
    """))
    popular_nickname_prefixes = popular_prefixes_result.fetchall()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "recent_registrations_7d": recent_registrations,
        "recent_registrations_24h": daily_registrations,
        "popular_nickname_prefixes": [
            {"prefix": row[0], "count": row[1]} 
            for row in popular_nickname_prefixes
        ]
    }

@router.get("/search/duplicates", tags=["User Management"])
async def find_duplicate_patterns(
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Найти паттерны дублирующихся пользователей"""
    # Похожие никнеймы
    similar_nicknames_result = await db.execute(text("""
        SELECT nickname, COUNT(*) as count
        FROM users 
        WHERE nickname SIMILAR TO 'Player[0-9]+' OR nickname SIMILAR TO 'TestUser[0-9]+'
        GROUP BY nickname 
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 10
    """))
    similar_nicknames = similar_nicknames_result.fetchall()

    # Подозрительные массовые регистрации
    suspicious_registrations_result = await db.execute(text("""
        SELECT DATE_TRUNC('minute', created_at) as minute_created, 
               COUNT(*) as count,
               ARRAY_AGG(nickname) as nicknames
        FROM users 
        GROUP BY DATE_TRUNC('minute', created_at)
        HAVING COUNT(*) > 5
        ORDER BY count DESC
        LIMIT 5
    """))
    suspicious_registrations = suspicious_registrations_result.fetchall()

    return {
        "duplicate_nicknames": [
            {"nickname": row[0], "count": row[1]} 
            for row in similar_nicknames
        ],
        "suspicious_mass_registrations": [
            {
                "minute": row[0].isoformat() if row[0] else None,
                "count": row[1],
                "sample_nicknames": row[2][:5] if row[2] else []
            }
            for row in suspicious_registrations
        ]
    }