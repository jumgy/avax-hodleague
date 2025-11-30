# api/routes/admin/tournaments.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator
from datetime import datetime, timedelta
from enum import Enum

from models.database import get_sync_db
from models.tournament_models import Tournament, TournamentStatus
from .auth import verify_admin_token

# Pydantic models
class TournamentStatusEnum(str, Enum):
    """Tournament status for Pydantic"""
    REGISTRATION = "registration"
    ONGOING = "ongoing"
    FINISHED = "finished"

class TournamentCreate(BaseModel):
    tournament_number: int
    status: TournamentStatusEnum = TournamentStatusEnum.REGISTRATION
    start_date: datetime
    end_date: datetime

    @validator('tournament_number')
    def validate_tournament_number(cls, v):
        if v is None:
            raise ValueError('Tournament number is required')
        if v < 1:
            raise ValueError('Tournament number must be positive')
        return v

    @validator('start_date')
    def validate_start_date(cls, v):
        if v is None:
            raise ValueError('Start date is required')
        # Разрешаем создавать турниры в прошлом (для тестирования)
        return v

    @validator('end_date')
    def validate_end_date(cls, v, values):
        if v is None:
            raise ValueError('End date is required')
        
        if 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
            
            # Минимум 1 день турнир
            if (v - values['start_date']).total_seconds() < 24 * 3600:
                raise ValueError('Tournament must be at least 1 day long')
                
        return v

class TournamentUpdate(BaseModel):
    tournament_number: Optional[int] = None
    status: Optional[TournamentStatusEnum] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @validator('tournament_number')
    def validate_tournament_number(cls, v):
        if v is not None and v < 1:
            raise ValueError('Tournament number must be positive')
        return v

    @validator('end_date')
    def validate_end_date(cls, v, values):
        if v is not None and 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
        return v

class TournamentResponse(BaseModel):
    id: int
    tournament_number: int
    status: TournamentStatusEnum
    start_date: datetime
    end_date: datetime
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    is_active: bool
    duration_days: int

    class Config:
        from_attributes = True

    @validator('status', pre=True)
    def convert_status_enum(cls, v):
        if hasattr(v, 'value'):
            return v.value
        return v

# Router
router = APIRouter(prefix="/panel/tournaments")

@router.get("/", response_model=List[TournamentResponse])
async def get_all_tournaments(
    status_filter: Optional[TournamentStatusEnum] = Query(None, description="Filter by tournament status"),
    active_only: bool = Query(False, description="Filter only active tournaments"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get all tournaments for admin panel"""
    query = db.query(Tournament)
    
    if status_filter:
        # Конвертируем строку в enum
        status_enum = TournamentStatus(status_filter.value)
        query = query.filter(Tournament.status == status_enum)
    
    if active_only:
        query = query.filter(Tournament.status.in_([
            TournamentStatus.REGISTRATION, 
            TournamentStatus.ONGOING
        ]))
    
    tournaments = query.order_by(Tournament.tournament_number.desc()).all()
    
    # Добавляем computed fields
    result = []
    for t in tournaments:
        tournament_dict = {
            "id": t.id,
            "tournament_number": t.tournament_number,
            "status": t.status.value,
            "start_date": t.start_date,
            "end_date": t.end_date,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "is_active": t.is_active,
            "duration_days": t.duration_days
        }
        result.append(TournamentResponse(**tournament_dict))
    
    return result

@router.get("/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(
    tournament_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get specific tournament by ID"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    tournament_dict = {
        "id": tournament.id,
        "tournament_number": tournament.tournament_number,
        "status": tournament.status.value,
        "start_date": tournament.start_date,
        "end_date": tournament.end_date,
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
    """Create new tournament"""
    # Check if tournament number already exists
    existing = db.query(Tournament).filter(
        Tournament.tournament_number == tournament_data.tournament_number
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Tournament with number {tournament_data.tournament_number} already exists"
        )
    
    # Check business rule: only one active tournament at a time
    if tournament_data.status in [TournamentStatusEnum.REGISTRATION, TournamentStatusEnum.ONGOING]:
        active_tournament = db.query(Tournament).filter(Tournament.status.in_([
            TournamentStatus.REGISTRATION,
            TournamentStatus.ONGOING
        ])).first()
        
        if active_tournament:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot create active tournament. Tournament #{active_tournament.tournament_number} is already active"
            )
    
    # Convert Pydantic enum to SQLAlchemy enum
    status_enum = TournamentStatus(tournament_data.status.value)
    
    # Create new tournament
    new_tournament = Tournament(
        tournament_number=tournament_data.tournament_number,
        status=status_enum,
        start_date=tournament_data.start_date,
        end_date=tournament_data.end_date
    )
    
    db.add(new_tournament)
    db.commit()
    db.refresh(new_tournament)
    
    # Return response
    tournament_dict = {
        "id": new_tournament.id,
        "tournament_number": new_tournament.tournament_number,
        "status": new_tournament.status.value,
        "start_date": new_tournament.start_date,
        "end_date": new_tournament.end_date,
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
    """Update existing tournament"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Check tournament number uniqueness if being updated
    if tournament_data.tournament_number and tournament_data.tournament_number != tournament.tournament_number:
        existing = db.query(Tournament).filter(
            Tournament.tournament_number == tournament_data.tournament_number
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Tournament with number {tournament_data.tournament_number} already exists"
            )
    
    # Check business rule for status changes
    if tournament_data.status:
        new_status = TournamentStatus(tournament_data.status.value)
        
        # If setting to active status, check no other active tournament exists
        if new_status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
            active_tournament = db.query(Tournament).filter(
                Tournament.id != tournament_id,  # Exclude current tournament
                Tournament.status.in_([TournamentStatus.REGISTRATION, TournamentStatus.ONGOING])
            ).first()
            
            if active_tournament:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot set tournament to active status. Tournament #{active_tournament.tournament_number} is already active"
                )
    
    # Validate dates consistency
    start_date = tournament_data.start_date or tournament.start_date
    end_date = tournament_data.end_date or tournament.end_date
    
    if end_date <= start_date:
        raise HTTPException(
            status_code=400,
            detail="End date must be after start date"
        )
    
    # Update fields
    update_data = tournament_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'status':
            setattr(tournament, field, TournamentStatus(value.value))
        else:
            setattr(tournament, field, value)
    
    tournament.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(tournament)
    
    # Return response
    tournament_dict = {
        "id": tournament.id,
        "tournament_number": tournament.tournament_number,
        "status": tournament.status.value,
        "start_date": tournament.start_date,
        "end_date": tournament.end_date,
        "created_at": tournament.created_at,
        "updated_at": tournament.updated_at,
        "is_active": tournament.is_active,
        "duration_days": tournament.duration_days
    }
    
    return TournamentResponse(**tournament_dict)

# Дополнительные utility endpoints
@router.get("/stats/summary", tags=["Tournament Statistics"])
async def get_tournaments_summary(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get tournament statistics summary"""
    total_tournaments = db.query(Tournament).count()
    registration_count = db.query(Tournament).filter(Tournament.status == TournamentStatus.REGISTRATION).count()
    ongoing_count = db.query(Tournament).filter(Tournament.status == TournamentStatus.ONGOING).count()
    finished_count = db.query(Tournament).filter(Tournament.status == TournamentStatus.FINISHED).count()
    
    # Get current active tournament
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
            "status": current_tournament.status.value
        } if current_tournament else None
    }