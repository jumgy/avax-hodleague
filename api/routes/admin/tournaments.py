from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime, timedelta

from models.database import get_sync_db
from models.tournament_models import Tournament, TournamentStatus
from services.card_score_service import card_score_service
from .auth import verify_admin_token

class TournamentCreate(BaseModel):
    tournament_number: int
    status: str = TournamentStatus.REGISTRATION
    start_date: datetime
    end_date: datetime
    gameplay_start_date: datetime  # NEW FIELD
    weight_limit: int = 30

    @validator('tournament_number')
    def validate_tournament_number(cls, v):
        if v is None:
            raise ValueError('Tournament number is required')
        if v < 1:
            raise ValueError('Tournament number must be positive')
        return v

    @validator('status')
    def validate_status(cls, v):
        if not TournamentStatus.is_valid(v):
            raise ValueError(f'Status must be one of: {", ".join(TournamentStatus.ALL_STATUSES)}')
        return v

    @validator('start_date')
    def validate_start_date(cls, v):
        if v is None:
            raise ValueError('Start date is required')
        return v

    @validator('gameplay_start_date')
    def validate_gameplay_start_date(cls, v, values):
        if v is None:
            raise ValueError('Gameplay start date is required')
        if 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('Gameplay start date must be after start date')
        return v

    @validator('end_date')
    def validate_end_date(cls, v, values):
        if v is None:
            raise ValueError('End date is required')
        if 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
            if (v - values['start_date']).total_seconds() < 24 * 3600:
                raise ValueError('Tournament must be at least 1 day long')
        if 'gameplay_start_date' in values and values['gameplay_start_date']:
            if v <= values['gameplay_start_date']:
                raise ValueError('End date must be after gameplay start date')
        return v

    @validator('weight_limit')
    def validate_weight_limit(cls, v):
        if v is None:
            raise ValueError('Weight limit is required')
        if v < 1:
            raise ValueError('Weight limit must be positive')
        if v > 1000:
            raise ValueError('Weight limit cannot exceed 1000')
        return v

    @validator('status')
    def validate_status_for_gameplay_date(cls, v, values):
        """Cannot set status to 'registration' if gameplay_start_date already passed"""
        if v == TournamentStatus.REGISTRATION and 'gameplay_start_date' in values:
            if values['gameplay_start_date'] <= datetime.utcnow():
                raise ValueError("Cannot create tournament with 'registration' status if gameplay_start_date is in the past")
        return v


class TournamentUpdate(BaseModel):
    tournament_number: Optional[int] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    gameplay_start_date: Optional[datetime] = None  # NEW FIELD
    weight_limit: Optional[int] = None

    @validator('tournament_number')
    def validate_tournament_number(cls, v):
        if v is not None and v < 1:
            raise ValueError('Tournament number must be positive')
        return v

    @validator('status')
    def validate_status(cls, v):
        if v is not None and not TournamentStatus.is_valid(v):
            raise ValueError(f'Status must be one of: {", ".join(TournamentStatus.ALL_STATUSES)}')
        return v

    @validator('end_date')
    def validate_end_date(cls, v, values):
        if v is not None and 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
        return v

    @validator('weight_limit')
    def validate_weight_limit(cls, v):
        if v is not None:
            if v < 1:
                raise ValueError('Weight limit must be positive')
            if v > 1000:
                raise ValueError('Weight limit cannot exceed 1000')
        return v


class TournamentResponse(BaseModel):
    id: int
    tournament_number: int
    status: str
    start_date: datetime
    end_date: datetime
    gameplay_start_date: Optional[datetime]  # NEW FIELD
    weight_limit: int
    created_at: datetime
    updated_at: datetime
    is_active: bool
    duration_days: int

    model_config = ConfigDict(from_attributes=True)


class PaginatedTournamentResponse(BaseModel):
    items: List[TournamentResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool


class SnapshotResponse(BaseModel):
    tournament_id: int
    snapshot_created: bool
    tokens_count: int
    message: str


router = APIRouter(prefix="/panel/tournaments")

@router.get("/", response_model=PaginatedTournamentResponse)
async def get_all_tournaments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    id: Optional[int] = Query(None),
    tournament_number: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, description="Filter by tournament status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status (true=active, false=inactive, null=all)"),
    weight_limit_from: Optional[int] = Query(None),
    weight_limit_to: Optional[int] = Query(None),
    start_date_from: Optional[datetime] = Query(None),
    start_date_to: Optional[datetime] = Query(None),
    end_date_from: Optional[datetime] = Query(None),
    end_date_to: Optional[datetime] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    updated_from: Optional[datetime] = Query(None),
    updated_to: Optional[datetime] = Query(None),
    sort_by: str = Query("tournament_number", regex="^(id|tournament_number|status|start_date|end_date|weight_limit|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    query = db.query(Tournament)

    if id is not None:
        query = query.filter(Tournament.id == id)
    if tournament_number is not None:
        query = query.filter(Tournament.tournament_number == tournament_number)
    if status_filter:
        if not TournamentStatus.is_valid(status_filter):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter. Must be one of: {', '.join(TournamentStatus.ALL_STATUSES)}"
            )
        query = query.filter(Tournament.status == status_filter)
    if is_active is not None:
        query = query.filter(Tournament.is_active == is_active)
    if weight_limit_from is not None:
        query = query.filter(Tournament.weight_limit >= weight_limit_from)
    if weight_limit_to is not None:
        query = query.filter(Tournament.weight_limit <= weight_limit_to)
    if start_date_from:
        query = query.filter(Tournament.start_date >= start_date_from)
    if start_date_to:
        query = query.filter(Tournament.start_date <= start_date_to)
    if end_date_from:
        query = query.filter(Tournament.end_date >= end_date_from)
    if end_date_to:
        query = query.filter(Tournament.end_date <= end_date_to)
    if created_from:
        query = query.filter(Tournament.created_at >= created_from)
    if created_to:
        query = query.filter(Tournament.created_at <= created_to)
    if updated_from:
        query = query.filter(Tournament.updated_at >= updated_from)
    if updated_to:
        query = query.filter(Tournament.updated_at <= updated_to)

    total = query.count()

    sort_column = getattr(Tournament, sort_by)
    query = query.order_by(sort_column.desc()) if sort_order == "desc" else query.order_by(sort_column.asc())

    tournaments = query.offset(skip).limit(limit).all()

    result = []
    for t in tournaments:
        tournament_dict = {
            "id": t.id,
            "tournament_number": t.tournament_number,
            "status": t.status,
            "start_date": t.start_date,
            "end_date": t.end_date,
            "gameplay_start_date": t.gameplay_start_date,  # NEW FIELD
            "weight_limit": t.weight_limit,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "is_active": t.is_active,
            "duration_days": t.duration_days
        }
        result.append(TournamentResponse(**tournament_dict))

    return PaginatedTournamentResponse(
        items=result,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )


@router.get("/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(
    tournament_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    tournament_dict = {
        "id": tournament.id,
        "tournament_number": tournament.tournament_number,
        "status": tournament.status,
        "start_date": tournament.start_date,
        "end_date": tournament.end_date,
        "gameplay_start_date": tournament.gameplay_start_date,  # NEW FIELD
        "weight_limit": tournament.weight_limit,
        "created_at": tournament.created_at,
        "updated_at": tournament.updated_at,
        "is_active": tournament.is_active,
        "duration_days": tournament.duration_days
    }
    return TournamentResponse(**tournament_dict)


@router.post("/", response_model=TournamentResponse, status_code=status.HTTP_201_CREATED)
async def create_tournament(
    tournament_data: TournamentCreate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    existing = db.query(Tournament).filter(
        Tournament.tournament_number == tournament_data.tournament_number
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Tournament with number {tournament_data.tournament_number} already exists"
        )

    if tournament_data.status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
        active_tournament = db.query(Tournament).filter(Tournament.status.in_([
            TournamentStatus.REGISTRATION,
            TournamentStatus.ONGOING
        ])).first()
        if active_tournament:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot create active tournament. Tournament #{active_tournament.tournament_number} is already active"
            )

    new_tournament = Tournament(
        tournament_number=tournament_data.tournament_number,
        status=tournament_data.status,
        start_date=tournament_data.start_date,
        end_date=tournament_data.end_date,
        gameplay_start_date=tournament_data.gameplay_start_date,  # NEW FIELD
        weight_limit=tournament_data.weight_limit
    )

    db.add(new_tournament)
    db.commit()
    db.refresh(new_tournament)

    tournament_dict = {
        "id": new_tournament.id,
        "tournament_number": new_tournament.tournament_number,
        "status": new_tournament.status,
        "start_date": new_tournament.start_date,
        "end_date": new_tournament.end_date,
        "gameplay_start_date": new_tournament.gameplay_start_date,  # NEW FIELD
        "weight_limit": new_tournament.weight_limit,
        "created_at": new_tournament.created_at,
        "updated_at": new_tournament.updated_at,
        "is_active": new_tournament.is_active,
        "duration_days": new_tournament.duration_days
    }
    return TournamentResponse(**tournament_dict)


@router.put("/{tournament_id}", response_model=TournamentResponse)
async def update_tournament(
    tournament_id: int,
    tournament_data: TournamentUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament_data.tournament_number and tournament_data.tournament_number != tournament.tournament_number:
        existing = db.query(Tournament).filter(
            Tournament.tournament_number == tournament_data.tournament_number
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Tournament with number {tournament_data.tournament_number} already exists"
            )

    # NEW: Protection - Cannot change gameplay_start_date if it's in the past
    if tournament_data.gameplay_start_date is not None:
        if tournament.gameplay_start_date and tournament.gameplay_start_date <= datetime.utcnow():
            raise HTTPException(
                status_code=400,
                detail="Cannot change gameplay_start_date - it's already in the past"
            )

    # NEW: Validate date chronology with gameplay_start_date
    new_start_date = tournament_data.start_date or tournament.start_date
    new_end_date = tournament_data.end_date or tournament.end_date
    new_gameplay_start = tournament_data.gameplay_start_date or tournament.gameplay_start_date

    if new_gameplay_start:
        if new_gameplay_start <= new_start_date:
            raise HTTPException(
                status_code=400,
                detail="Gameplay start date must be after start date"
            )
        if new_gameplay_start >= new_end_date:
            raise HTTPException(
                status_code=400,
                detail="Gameplay start date must be before end date"
            )

    if new_end_date <= new_start_date:
        raise HTTPException(
            status_code=400,
            detail="End date must be after start date"
        )

    # NEW: Protection - Cannot set status to 'registration' if gameplay_start_date passed
    if tournament_data.status == TournamentStatus.REGISTRATION:
        if new_gameplay_start and new_gameplay_start <= datetime.utcnow():
            raise HTTPException(
                status_code=400,
                detail="Cannot set status to 'registration' - gameplay_start_date has already passed"
            )

    if tournament_data.status:
        if tournament_data.status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
            active_tournament = db.query(Tournament).filter(
                Tournament.id != tournament_id,
                Tournament.status.in_([TournamentStatus.REGISTRATION, TournamentStatus.ONGOING])
            ).first()
            if active_tournament:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot set tournament to active status. Tournament #{active_tournament.tournament_number} is already active"
                )

    update_data = tournament_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tournament, field, value)

    tournament.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(tournament)

    tournament_dict = {
        "id": tournament.id,
        "tournament_number": tournament.tournament_number,
        "status": tournament.status,
        "start_date": tournament.start_date,
        "end_date": tournament.end_date,
        "gameplay_start_date": tournament.gameplay_start_date,  # NEW FIELD
        "weight_limit": tournament.weight_limit,
        "created_at": tournament.created_at,
        "updated_at": tournament.updated_at,
        "is_active": tournament.is_active,
        "duration_days": tournament.duration_days
    }
    return TournamentResponse(**tournament_dict)


