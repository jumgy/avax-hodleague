from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, date

from models.database import get_sync_db
from models.user_card_models import UserCard
from .auth import verify_admin_token

class UserCardResponse(BaseModel):
    id: int
    user_id: int
    card_id: int
    pack_opening_id: Optional[int]
    obtained_at: datetime
    expires_at: Optional[datetime]
    source: str
    status: str
    is_active: bool
    transaction_hash: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedUserCardsResponse(BaseModel):
    items: List[UserCardResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/panel/user-cards")

@router.get("/", response_model=PaginatedUserCardsResponse)
async def get_user_cards(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user_id: Optional[int] = Query(None),
    card_id: Optional[int] = Query(None),
    pack_opening_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    obtained_from: Optional[date] = Query(None),
    obtained_to: Optional[date] = Query(None),
    created_from: Optional[date] = Query(None),
    created_to: Optional[date] = Query(None),
    has_transaction: Optional[bool] = Query(None),
    sort_by: str = Query("created_at", regex="^(id|user_id|card_id|obtained_at|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token),
):
    query = db.query(UserCard)

    if user_id:
        query = query.filter(UserCard.user_id == user_id)
    if card_id:
        query = query.filter(UserCard.card_id == card_id)
    if pack_opening_id:
        query = query.filter(UserCard.pack_opening_id == pack_opening_id)
    if status:
        query = query.filter(UserCard.status == status)
    if source:
        query = query.filter(UserCard.source == source)
    if is_active is not None:
        query = query.filter(UserCard.is_active == is_active)
    if obtained_from:
        query = query.filter(UserCard.obtained_at >= obtained_from)
    if obtained_to:
        query = query.filter(UserCard.obtained_at < obtained_to)
    if created_from:
        query = query.filter(UserCard.created_at >= created_from)
    if created_to:
        query = query.filter(UserCard.created_at < created_to)
    if has_transaction is True:
        query = query.filter(UserCard.transaction_hash.isnot(None))
    elif has_transaction is False:
        query = query.filter(UserCard.transaction_hash.is_(None))

    total = query.count()

    sort_column = getattr(UserCard, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    items = query.offset(skip).limit(limit).all()

    return PaginatedUserCardsResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/{user_card_id}", response_model=UserCardResponse)
async def get_user_card(
    user_card_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token),
):
    obj = db.query(UserCard).filter(UserCard.id == user_card_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="UserCard not found")
    return obj