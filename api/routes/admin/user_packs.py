from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, date

from models.database import get_sync_db
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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token),
):
    query = db.query(UserPack)

    if user_id:
        query = query.filter(UserPack.user_id == user_id)
    if pack_type_id:
        query = query.filter(UserPack.pack_type_id == pack_type_id)
    if is_opened is not None:
        query = query.filter(UserPack.is_opened == is_opened)
    if source:
        query = query.filter(UserPack.source == source)
    if obtained_from:
        query = query.filter(UserPack.obtained_at >= obtained_from)
    if obtained_to:
        query = query.filter(UserPack.obtained_at < obtained_to)
    if created_from:
        query = query.filter(UserPack.created_at >= created_from)
    if created_to:
        query = query.filter(UserPack.created_at < created_to)

    total = query.count()

    sort_column = getattr(UserPack, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    items = query.offset(skip).limit(limit).all()

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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token),
):
    obj = db.query(UserPack).filter(UserPack.id == user_pack_id).first()
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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token),
):
    query = db.query(PackOpening)

    if user_id:
        query = query.filter(PackOpening.user_id == user_id)
    if pack_id:
        query = query.filter(PackOpening.pack_id == pack_id)
    if cards_count_min is not None:
        query = query.filter(PackOpening.cards_count >= cards_count_min)
    if cards_count_max is not None:
        query = query.filter(PackOpening.cards_count <= cards_count_max)
    if has_transaction is True:
        query = query.filter(PackOpening.transaction_hash.isnot(None))
    elif has_transaction is False:
        query = query.filter(PackOpening.transaction_hash.is_(None))
    if opened_from:
        query = query.filter(PackOpening.opened_at >= opened_from)
    if opened_to:
        query = query.filter(PackOpening.opened_at < opened_to)

    total = query.count()

    sort_column = getattr(PackOpening, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    items = query.offset(skip).limit(limit).all()

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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token),
):
    obj = db.query(PackOpening).filter(PackOpening.id == opening_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="PackOpening not found")
    return obj