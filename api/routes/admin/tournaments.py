from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional, Dict
from pydantic import BaseModel, validator, ConfigDict
from datetime import datetime, timedelta, timezone

from models.database import get_async_db
from models.tournament_models import Tournament, TournamentStatus, TournamentTokenSnapshot
from services.tournament_service import tournament_service
from .auth import verify_admin_token

class TournamentCreate(BaseModel):
    tournament_number: int
    status: str = TournamentStatus.REGISTRATION
    start_date: datetime
    end_date: datetime
    gameplay_start_date: datetime
    weight_limit: int = 30
    reward_types: Optional[List[int]] = None
    prize_pools: Optional[Dict[str, str]] = None

    

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
            if values['gameplay_start_date'] <= datetime.now(timezone.utc):
                raise ValueError("Cannot create tournament with 'registration' status if gameplay_start_date is in the past")
        return v


class TournamentUpdate(BaseModel):
    tournament_number: Optional[int] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    gameplay_start_date: Optional[datetime] = None
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
    gameplay_start_date: Optional[datetime]
    weight_limit: int
    reward_types: Optional[List[int]] = None
    prize_pools: Optional[Dict[str, str]] = None
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
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить все турниры с фильтрацией, сортировкой и пагинацией"""
    # Базовый запрос
    query = select(Tournament)

    # Применяем фильтры
    if id is not None:
        query = query.where(Tournament.id == id)
    if tournament_number is not None:
        query = query.where(Tournament.tournament_number == tournament_number)
    if status_filter:
        if not TournamentStatus.is_valid(status_filter):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter. Must be one of: {', '.join(TournamentStatus.ALL_STATUSES)}"
            )
        query = query.where(Tournament.status == status_filter)
    if is_active is not None:
        query = query.where(Tournament.is_active == is_active)
    if weight_limit_from is not None:
        query = query.where(Tournament.weight_limit >= weight_limit_from)
    if weight_limit_to is not None:
        query = query.where(Tournament.weight_limit <= weight_limit_to)
    if start_date_from:
        query = query.where(Tournament.start_date >= start_date_from)
    if start_date_to:
        query = query.where(Tournament.start_date <= start_date_to)
    if end_date_from:
        query = query.where(Tournament.end_date >= end_date_from)
    if end_date_to:
        query = query.where(Tournament.end_date <= end_date_to)
    if created_from:
        query = query.where(Tournament.created_at >= created_from)
    if created_to:
        query = query.where(Tournament.created_at <= created_to)
    if updated_from:
        query = query.where(Tournament.updated_at >= updated_from)
    if updated_to:
        query = query.where(Tournament.updated_at <= updated_to)

    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Применяем сортировку
    sort_column = getattr(Tournament, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedTournamentResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )


@router.get("/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретный турнир по ID"""
    query = select(Tournament).where(Tournament.id == tournament_id)
    result = await db.execute(query)
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    return tournament


