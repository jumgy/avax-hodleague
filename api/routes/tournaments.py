# api/routes/tournaments.py

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict
from datetime import datetime
import logging

from models.database import get_async_db
from models.tournament_models import Tournament, TournamentStatus
from models.tournament_deck_models import TournamentDeck
from models.user_card_models import UserCard
from models.card_models import Card
from models.rarity_models import Rarity
from models.token_models import Token
from services.web3_auth_service import web3_auth_service
from services.tournament_registration_service import TournamentRegistrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tournaments")
security_optional = HTTPBearer(auto_error=False)

# ==================== Auth Dependencies ====================

def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[dict]:
    if not credentials:
        return None
    try:
        token = credentials.credentials
        payload = web3_auth_service.verify_jwt_token(token)
        return payload if payload else None
    except Exception as e:
        logger.debug(f"Optional auth failed (this is OK): {e}")
        return None

def get_current_user_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    try:
        token = credentials.credentials
        payload = web3_auth_service.verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

# ==================== Pydantic Models ====================

class CardInDeckInfo(BaseModel):
    """Полная информация о карте в деке"""
    user_card_id: int
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    token_weight: int
    rarity_name: str
    rarity_color: str
    rarity_score_bonus: int
    design_type: str
    background_image_url: str
    current_price: Optional[float]
    market_cap: Optional[int]
    change_24h: Optional[float]
    calculated_score: float

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
    my_deck: Optional[Union[List[int], List[CardInDeckInfo]]] = None
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

# ==================== Registration Models ====================

class DeckRegisterRequest(BaseModel):
    deck_composition: List[int]
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "deck_composition": [1, 2, 3, 4, 5]
            }
        }
    )

class CardInDeckResponse(BaseModel):
    user_card_id: int
    card_name: str
    rarity: str
    weight: float

class DeckRegisterResponse(BaseModel):
    deck_id: int
    deck_hash: str
    total_weight: float
    cards: List[CardInDeckResponse]
    message: str

# ==================== Endpoints ====================

@router.get("",
           response_model=PaginatedTournamentsResponse,
           summary="Get tournaments list",
           description="Get list of tournaments with pagination and filters, optional auth")
async def get_tournaments_list(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status: registration, ongoing, finished"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        if status_filter and not TournamentStatus.is_valid(status_filter):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(TournamentStatus.ALL_STATUSES)}"
            )

        query = select(Tournament)
        if status_filter:
            query = query.where(Tournament.status == status_filter)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * limit
        query = query.order_by(Tournament.tournament_number.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        tournaments = result.scalars().all()

        user_id = current_user.get('user_id') if current_user else None

        items = []
        for tournament in tournaments:
            participants_count_query = select(func.count()).select_from(TournamentDeck).where(
                TournamentDeck.tournament_id == tournament.id,
                TournamentDeck.is_active == True
            )
            participants_result = await db.execute(participants_count_query)
            participants_count = participants_result.scalar() or 0

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
           description="Get detailed information about a specific tournament with optional full deck info")
async def get_tournament_details(
    tournament_id: int,
    include_deck: bool = Query(False, description="Include full card details for user's deck"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed information about a specific tournament
    
    - **tournament_id**: Tournament ID
    - **include_deck**: If true, returns full card information instead of just IDs
    - Shows tournament details and participant count
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
                deck_composition = deck.deck_composition if isinstance(deck.deck_composition, list) else None

                if deck_composition:
                    if include_deck:
                        # Получаем полную информацию о картах через материализованное представление
                        cards_query = text("""
                            SELECT 
                                uc.id as user_card_id,
                                ac.card_id,
                                ac.token_symbol,
                                ac.token_name,
                                ac.token_image_url,
                                ac.token_weight,
                                ac.rarity_name,
                                ac.rarity_color,
                                ac.rarity_score_bonus,
                                ac.design_type,
                                ac.background_image_url,
                                ac.current_price,
                                ac.market_cap,
                                ac.change_24h,
                                ac.calculated_score
                            FROM user_cards uc
                            JOIN active_cards_with_score ac ON uc.card_id = ac.card_id
                            WHERE uc.id = ANY(:user_card_ids)
                              AND uc.is_active = true
                              AND ac.is_active = true
                        """)
                        
                        cards_result = await db.execute(
                            cards_query, 
                            {"user_card_ids": deck_composition}
                        )
                        cards_rows = cards_result.fetchall()

                        # Создаем словарь для сохранения порядка карт
                        cards_dict = {}
                        for row in cards_rows:
                            cards_dict[row.user_card_id] = CardInDeckInfo(
                                user_card_id=row.user_card_id,
                                card_id=row.card_id,
                                token_symbol=row.token_symbol,
                                token_name=row.token_name,
                                token_image_url=row.token_image_url,
                                token_weight=row.token_weight,
                                rarity_name=row.rarity_name,
                                rarity_color=row.rarity_color,
                                rarity_score_bonus=row.rarity_score_bonus,
                                design_type=row.design_type,
                                background_image_url=row.background_image_url,
                                current_price=float(row.current_price) if row.current_price else None,
                                market_cap=int(row.market_cap) if row.market_cap else None,
                                change_24h=float(row.change_24h) if row.change_24h else None,
                                calculated_score=float(row.calculated_score) if row.calculated_score else 0.0
                            )

                        # Возвращаем карты в правильном порядке
                        my_deck = [cards_dict[card_id] for card_id in deck_composition if card_id in cards_dict]
                    else:
                        # Возвращаем только ID карт
                        my_deck = deck_composition

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

@router.post("/{tournament_id}/register",
            response_model=DeckRegisterResponse,
            summary="Register for tournament",
            description="Register for a tournament with a deck of 5 cards")
async def register_for_tournament(
    tournament_id: int,
    request: DeckRegisterRequest,
    current_user: dict = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data in token"
            )

        tournament_deck = await TournamentRegistrationService.validate_and_register_deck(
            db=db,
            tournament_id=tournament_id,
            user_id=user_id,
            deck_composition=request.deck_composition
        )

        cards_query = select(UserCard, Card, Token, Rarity).join(
            Card, UserCard.card_id == Card.id
        ).join(
            Token, Card.token_id == Token.id
        ).join(
            Rarity, Card.rarity_id == Rarity.id
        ).where(UserCard.id.in_(request.deck_composition))

        cards_result = (await db.execute(cards_query)).all()

        cards_info = [
            CardInDeckResponse(
                user_card_id=user_card.id,
                card_name=token.name,
                rarity=rarity.name,
                weight=float(token.weight)
            )
            for user_card, card, token, rarity in cards_result
        ]

        return DeckRegisterResponse(
            deck_id=tournament_deck.id,
            deck_hash=tournament_deck.deck_hash,
            total_weight=tournament_deck.total_weight,
            cards=cards_info,
            message="Successfully registered for tournament. Your cards are now locked."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering for tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register for tournament: {str(e)}"
        )