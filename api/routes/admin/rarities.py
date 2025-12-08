from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime
import re

from models.database import get_sync_db
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

router = APIRouter(prefix="/panel/rarities")

@router.get("/", response_model=PaginatedRarityResponse)
async def get_all_rarities(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    active_only: Optional[bool] = Query(None, description="Filter only active rarities"),
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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    query = db.query(Rarity)

    if id is not None:
        query = query.filter(Rarity.id == id)
    if active_only is True:
        query = query.filter(Rarity.is_active == True)
    elif active_only is False:
        query = query.filter(Rarity.is_active == False)
    if name:
        query = query.filter(Rarity.name.ilike(f"%{name}%"))
    if description:
        query = query.filter(Rarity.description.ilike(f"%{description}%"))
    if color:
        query = query.filter(Rarity.color == color.upper())
    if score_bonus_from is not None:
        query = query.filter(Rarity.score_bonus >= score_bonus_from)
    if score_bonus_to is not None:
        query = query.filter(Rarity.score_bonus <= score_bonus_to)
    if created_from:
        query = query.filter(Rarity.created_at >= created_from)
    if created_to:
        query = query.filter(Rarity.created_at <= created_to)
    if updated_from:
        query = query.filter(Rarity.updated_at >= updated_from)
    if updated_to:
        query = query.filter(Rarity.updated_at <= updated_to)

    total = query.count()

    sort_column = getattr(Rarity, sort_by)
    query = query.order_by(sort_column.desc()) if sort_order == "desc" else query.order_by(sort_column.asc())

    rarities = query.offset(skip).limit(limit).all()

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
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    rarity = db.query(Rarity).filter(Rarity.id == rarity_id).first()
    if not rarity:
        raise HTTPException(status_code=404, detail="Rarity not found")
    return rarity

@router.post("/", response_model=RarityResponse, status_code=status.HTTP_201_CREATED)
async def create_rarity(
    rarity_data: RarityCreate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    existing = db.query(Rarity).filter(Rarity.name.ilike(rarity_data.name)).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Rarity with name '{rarity_data.name}' already exists"
        )

    new_rarity = Rarity(
        name=rarity_data.name,
        description=rarity_data.description,
        score_bonus=rarity_data.score_bonus,
        color=rarity_data.color,
        is_active=rarity_data.is_active
    )

    db.add(new_rarity)
    db.commit()
    db.refresh(new_rarity)
    return new_rarity

@router.put("/{rarity_id}", response_model=RarityResponse)
async def update_rarity(
    rarity_id: int,
    rarity_data: RarityUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    rarity = db.query(Rarity).filter(Rarity.id == rarity_id).first()
    if not rarity:
        raise HTTPException(status_code=404, detail="Rarity not found")

    if rarity_data.name and rarity_data.name.lower() != rarity.name.lower():
        existing = db.query(Rarity).filter(Rarity.name.ilike(rarity_data.name)).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Rarity with name '{rarity_data.name}' already exists"
            )

    if rarity_data.is_active is False and rarity.is_active:
        active_cards_count = db.query(Card).filter(
            Card.rarity_id == rarity_id,
            Card.is_active == True
        ).count()
        if active_cards_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot deactivate rarity '{rarity.name}'. It is currently used by {active_cards_count} active card(s). Please deactivate or change rarity of all cards first."
            )

    update_data = rarity_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rarity, field, value)

    rarity.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rarity)
    return rarity

@router.get("/stats/summary")
async def get_rarities_summary(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    from sqlalchemy import func
    
    total_rarities = db.query(Rarity).count()
    active_rarities = db.query(Rarity).filter(Rarity.is_active == True).count()
    inactive_rarities = total_rarities - active_rarities

    score_stats = db.query(
        func.avg(Rarity.score_bonus).label('avg_score'),
        func.max(Rarity.score_bonus).label('max_score')
    ).filter(Rarity.is_active == True).first()

    avg_score_bonus = float(score_stats.avg_score) if score_stats.avg_score else 0
    max_score_bonus = score_stats.max_score if score_stats.max_score else 0

    recent_rarities = db.query(Rarity).order_by(
        Rarity.created_at.desc()
    ).limit(5).all()

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