from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from decimal import Decimal
from datetime import datetime

from models.database import get_sync_db
from models.tournament_models import Tournament
from models.tournament_deck_models import TournamentPrizeConfig
from models.reward_models import RewardType
from .auth import verify_admin_token

class TournamentPrizeConfigCreate(BaseModel):
    tournament_id: int
    position_from: int
    position_to: int
    reward_type_id: int
    reward_amount: Decimal

    @validator('position_from', 'position_to')
    def positions_valid(cls, v):
        if v < 1:
            raise ValueError("position must be >= 1")
        return v

    @validator('reward_amount')
    def reward_amount_valid(cls, v):
        if v < 0 or v > Decimal("999999999999.99999999"):
            raise ValueError("reward_amount invalid")
        return v

    @validator('position_to')
    def positions_order(cls, v, values):
        pf = values.get('position_from')
        if pf and v < pf:
            raise ValueError('position_to must be >= position_from')
        return v

class TournamentPrizeConfigUpdate(BaseModel):
    position_from: Optional[int]
    position_to: Optional[int]
    reward_type_id: Optional[int]
    reward_amount: Optional[Decimal]

    @validator('position_from', 'position_to')
    def positions_valid(cls, v):
        if v is not None and v < 1:
            raise ValueError("position must be >= 1")
        return v

    @validator('reward_amount')
    def reward_amount_valid(cls, v):
        if v is not None and (v < 0 or v > Decimal("999999999999.99999999")):
            raise ValueError("reward_amount invalid")
        return v

    @validator('position_to')
    def positions_order(cls, v, values):
        pf = values.get('position_from')
        if pf is not None and v is not None and v < pf:
            raise ValueError('position_to must be >= position_from')
        return v

class TournamentPrizeConfigResponse(BaseModel):
    id: int
    tournament_id: int
    position_from: int
    position_to: int
    reward_type_id: int
    reward_amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedTournamentPrizeConfigResponse(BaseModel):
    items: List[TournamentPrizeConfigResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/panel/tournament-prizes")

@router.get("/", response_model=PaginatedTournamentPrizeConfigResponse)
async def get_tournament_prize_configs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    id: Optional[int] = Query(None),
    tournament_id: Optional[int] = Query(None),
    position_from: Optional[int] = Query(None),
    position_to: Optional[int] = Query(None),
    reward_type_id: Optional[int] = Query(None),
    reward_amount_from: Optional[Decimal] = Query(None),
    reward_amount_to: Optional[Decimal] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    sort_by: str = Query("position_from", regex="^(id|tournament_id|position_from|position_to|reward_type_id|reward_amount|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    query = db.query(TournamentPrizeConfig).options(
        joinedload(TournamentPrizeConfig.tournament),
        joinedload(TournamentPrizeConfig.reward_type)
    )

    if id is not None:
        query = query.filter(TournamentPrizeConfig.id == id)
    if tournament_id is not None:
        query = query.filter(TournamentPrizeConfig.tournament_id == tournament_id)
    if position_from is not None:
        query = query.filter(TournamentPrizeConfig.position_from >= position_from)
    if position_to is not None:
        query = query.filter(TournamentPrizeConfig.position_to <= position_to)
    if reward_type_id is not None:
        query = query.filter(TournamentPrizeConfig.reward_type_id == reward_type_id)
    if reward_amount_from is not None:
        query = query.filter(TournamentPrizeConfig.reward_amount >= reward_amount_from)
    if reward_amount_to is not None:
        query = query.filter(TournamentPrizeConfig.reward_amount <= reward_amount_to)
    if created_from is not None:
        query = query.filter(TournamentPrizeConfig.created_at >= created_from)
    if created_to is not None:
        query = query.filter(TournamentPrizeConfig.created_at <= created_to)

    total = query.count()

    sort_column = getattr(TournamentPrizeConfig, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    results = query.offset(skip).limit(limit).all()

    return PaginatedTournamentPrizeConfigResponse(
        items=results,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0,
    )

@router.get("/{prize_id}", response_model=TournamentPrizeConfigResponse)
async def get_tournament_prize_config(
    prize_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    obj = db.query(TournamentPrizeConfig).options(
        joinedload(TournamentPrizeConfig.tournament),
        joinedload(TournamentPrizeConfig.reward_type)
    ).filter(TournamentPrizeConfig.id == prize_id).first()

    if not obj:
        raise HTTPException(status_code=404, detail="TournamentPrizeConfig not found")
    return obj

@router.post("/", response_model=TournamentPrizeConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_tournament_prize_config(
    data: TournamentPrizeConfigCreate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    tournament = db.query(Tournament).filter(Tournament.id == data.tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.status != "registration":
        raise HTTPException(status_code=409, detail="Cannot add prizes for tournaments that have started or finished.")
    
    reward_type = db.query(RewardType).filter(
        RewardType.id == data.reward_type_id,
        RewardType.is_active == True
    ).first()
    if not reward_type:
        raise HTTPException(status_code=404, detail="Reward type not found or inactive")

    existing_prize = db.query(TournamentPrizeConfig).filter(
        TournamentPrizeConfig.tournament_id == data.tournament_id,
        TournamentPrizeConfig.position_from <= data.position_to,
        TournamentPrizeConfig.position_to >= data.position_from
    ).first()
    
    if existing_prize:
        raise HTTPException(
            status_code=400, 
            detail=f"Position range {data.position_from}-{data.position_to} overlaps with existing prize configuration"
        )

    obj = TournamentPrizeConfig(
        tournament_id=data.tournament_id,
        position_from=data.position_from,
        position_to=data.position_to,
        reward_type_id=data.reward_type_id,
        reward_amount=data.reward_amount,
    )

    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@router.put("/{prize_id}", response_model=TournamentPrizeConfigResponse)
async def update_tournament_prize_config(
    prize_id: int,
    data: TournamentPrizeConfigUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    obj = db.query(TournamentPrizeConfig).options(
        joinedload(TournamentPrizeConfig.tournament),
        joinedload(TournamentPrizeConfig.reward_type)
    ).filter(TournamentPrizeConfig.id == prize_id).first()
    
    if not obj:
        raise HTTPException(status_code=404, detail="TournamentPrizeConfig not found")

    if not obj.tournament or obj.tournament.status != "registration":
        raise HTTPException(status_code=409, detail="Can edit prizes only when tournament in registration state")

    if data.reward_type_id:
        reward_type = db.query(RewardType).filter(
            RewardType.id == data.reward_type_id,
            RewardType.is_active == True
        ).first()
        if not reward_type:
            raise HTTPException(status_code=404, detail="Reward type not found or inactive")

    if data.position_from is not None or data.position_to is not None:
        new_position_from = data.position_from or obj.position_from
        new_position_to = data.position_to or obj.position_to
        
        existing_prize = db.query(TournamentPrizeConfig).filter(
            TournamentPrizeConfig.tournament_id == obj.tournament_id,
            TournamentPrizeConfig.id != prize_id,
            TournamentPrizeConfig.position_from <= new_position_to,
            TournamentPrizeConfig.position_to >= new_position_from
        ).first()
        
        if existing_prize:
            raise HTTPException(
                status_code=400, 
                detail=f"Position range {new_position_from}-{new_position_to} overlaps with existing prize configuration"
            )

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj