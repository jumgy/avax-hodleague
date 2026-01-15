from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from datetime import datetime

from models.database import get_async_db
from models.reward_models import UserReward, ClaimStatus, RewardType
from models.user_models import User
from .auth import verify_admin_token

# --- Pydantic models ---

class UserRewardResponse(BaseModel):
    id: int
    user_id: int
    reward_type_id: int
    amount: Decimal
    tournament_result_id: Optional[int]
    earned_at: datetime
    claimed_at: Optional[datetime]
    claim_status: str
    expires_at: Optional[datetime]
    extra_data: Optional[dict]
    
    # Дополнительная информация из связанных таблиц
    user_nickname: Optional[str] = None 
    reward_type_name: Optional[str] = None
    reward_category: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class PaginatedUserRewardResponse(BaseModel):
    items: List[UserRewardResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

# --- Router ---

router = APIRouter(prefix="/panel/user-rewards")

@router.get("/", response_model=PaginatedUserRewardResponse)
async def get_user_rewards(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None, description="Filter by reward ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    reward_type_id: Optional[int] = Query(None, description="Filter by reward type ID"),
    tournament_result_id: Optional[int] = Query(None, description="Filter by tournament result ID"),
    claim_status: Optional[str] = Query(None, description="Filter by claim status"),
    amount_from: Optional[Decimal] = Query(None),
    amount_to: Optional[Decimal] = Query(None),
    earned_from: Optional[datetime] = Query(None, description="Filter earned_at from date"),
    earned_to: Optional[datetime] = Query(None, description="Filter earned_at to date"),
    claimed_from: Optional[datetime] = Query(None),
    claimed_to: Optional[datetime] = Query(None),
    expires_from: Optional[datetime] = Query(None),
    expires_to: Optional[datetime] = Query(None),
    is_expired: Optional[bool] = Query(None, description="Filter expired rewards (expires_at < now)"),
    is_claimed: Optional[bool] = Query(None, description="Filter claimed/unclaimed rewards"),
    nickname: Optional[str] = Query(None, description="Search by nickname"),
    reward_type_name: Optional[str] = Query(None, description="Search by reward type name"),
    sort_by: str = Query("earned_at", regex="^(id|user_id|reward_type_id|amount|earned_at|claimed_at|claim_status|expires_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все награды пользователей с фильтрацией, сортировкой и пагинацией
    """
    # Базовый запрос с загрузкой связанных данных
    query = select(UserReward).options(
        joinedload(UserReward.user),
        joinedload(UserReward.reward_type)
    )
    
    # Применяем фильтры
    if id is not None:
        query = query.where(UserReward.id == id)
    
    if user_id is not None:
        query = query.where(UserReward.user_id == user_id)
    
    if reward_type_id is not None:
        query = query.where(UserReward.reward_type_id == reward_type_id)
    
    if tournament_result_id is not None:
        query = query.where(UserReward.tournament_result_id == tournament_result_id)
    
    if claim_status:
        if not ClaimStatus.is_valid(claim_status):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid claim status. Must be one of: {ClaimStatus.ALL_STATUSES}"
            )
        query = query.where(UserReward.claim_status == claim_status)
    
    if amount_from is not None:
        query = query.where(UserReward.amount >= amount_from)
    
    if amount_to is not None:
        query = query.where(UserReward.amount <= amount_to)
    
    if earned_from:
        query = query.where(UserReward.earned_at >= earned_from)
    
    if earned_to:
        query = query.where(UserReward.earned_at <= earned_to)
    
    if claimed_from:
        query = query.where(UserReward.claimed_at >= claimed_from)
    
    if claimed_to:
        query = query.where(UserReward.claimed_at <= claimed_to)
    
    if expires_from:
        query = query.where(UserReward.expires_at >= expires_from)
    
    if expires_to:
        query = query.where(UserReward.expires_at <= expires_to)
    
    if is_expired is not None:
        if is_expired:
            query = query.where(UserReward.expires_at < datetime.now())
        else:
            query = query.where(
                (UserReward.expires_at.is_(None)) | (UserReward.expires_at >= datetime.now())
            )
    
    if is_claimed is not None:
        if is_claimed:
            query = query.where(UserReward.claim_status == ClaimStatus.CLAIMED)
        else:
            query = query.where(UserReward.claim_status != ClaimStatus.CLAIMED)
    
    # Фильтры по связанным таблицам
    if nickname:
        query = query.join(User).where(User.nickname.ilike(f"%{nickname}%"))
    
    if reward_type_name:
        query = query.join(RewardType).where(RewardType.name.ilike(f"%{reward_type_name}%"))
    
    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(UserReward, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items_raw = result.unique().scalars().all()
    
    # Форматируем ответ с дополнительными данными
    items = []
    for reward in items_raw:
        item_dict = {
            "id": reward.id,
            "user_id": reward.user_id,
            "reward_type_id": reward.reward_type_id,
            "amount": reward.amount,
            "tournament_result_id": reward.tournament_result_id,
            "earned_at": reward.earned_at,
            "claimed_at": reward.claimed_at,
            "claim_status": reward.claim_status,
            "expires_at": reward.expires_at,
            "extra_data": reward.extra_data,
            "user_nickname": reward.user.nickname if reward.user else None,
            "reward_type_name": reward.reward_type.name if reward.reward_type else None,
            "reward_category": reward.reward_type.reward_category if reward.reward_type else None,
        }
        items.append(UserRewardResponse(**item_dict))
    
    return PaginatedUserRewardResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{reward_id}", response_model=UserRewardResponse)
async def get_user_reward(
    reward_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретную награду пользователя по ID"""
    query = select(UserReward).options(
        joinedload(UserReward.user),
        joinedload(UserReward.reward_type)
    ).where(UserReward.id == reward_id)
    
    result = await db.execute(query)
    obj = result.unique().scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="User reward not found")
    
    return UserRewardResponse(
        id=obj.id,
        user_id=obj.user_id,
        reward_type_id=obj.reward_type_id,
        amount=obj.amount,
        tournament_result_id=obj.tournament_result_id,
        earned_at=obj.earned_at,
        claimed_at=obj.claimed_at,
        claim_status=obj.claim_status,
        expires_at=obj.expires_at,
        extra_data=obj.extra_data,
        user_nickname=obj.user.nickname if obj.user else None,
        reward_type_name=obj.reward_type.name if obj.reward_type else None,
        reward_category=obj.reward_type.reward_category if obj.reward_type else None,
    )