@router.post("/", response_model=TournamentResponse, status_code=status.HTTP_201_CREATED)
async def create_tournament(
    tournament_data: TournamentCreate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Создать новый турнир"""
    
    # Проверяем существование турнира с таким номером
    existing_query = select(Tournament).where(
        Tournament.tournament_number == tournament_data.tournament_number
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Tournament with number {tournament_data.tournament_number} already exists"
        )
    
    # ⭐ NEW: Проверяем пересечение по датам gameplay (только для REGISTRATION/ONGOING)
    if tournament_data.status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
        # Ищем турниры, у которых период gameplay пересекается с новым турниром
        overlap_query = select(Tournament).where(
            and_(
                Tournament.status.in_([
                    TournamentStatus.REGISTRATION,
                    TournamentStatus.ONGOING
                ]),
                # Пересечение: новый.gameplay_start <= существующий.end AND новый.end >= существующий.gameplay_start
                Tournament.end_date >= tournament_data.gameplay_start_date,
                Tournament.gameplay_start_date <= tournament_data.end_date
            )
        )
        overlap_result = await db.execute(overlap_query)
        overlapping_tournament = overlap_result.scalar_one_or_none()
        
        if overlapping_tournament:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot create tournament. Time conflict with tournament #{overlapping_tournament.tournament_number} "
                    f"(gameplay: {overlapping_tournament.gameplay_start_date} - {overlapping_tournament.end_date})"
                )
            )
    
    # Создаем новый турнир
    new_tournament = Tournament(
        tournament_number=tournament_data.tournament_number,
        status=tournament_data.status,
        start_date=tournament_data.start_date,
        end_date=tournament_data.end_date,
        gameplay_start_date=tournament_data.gameplay_start_date,
        weight_limit=tournament_data.weight_limit,
        reward_types=tournament_data.reward_types,
        prize_pools=tournament_data.prize_pools 
    )
    
    db.add(new_tournament)
    await db.commit()
    await db.refresh(new_tournament)
    
    return new_tournament


@router.put("/{tournament_id}", response_model=TournamentResponse)
async def update_tournament(
    tournament_id: int,
    tournament_data: TournamentUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Обновить существующий турнир"""
    # Получаем турнир
    query = select(Tournament).where(Tournament.id == tournament_id)
    result = await db.execute(query)
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Проверяем уникальность номера турнира
    if tournament_data.tournament_number and tournament_data.tournament_number != tournament.tournament_number:
        existing_query = select(Tournament).where(
            Tournament.tournament_number == tournament_data.tournament_number
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Tournament with number {tournament_data.tournament_number} already exists"
            )

    # Защита - нельзя изменить gameplay_start_date если она в прошлом
    if tournament_data.gameplay_start_date is not None:
        if tournament.gameplay_start_date and tournament.gameplay_start_date <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400,
                detail="Cannot change gameplay_start_date - it's already in the past"
            )

    # Валидация хронологии дат
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

    # Защита - нельзя установить статус 'registration' если gameplay_start_date прошла
    if tournament_data.status == TournamentStatus.REGISTRATION:
        if new_gameplay_start and new_gameplay_start <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400,
                detail="Cannot set status to 'registration' - gameplay_start_date has already passed"
            )

    # Проверка активных турниров
    if tournament_data.status:
        if tournament_data.status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
            active_query = select(Tournament).where(
                Tournament.id != tournament_id,
                Tournament.status.in_([TournamentStatus.REGISTRATION, TournamentStatus.ONGOING])
            )
            active_result = await db.execute(active_query)
            active_tournament = active_result.scalar_one_or_none()
            
            if active_tournament:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot set tournament to active status. Tournament #{active_tournament.tournament_number} is already active"
                )

    # Применяем обновления
    update_data = tournament_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tournament, field, value)

    tournament.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(tournament)

    return tournament


@router.delete("/{tournament_id}")
async def delete_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Деактивировать турнир (мягкое удаление)"""
    query = select(Tournament).where(Tournament.id == tournament_id)
    result = await db.execute(query)
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Проверка что турнир можно деактивировать
    if tournament.status in [TournamentStatus.REGISTRATION, TournamentStatus.ONGOING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot deactivate active tournament. Tournament #{tournament.tournament_number} is currently {tournament.status.lower()}"
        )

    tournament.is_active = False
    tournament.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "message": f"Tournament #{tournament.tournament_number} has been deactivated",
        "tournament_id": tournament_id,
        "success": True
    }


@router.get("/stats/summary")
async def get_tournaments_summary(
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику по турнирам"""
    # Общее количество турниров
    total_query = select(func.count()).select_from(Tournament)
    total_result = await db.execute(total_query)
    total_tournaments = total_result.scalar()

    # Количество по статусам
    registration_query = select(func.count()).select_from(Tournament).where(
        Tournament.status == TournamentStatus.REGISTRATION
    )
    registration_result = await db.execute(registration_query)
    registration_count = registration_result.scalar()

    ongoing_query = select(func.count()).select_from(Tournament).where(
        Tournament.status == TournamentStatus.ONGOING
    )
    ongoing_result = await db.execute(ongoing_query)
    ongoing_count = ongoing_result.scalar()

    finished_query = select(func.count()).select_from(Tournament).where(
        Tournament.status == TournamentStatus.FINISHED
    )
    finished_result = await db.execute(finished_query)
    finished_count = finished_result.scalar()

    # Текущий активный турнир
    current_query = select(Tournament).where(Tournament.status.in_([
        TournamentStatus.REGISTRATION,
        TournamentStatus.ONGOING
    ]))
    current_result = await db.execute(current_query)
    current_tournament = current_result.scalar_one_or_none()

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
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Вручную создать снапшот цен для турнира (только для администраторов)
    
    Обычно снапшоты создаются автоматически сервисом управления турнирами
    когда наступает gameplay_start_date.
    """
    # Проверяем существование турнира
    query = select(Tournament).where(Tournament.id == tournament_id)
    result = await db.execute(query)
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    try:
        # Вызываем асинхронный сервис создания снапшота
        success = await tournament_service.create_tournament_snapshot(tournament_id, db)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to create tournament snapshot"
            )

        # Подсчитываем созданные снапшоты
        count_query = select(func.count()).select_from(TournamentTokenSnapshot).where(
            TournamentTokenSnapshot.tournament_id == tournament_id
        )
        count_result = await db.execute(count_query)
        tokens_count = count_result.scalar() or 0

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