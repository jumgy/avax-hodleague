from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from models.database import get_async_db
from models.tournament_deck_models import TournamentDeck, TournamentResult
from .auth import verify_admin_token

class TournamentDeckResponse(BaseModel):
    id: int
    tournament_id: int
    user_id: int
    deck_composition: Any
    deck_hash: str
    submitted_at: datetime
    is_valid: bool
    is_active: bool
    validation_errors: Optional[str]
    transaction_hash: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class TournamentResultResponse(BaseModel):
    id: int
    tournament_id: int
    tournament_deck_id: int
    final_position: int
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedTournamentDeckResponse(BaseModel):
    items: List[TournamentDeckResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

class PaginatedTournamentResultResponse(BaseModel):
    items: List[TournamentResultResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

router = APIRouter(prefix="/panel/tournament-decks")

@router.get("/decks", response_model=PaginatedTournamentDeckResponse)
async def get_tournament_decks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    id: Optional[int] = Query(None),
    tournament_id: Optional[int] = Query(None, description="Filter by tournament_id"),
    user_id: Optional[int] = Query(None, description="Filter by user_id"),
    is_valid: Optional[bool] = Query(None, description="Filter by valid decks"),
    is_active: Optional[bool] = Query(None, description="Filter only active decks"),
    submitted_from: Optional[datetime] = Query(None),
    submitted_to: Optional[datetime] = Query(None),
    sort_by: str = Query("submitted_at", regex="^(id|tournament_id|user_id|deck_hash|submitted_at|is_valid|is_active)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    """
    Получить все турнирные колоды с фильтрацией, сортировкой и пагинацией
    """
    
    # Базовый запрос
    query = select(TournamentDeck)
    
    # Применяем фильтры
    if id is not None:
        query = query.where(TournamentDeck.id == id)
    
    if tournament_id is not None:
        query = query.where(TournamentDeck.tournament_id == tournament_id)
    
    if user_id is not None:
        query = query.where(TournamentDeck.user_id == user_id)
    
    if is_valid is not None:
        query = query.where(TournamentDeck.is_valid == is_valid)
    
    if is_active is not None:
        query = query.where(TournamentDeck.is_active == is_active)
    
    if submitted_from:
        query = query.where(TournamentDeck.submitted_at >= submitted_from)
    
    if submitted_to:
        query = query.where(TournamentDeck.submitted_at <= submitted_to)
    
    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(TournamentDeck, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return PaginatedTournamentDeckResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/decks/{deck_id}", response_model=TournamentDeckResponse)
async def get_tournament_deck(
    deck_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретную турнирную колоду по ID"""
    
    query = select(TournamentDeck).where(TournamentDeck.id == deck_id)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="TournamentDeck not found")
    
    return obj

@router.get("/results", response_model=PaginatedTournamentResultResponse)
async def get_tournament_results(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    id: Optional[int] = Query(None),
    tournament_id: Optional[int] = Query(None),
    tournament_deck_id: Optional[int] = Query(None),
    final_position: Optional[int] = Query(None),
    calculated_from: Optional[datetime] = Query(None),
    calculated_to: Optional[datetime] = Query(None),
    sort_by: str = Query("calculated_at", regex="^(id|tournament_id|tournament_deck_id|final_position|calculated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить все результаты турниров с фильтрацией, сортировкой и пагинацией
    """
    
    # Базовый запрос
    query = select(TournamentResult)
    
    # Применяем фильтры
    if id is not None:
        query = query.where(TournamentResult.id == id)
    
    if tournament_id is not None:
        query = query.where(TournamentResult.tournament_id == tournament_id)
    
    if tournament_deck_id is not None:
        query = query.where(TournamentResult.tournament_deck_id == tournament_deck_id)
    
    if final_position is not None:
        query = query.where(TournamentResult.final_position == final_position)
    
    if calculated_from:
        query = query.where(TournamentResult.calculated_at >= calculated_from)
    
    if calculated_to:
        query = query.where(TournamentResult.calculated_at <= calculated_to)
    
    # Подсчитываем общее количество
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Применяем сортировку
    sort_column = getattr(TournamentResult, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return PaginatedTournamentResultResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/results/{result_id}", response_model=TournamentResultResponse)
async def get_tournament_result(
    result_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретный результат турнира по ID"""
    
    query = select(TournamentResult).where(TournamentResult.id == result_id)
    result = await db.execute(query)
    obj = result.scalar_one_or_none()
    
    if not obj:
        raise HTTPException(status_code=404, detail="TournamentResult not found")
    
    return obj