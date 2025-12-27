# api/routes/tournaments.py

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime
import logging

from models.database import get_async_db
from models.tournament_models import Tournament, TournamentStatus
from models.tournament_deck_models import TournamentDeck
from services.web3_auth_service import web3_auth_service

logger = logging.getLogger(__name__)

# Create router with prefix
router = APIRouter(prefix="/tournaments")

# Security for optional JWT
security_optional = HTTPBearer(auto_error=False)

# ==================== Optional Auth Dependency ====================

def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[dict]:
    """
    Optional JWT authentication - returns user data if token present, None otherwise
    Does not raise errors if token is missing or invalid
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        payload = web3_auth_service.verify_jwt_token(token)
        return payload if payload else None
    except Exception as e:
        logger.debug(f"Optional auth failed (this is OK): {e}")
        return None

# ==================== Pydantic Models ====================

class TournamentListItem(BaseModel):
    id: int
    tournament_number: int
    status: str
    start_date: datetime
    end_date: datetime
    gameplay_start_date: Optional[datetime]
    weight_limit: int
    participants_count: int
    is_registered: bool = False

    model_config = ConfigDict(from_attributes=True)

class TournamentDetail(BaseModel):
    id: int
    tournament_number: int
    status: str
    start_date: datetime
    end_date: datetime
    gameplay_start_date: Optional[datetime]
    weight_limit: int
    participants_count: int
    is_active: bool
    duration_days: int
    is_registered: bool = False
    my_deck: Optional[List[int]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedTournamentsResponse(BaseModel):
    items: List[TournamentListItem]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool

# ==================== Endpoints ====================

@router.get("",
           response_model=PaginatedTournamentsResponse,
           summary="Get tournaments list",
           description="Get list of tournaments with pagination and filters, optinal auth")
async def get_tournaments_list(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status: registration, ongoing, finished"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of tournaments with pagination and filters
    - **page**: Page number (starts from 1)
    - **limit**: Items per page (max 100)
    - **status_filter**: Filter by tournament status
    
    Returns tournaments sorted by tournament_number descending (newest first)
    If user is authenticated, shows registration status for each tournament
    """
    try:
        # Validate status filter
        if status_filter and not TournamentStatus.is_valid(status_filter):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(TournamentStatus.ALL_STATUSES)}"
            )

        # Build query - БЕЗ фильтра is_active в базовом запросе
        query = select(Tournament)
        
        if status_filter:
            query = query.where(Tournament.status == status_filter)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Calculate offset
        offset = (page - 1) * limit

        # Get tournaments with pagination
        query = query.order_by(Tournament.tournament_number.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        tournaments = result.scalars().all()

        # Get user_id if authenticated
        user_id = current_user.get('user_id') if current_user else None

        # Build response
        items = []
        for tournament in tournaments:
            # Count participants
            participants_count_query = select(func.count()).select_from(TournamentDeck).where(
                TournamentDeck.tournament_id == tournament.id,
                TournamentDeck.is_active == True
            )
            participants_result = await db.execute(participants_count_query)
            participants_count = participants_result.scalar() or 0

            # Check if user is registered
            is_registered = False
            if user_id:
                deck_query = select(TournamentDeck).where(
                    TournamentDeck.tournament_id == tournament.id,
                    TournamentDeck.user_id == user_id,
                    TournamentDeck.is_active == True
                )
                deck_result = await db.execute(deck_query)
                deck = deck_result.scalar_one_or_none()
                is_registered = deck is not None

            items.append(TournamentListItem(
                id=tournament.id,
                tournament_number=tournament.tournament_number,
                status=tournament.status,
                start_date=tournament.start_date,
                end_date=tournament.end_date,
                gameplay_start_date=tournament.gameplay_start_date,
                weight_limit=tournament.weight_limit,
                participants_count=participants_count,
                is_registered=is_registered
            ))

        return PaginatedTournamentsResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            has_next=(offset + limit) < total,
            has_prev=page > 1
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tournaments list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve tournaments: {str(e)}"
        )

@router.get("/{tournament_id}",
           response_model=TournamentDetail,
           summary="Get tournament details",
           description="Get detailed information about a specific tournament")
async def get_tournament_details(
    tournament_id: int,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed information about a specific tournament
    - Shows tournament details
    - Shows participant count
    - If authenticated: shows if user is registered and their deck
    """
    try:
        # Get tournament
        query = select(Tournament).where(Tournament.id == tournament_id)
        result = await db.execute(query)
        tournament = result.scalar_one_or_none()
        
        if not tournament:
            raise HTTPException(
                status_code=404, 
                detail=f"Tournament with id {tournament_id} not found"
            )

        # Count participants
        participants_count_query = select(func.count()).select_from(TournamentDeck).where(
            TournamentDeck.tournament_id == tournament.id,
            TournamentDeck.is_active == True
        )
        participants_result = await db.execute(participants_count_query)
        participants_count = participants_result.scalar() or 0

        # Get user info if authenticated
        user_id = current_user.get('user_id') if current_user else None
        is_registered = False
        my_deck = None

        if user_id:
            deck_query = select(TournamentDeck).where(
                TournamentDeck.tournament_id == tournament.id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True
            )
            deck_result = await db.execute(deck_query)
            deck = deck_result.scalar_one_or_none()
            
            if deck:
                is_registered = True
                my_deck = deck.deck_composition if isinstance(deck.deck_composition, list) else None

        return TournamentDetail(
            id=tournament.id,
            tournament_number=tournament.tournament_number,
            status=tournament.status,
            start_date=tournament.start_date,
            end_date=tournament.end_date,
            gameplay_start_date=tournament.gameplay_start_date,
            weight_limit=tournament.weight_limit,
            participants_count=participants_count,
            is_active=tournament.is_active,
            duration_days=tournament.duration_days,
            is_registered=is_registered,
            my_deck=my_deck,
            created_at=tournament.created_at,
            updated_at=tournament.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve tournament details: {str(e)}"
        )