@router.delete("/{tournament_id}")
async def delete_tournament(
    tournament_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Проверка что турнир можно деактивировать
    if tournament.status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot deactivate active tournament. Tournament #{tournament.tournament_number} is currently {tournament.status.lower()}"
        )

    tournament.is_active = False
    tournament.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": f"Tournament #{tournament.tournament_number} has been deactivated",
        "tournament_id": tournament_id,
        "success": True
    }


@router.get("/stats/summary")
async def get_tournaments_summary(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    from sqlalchemy import func

    total_tournaments = db.query(Tournament).count()
    registration_count = db.query(Tournament).filter(Tournament.status == TournamentStatus.REGISTRATION).count()
    ongoing_count = db.query(Tournament).filter(Tournament.status == TournamentStatus.ONGOING).count()
    finished_count = db.query(Tournament).filter(Tournament.status == TournamentStatus.FINISHED).count()

    current_tournament = db.query(Tournament).filter(Tournament.status.in_([
        TournamentStatus.REGISTRATION,
        TournamentStatus.ONGOING
    ])).first()

    return {
        "total_tournaments": total_tournaments,
        "by_status": {
            "registration": registration_count,
            "ongoing": ongoing_count,
            "finished": finished_count
        },
        "current_active_tournament": {
            "id": current_tournament.id,
            "tournament_number": current_tournament.tournament_number,
            "status": current_tournament.status,
            "weight_limit": current_tournament.weight_limit
        } if current_tournament else None
    }

@router.post("/{tournament_id}/snapshot", response_model=SnapshotResponse)
async def create_tournament_snapshot(
    tournament_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Manually create price snapshot for tournament (Admin only)
    
    This endpoint allows manual snapshot creation.
    Typically snapshots are created automatically by the tournament management service
    when gameplay_start_date is reached.
    """
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Note: card_score_service uses async, we need async wrapper
    import asyncio
    from models.database import AsyncSessionLocal
    
    async def create_snapshot():
        async with AsyncSessionLocal() as async_db:
            return await card_score_service.create_tournament_snapshot(tournament_id, async_db)
    
    try:
        success = asyncio.run(create_snapshot())
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to create tournament snapshot"
            )

        # Count created snapshots
        from models.tournament_models import TournamentTokenSnapshot
        from sqlalchemy import func
        
        tokens_count = db.query(func.count()).select_from(TournamentTokenSnapshot).filter(
            TournamentTokenSnapshot.tournament_id == tournament_id
        ).scalar() or 0

        return SnapshotResponse(
            tournament_id=tournament_id,
            snapshot_created=True,
            tokens_count=tokens_count,
            message=f"Snapshot created successfully for {tokens_count} tokens"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating tournament snapshot: {str(e)}"
        )