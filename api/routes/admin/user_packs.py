from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, date

from models.database import get_async_db
from models.user_pack_models import UserPack, PackOpening
from .auth import verify_admin_token

class UserPackResponse(BaseModel):
    id: int
    user_id: int
    pack_type_id: int
    obtained_at: datetime
    is_opened: bool
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PackOpeningResponse(BaseModel):
    id: int
    user_id: int
    pack_id: int
    opened_at: datetime
    cards_count: int
    transaction_hash: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class PaginatedUserPacksResponse(BaseModel):
    items: List[UserPackResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

class PaginatedPackOpeningsResponse(BaseModel):
    items: List[PackOpeningResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/panel/user-packs")

@router.get("/", response_model=PaginatedUserPacksResponse)
async def get_user_packs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user_id: Optional[int] = Query(None),
    pack_type_id: Optional[int] = Query(None),
    is_opened: Optional[bool] = Query(None),
    source: Optional[str] = Query(None),
    obtained_from: Optional[date] = Query(None),
    obtained_to: Optional[date] = Query(None),
    created_from: Optional[date] = Query(None),
    created_to: Optional[date] = Query(None),
    sort_by: str = Query("created_at", regex="^(id|user_id|pack_type_id|obtained_at|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    """Get user packs with filtering, sorting and pagination."""
    query = select(UserPack)

    # Apply filters
    if user_id:
        query = query.where(UserPack.user_id == user_id)
    if pack_type_id:
        query = query.where(UserPack.pack_type_id == pack_type_id)
    if is_opened is not None:
        query = query.where(UserPack.is_opened == is_opened)
    if source:
        query = query.where(UserPack.source == source)
    if obtained_from:
        query = query.where(UserPack.obtained_at >= obtained_from)
    if obtained_to:
        query = query.where(UserPack.obtained_at < obtained_to)
    if created_from:
        query = query.where(UserPack.created_at >= created_from)
    if created_to:
        query = query.where(UserPack.created_at < created_to)

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply sort
    sort_column = getattr(UserPack, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Paginate and execute
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedUserPacksResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{user_pack_id}", response_model=UserPackResponse)
async def get_user_pack(
    user_pack_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    """Get user pack by ID."""
    query = select(UserPack).where(UserPack.id == user_pack_id)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="UserPack not found")
    
    return obj

@router.get("/openings/", response_model=PaginatedPackOpeningsResponse)
async def get_pack_openings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user_id: Optional[int] = Query(None),
    pack_id: Optional[int] = Query(None),
    cards_count_min: Optional[int] = Query(None, ge=0),
    cards_count_max: Optional[int] = Query(None, ge=0),
    has_transaction: Optional[bool] = Query(None),
    opened_from: Optional[date] = Query(None),
    opened_to: Optional[date] = Query(None),
    sort_by: str = Query("opened_at", regex="^(id|user_id|pack_id|opened_at|cards_count)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    """Get pack openings with filtering, sorting and pagination."""
    query = select(PackOpening)

    # Apply filters
    if user_id:
        query = query.where(PackOpening.user_id == user_id)
    if pack_id:
        query = query.where(PackOpening.pack_id == pack_id)
    if cards_count_min is not None:
        query = query.where(PackOpening.cards_count >= cards_count_min)
    if cards_count_max is not None:
        query = query.where(PackOpening.cards_count <= cards_count_max)
    if has_transaction is True:
        query = query.where(PackOpening.transaction_hash.isnot(None))
    elif has_transaction is False:
        query = query.where(PackOpening.transaction_hash.is_(None))
    if opened_from:
        query = query.where(PackOpening.opened_at >= opened_from)
    if opened_to:
        query = query.where(PackOpening.opened_at < opened_to)

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply sort
    sort_column = getattr(PackOpening, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Paginate and execute
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedPackOpeningsResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/openings/{opening_id}", response_model=PackOpeningResponse)
async def get_pack_opening(
    opening_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    """Get pack opening by ID."""
    query = select(PackOpening).where(PackOpening.id == opening_id)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="PackOpening not found")
    
    return obj