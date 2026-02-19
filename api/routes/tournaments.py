# api/routes/tournaments.py

import logging
from datetime import datetime
from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.card_models import Card
from models.database import get_async_db
from models.rarity_models import Rarity
from models.reward_models import RewardType
from models.token_models import Token
from models.tournament_deck_models import TournamentDeck, TournamentResult
from models.tournament_models import Tournament, TournamentStatus
from models.user_card_models import UserCard
from models.user_models import User
from services.prize_config_service import PrizeConfigService
from services.tournament_registration_service import TournamentRegistrationService
from services.web3_auth_service import web3_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tournaments")
security_optional = HTTPBearer(auto_error=False)

# ==================== Auth Dependencies ====================


def get_current_user_optional(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[dict]:
    """Optional auth: cookie OR Bearer header"""
    token = None

    # 1. Пробуем Bearer header (Swagger)
    if credentials:
        token = credentials.credentials

    # 2. Если нет, пробуем cookie (фронт)
    if not token:
        token = request.cookies.get("access_token")

    # 3. Если токена нет - это optional, возвращаем None
    if not token:
        return None

    try:
        payload = web3_auth_service.verify_jwt_token(token)
        return payload if payload else None
    except Exception as e:
        logger.debug(f"Optional auth failed (this is OK): {e}")
        return None


def get_current_user_required(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> dict:
    """Required auth: cookie OR Bearer header"""
    token = None

    # 1. Пробуем Bearer header (Swagger)
    if credentials:
        token = credentials.credentials

    # 2. Если нет, пробуем cookie (фронт)
    if not token:
        token = request.cookies.get("access_token")

    # 3. Если токена нет - ошибка
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = web3_auth_service.verify_jwt_token(token)
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


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
    design_type: str
    rendered_image_url: str
    tournament_change: Optional[float]
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


class PrizePoolInfo(BaseModel):
    amount: str
    currency_name: str


class TournamentDetail(BaseModel):
    id: int
    tournament_number: int
    status: str
    start_date: datetime
    end_date: datetime
    gameplay_start_date: Optional[datetime]
    weight_limit: int
    prize_pools: Optional[dict[str, PrizePoolInfo]] = None  # Базовые prize pools
    estimated_final_prize_pools: Optional[dict[str, PrizePoolInfo]] = None  # Расчётные с учётом участников
    participants_count: int
    is_active: bool
    duration_days: int
    is_registered: bool = False
    my_deck: Optional[Union[list[int], list[CardInDeckInfo]]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedTournamentsResponse(BaseModel):
    items: list[TournamentListItem]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool


# ==================== Registration Models ====================


class CardInDeckResponse(BaseModel):
    user_card_id: int
    card_name: str
    rarity: str
    weight: float


class DeckValidateRequest(BaseModel):
    """Запрос на пре-валидацию деки"""

    deck_composition: list[int]

    model_config = ConfigDict(json_schema_extra={"example": {"deck_composition": [210, 211, 212, 213, 214]}})


class DeckValidateResponse(BaseModel):
    """Ответ пре-валидации с deck_hash для контракта и рекомендацией сети"""

    valid: bool
    deck_hash: str
    total_weight: float
    weight_limit: float
    cards: list[CardInDeckResponse]
    message: str
    preferred_network: Literal["abstract", "avalanche"] = "abstract"
    switch_network_required: bool = False
    avalanche_chain_id: Optional[int] = None
    avalanche_contract_address: Optional[str] = None


class DeckRegisterRequest(BaseModel):
    """Запрос на финальную регистрацию с tx_hash"""

    deck_composition: list[int]
    tx_hash: str
    network: Literal["abstract", "avalanche"] = "abstract"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "deck_composition": [210, 211, 212, 213, 214],
                "tx_hash": "0x1234567890abcdef...",
                "network": "abstract",
            }
        }
    )


class DeckRegisterResponse(BaseModel):
    """Ответ успешной регистрации"""

    success: bool
    deck_id: int
    deck_hash: str
    tx_hash: str
    total_weight: float
    cards: list[CardInDeckResponse]
    message: str


class DeckUnregisterRequest(BaseModel):
    """Запрос на отмену регистрации"""

    tx_hash: str
    network: Literal["abstract", "avalanche"] = "abstract"

    model_config = ConfigDict(
        json_schema_extra={"example": {"tx_hash": "0xabcdef1234567890...", "network": "abstract"}}
    )


class DeckUnregisterResponse(BaseModel):
    """Ответ отмены регистрации"""

    success: bool
    cards_unlocked: int
    tx_hash: str
    message: str


# ==================== Leaderboard Models ====================


class CardInDeck(BaseModel):
    """Информация о карте в деке"""

    card_id: int
    token_id: int
    token_symbol: str
    token_name: str
    rarity: str
    design_type: str
    rendered_image_url: Optional[str] = None
    template_image_url: str

    model_config = ConfigDict(from_attributes=True)


class PrizeInfo(BaseModel):
    """Информация о призе"""

    reward_type_id: int
    reward_name: str
    reward_category: str
    currency_type: str
    amount: str  # Decimal as string

    class Config:
        from_attributes = True


class LeaderboardEntry(BaseModel):
    """Запись в лидерборде"""

    position: int
    deck_id: int
    user_id: int
    wallet_address: Optional[str] = None
    nickname: str
    avatar_url: Optional[str] = None
    final_score: float
    deck_composition: list[int]
    cards: list[CardInDeck]
    prizes: Optional[list[PrizeInfo]]
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeaderboardResponse(BaseModel):
    """Ответ с лидербордом турнира"""

    tournament_id: int
    tournament_number: int
    status: str
    leaderboard: list[LeaderboardEntry]
    total_participants: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool
    my_position: Optional[LeaderboardEntry] = None
    last_updated: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DeckDetailResponse(BaseModel):
    deck_id: int
    tournament_id: int
    tournament_number: int
    tournament_status: str
    user_id: int
    wallet_address: Optional[str] = None
    nickname: str
    avatar_url: Optional[str] = None
    deck_composition: list[int]
    cards: list[CardInDeckInfo]
    total_weight: float
    submitted_at: datetime

    position: Optional[int] = None
    final_score: Optional[float] = None
    prizes: Optional[list[PrizeInfo]] = None

    model_config = ConfigDict(from_attributes=True)


# ==================== Endpoints ====================


@router.get(
    "",
    response_model=PaginatedTournamentsResponse,
    summary="Get tournaments list",
    description="Get list of tournaments with pagination and filters, optional auth",
)
async def get_tournaments_list(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status: registration, ongoing, finished"),
    include_featured: bool = Query(False, description="Include featured tournaments in the list"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        if status_filter and not TournamentStatus.is_valid(status_filter):
            raise HTTPException(
                status_code=400, detail=f"Invalid status. Must be one of: {', '.join(TournamentStatus.ALL_STATUSES)}"
            )

        query = select(Tournament).where(Tournament.is_active == True)

        # Фильтр по статусу
        if status_filter:
            query = query.where(Tournament.status == status_filter)
        else:
            # По умолчанию НЕ показываем featured турниры
            if not include_featured:
                query = query.where(Tournament.status != TournamentStatus.FEATURED)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * limit
        query = query.order_by(Tournament.tournament_number.desc()).offset(offset).limit(limit)

        result = await db.execute(query)
        tournaments = result.scalars().all()

        user_id = current_user.get("user_id") if current_user else None

        items = []
        for tournament in tournaments:
            participants_count_query = (
                select(func.count())
                .select_from(TournamentDeck)
                .where(TournamentDeck.tournament_id == tournament.id, TournamentDeck.is_active == True)
            )
            participants_result = await db.execute(participants_count_query)
            participants_count = participants_result.scalar() or 0

            is_registered = False
            if user_id:
                deck_query = select(TournamentDeck).where(
                    TournamentDeck.tournament_id == tournament.id,
                    TournamentDeck.user_id == user_id,
                    TournamentDeck.is_active == True,
                )
                deck_result = await db.execute(deck_query)
                deck = deck_result.scalar_one_or_none()
                is_registered = deck is not None

            items.append(
                TournamentListItem(
                    id=tournament.id,
                    tournament_number=tournament.tournament_number,
                    status=tournament.status,
                    start_date=tournament.start_date,
                    end_date=tournament.end_date,
                    gameplay_start_date=tournament.gameplay_start_date,
                    weight_limit=tournament.weight_limit,
                    participants_count=participants_count,
                    is_registered=is_registered,
                )
            )

        return PaginatedTournamentsResponse(
            items=items, total=total, page=page, limit=limit, has_next=(offset + limit) < total, has_prev=page > 1
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tournaments list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve tournaments: {str(e)}"
        )


@router.get(
    "/{tournament_id}",
    response_model=TournamentDetail,
    summary="Get tournament details",
    description="Get detailed information about a specific tournament with optional full deck info",
)
async def get_tournament_details(
    tournament_id: int,
    include_deck: bool = Query(False, description="Include full card details for user's deck"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db),
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
            raise HTTPException(status_code=404, detail=f"Tournament with id {tournament_id} not found")

        # Count participants
        participants_count_query = (
            select(func.count())
            .select_from(TournamentDeck)
            .where(TournamentDeck.tournament_id == tournament.id, TournamentDeck.is_active == True)
        )
        participants_result = await db.execute(participants_count_query)
        participants_count = participants_result.scalar() or 0

        # Initialize prize config service
        prize_service = PrizeConfigService(db)

        # Get prize pools information (базовые + расчётные)
        prize_pools_info = None
        estimated_final_prize_pools_info = None

        if tournament.prize_pools:
            prize_pools_info = {}
            estimated_final_prize_pools_info = {}

            # Получаем все reward types за один запрос
            reward_type_ids = [int(rid) for rid in tournament.prize_pools.keys()]
            reward_types_query = select(RewardType).where(RewardType.id.in_(reward_type_ids))
            reward_types_result = await db.execute(reward_types_query)
            reward_types = reward_types_result.scalars().all()

            # Создаем словарь для быстрого доступа
            reward_types_dict = {str(rt.id): rt for rt in reward_types}

            # Формируем prize_pools_info (базовые) и estimated_final_prize_pools (расчётные)
            for reward_type_id, base_amount in tournament.prize_pools.items():
                reward_type = reward_types_dict.get(reward_type_id)
                if reward_type:
                    # Базовый prize pool
                    base_amount_float = float(base_amount)
                    prize_pools_info[reward_type_id] = {
                        "amount": str(base_amount_float),
                        "currency_name": reward_type.name,
                    }

                    # Расчётный финальный prize pool с учётом участников
                    final_amount = prize_service.calculate_dynamic_prize_pool(
                        base_prize_pool=float(base_amount), total_participants=participants_count
                    )
                    estimated_final_prize_pools_info[reward_type_id] = {
                        "amount": str(round(final_amount, 2)),
                        "currency_name": reward_type.name,
                    }

        # Get user info if authenticated
        user_id = current_user.get("user_id") if current_user else None
        is_registered = False
        my_deck = None

        if user_id:
            deck_query = select(TournamentDeck).where(
                TournamentDeck.tournament_id == tournament.id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True,
            )
            deck_result = await db.execute(deck_query)
            deck = deck_result.scalar_one_or_none()

            if deck:
                is_registered = True
                deck_composition = deck.deck_composition if isinstance(deck.deck_composition, list) else None

                if deck_composition:
                    if include_deck:
                        # Для FINISHED турниров используем исторические scores из TournamentResult
                        if tournament.status == TournamentStatus.FINISHED:
                            # Получаем result для этой деки (deck уже найден выше)
                            result_query = select(TournamentResult).where(
                                TournamentResult.tournament_deck_id == deck.id  # ✅ Проще!
                            )
                            result = (await db.execute(result_query)).scalar_one_or_none()

                            if result:
                                # Используем исторические scores
                                my_deck = await get_historical_cards_info(
                                    user_card_ids=deck_composition,
                                    card_scores=result.card_scores,
                                    tournament_id=tournament.id,
                                    db=db,
                                )
                            else:
                                # Если результата нет - показываем просто состав
                                my_deck = deck_composition
                        else:
                            # Для REGISTRATION/ONGOING используем live данные из view
                            my_deck = await get_full_cards_info(deck_composition, db)
                    else:
                        my_deck = deck_composition

        return TournamentDetail(
            id=tournament.id,
            tournament_number=tournament.tournament_number,
            status=tournament.status,
            start_date=tournament.start_date,
            end_date=tournament.end_date,
            gameplay_start_date=tournament.gameplay_start_date,
            weight_limit=tournament.weight_limit,
            prize_pools=prize_pools_info,  # Базовые prize pools
            estimated_final_prize_pools=estimated_final_prize_pools_info,  # Расчётные prize pools
            participants_count=participants_count,
            is_active=tournament.is_active,
            duration_days=tournament.duration_days,
            is_registered=is_registered,
            my_deck=my_deck,
            created_at=tournament.created_at,
            updated_at=tournament.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve tournament details: {str(e)}"
        )


async def get_cards_info(user_card_ids: list[int], db: AsyncSession) -> list[CardInDeck]:
    """
    Получить детальную информацию о картах по их user_card_id

    Args:
        user_card_ids: Список user_cards.id из deck_composition
        db: Database session

    Returns:
        Список CardInDeck с полной информацией (включая изображения из cards)
    """
    if not user_card_ids:
        return []

    from models.card_models import Card
    from models.rarity_models import Rarity
    from models.token_models import Token
    from models.user_card_models import UserCard

    # ⭐ Получаем cards через user_cards
    cards_query = (
        select(
            UserCard.id.label("user_card_id"),
            Card.id.label("card_id"),
            Card.rendered_image_url,
            Card.template_image_url,
            Card.design_type,
            Token.id.label("token_id"),
            Token.symbol,
            Token.name,
            Rarity.name.label("rarity_name"),
        )
        .join(Card, UserCard.card_id == Card.id)
        .join(Token, Card.token_id == Token.id)
        .join(Rarity, Card.rarity_id == Rarity.id)
        .where(UserCard.id.in_(user_card_ids))
    )

    cards_result = await db.execute(cards_query)
    cards_rows = cards_result.all()

    # Создаем словарь для быстрого доступа по user_card_id
    cards_dict = {}
    for row in cards_rows:
        cards_dict[row.user_card_id] = CardInDeck(
            card_id=row.card_id,
            token_id=row.token_id,
            token_symbol=row.symbol,
            token_name=row.name,
            rarity=row.rarity_name,
            design_type=row.design_type,
            rendered_image_url=row.rendered_image_url,
            template_image_url=row.template_image_url,
        )

    # Возвращаем в том же порядке что и user_card_ids
    return [cards_dict[user_card_id] for user_card_id in user_card_ids if user_card_id in cards_dict]


async def get_full_cards_info(user_card_ids: list[int], db: AsyncSession) -> list[CardInDeckInfo]:
    """
    Получить ПОЛНУЮ детальную информацию о картах из деки
    Используется:
    - В GET /tournaments/{id}?include_deck=true (для своей деки)
    - В GET /tournaments/{id}/decks/{deck_id} (для любой деки с проверкой доступа)

    Args:
        user_card_ids: Список user_cards.id из deck_composition
        db: Database session

    Returns:
        Список CardInDeckInfo с полной информацией (score, tournament_change, market_cap, images)
    """
    if not user_card_ids:
        return []

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
            ac.design_type,
            ac.rendered_image_url,
            ac.current_price,
            ac.market_cap,
            ac.tournament_change,
            ac.calculated_score
        FROM user_cards uc
        JOIN active_cards_with_score ac ON uc.card_id = ac.card_id
        WHERE uc.id = ANY(:user_card_ids)
        AND ac.is_active = true
    """)

    cards_result = await db.execute(cards_query, {"user_card_ids": user_card_ids})
    cards_rows = cards_result.fetchall()

    # Сохраняем порядок карт из deck_composition
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
            design_type=row.design_type,
            rendered_image_url=row.rendered_image_url,
            current_price=float(row.current_price) if row.current_price else None,
            market_cap=int(row.market_cap) if row.market_cap else None,
            tournament_change=float(row.tournament_change) if row.tournament_change else None,
            calculated_score=float(row.calculated_score) if row.calculated_score else 0.0,
        )

    # Возвращаем в том же порядке что в deck_composition
    return [cards_dict[card_id] for card_id in user_card_ids if card_id in cards_dict]


async def get_prizes_info(prizes_json: dict, db: AsyncSession) -> list[PrizeInfo]:
    """
    Преобразует prizes JSON в список PrizeInfo с названиями наград.

    Args:
        prizes_json: {"1": "12250.50", "2": "45000.00"}
        db: Database session

    Returns:
        List[PrizeInfo]
    """
    if not prizes_json:
        return []

    prize_list = []

    for reward_type_id_str, amount_str in prizes_json.items():
        reward_type_id = int(reward_type_id_str)

        # Получаем информацию о reward_type
        reward_query = select(RewardType).where(RewardType.id == reward_type_id)
        reward_result = await db.execute(reward_query)
        reward_type = reward_result.scalar_one_or_none()

        if reward_type:
            prize_list.append(
                PrizeInfo(
                    reward_type_id=reward_type_id,
                    reward_name=reward_type.name,
                    reward_category=reward_type.reward_category,
                    currency_type=reward_type.currency_type,
                    amount=amount_str,
                )
            )
        else:
            logger.warning(f"RewardType {reward_type_id} not found")

    return prize_list


async def get_historical_cards_info(
    user_card_ids: list[int], card_scores: Optional[Union[dict, list]], tournament_id: int, db: AsyncSession
) -> list[CardInDeckInfo]:
    """
    Получить информацию о картах с историческими скорами из TournamentResult.

    Args:
        user_card_ids: Список user_cards.id из deck_composition
        card_scores: JSON из TournamentResult.card_scores
                    Может быть dict {"card_id": score} или list [score1, score2, score3]
        tournament_id: ID турнира для получения price_change из token_scores
        db: Database session

    Returns:
        Список CardInDeckInfo с историческими скорами
    """
    if not user_card_ids:
        return []

    # 1. Получаем базовую информацию о картах
    cards_query = text("""
        SELECT 
            uc.id as user_card_id,
            c.id as card_id,
            c.token_id,
            t.symbol as token_symbol,
            t.name as token_name,
            t.image_url as token_image_url,
            t.weight as token_weight,
            r.name as rarity_name,
            r.color as rarity_color,
            c.design_type,
            c.rendered_image_url
        FROM user_cards uc
        JOIN cards c ON uc.card_id = c.id
        JOIN tokens t ON c.token_id = t.id
        JOIN rarities r ON c.rarity_id = r.id
        WHERE uc.id = ANY(:user_card_ids)
    """)

    cards_result = await db.execute(cards_query, {"user_card_ids": user_card_ids})
    cards_rows = cards_result.fetchall()

    if not cards_rows:
        return []

    # 2. Получаем token_ids для запроса token_scores
    token_ids = [row.token_id for row in cards_rows]

    # 3. Получаем последние записи price_change для каждого токена в этом турнире
    token_changes_query = text("""
        WITH latest_scores AS (
            SELECT 
                token_id,
                price_change_percent,
                ROW_NUMBER() OVER (PARTITION BY token_id ORDER BY calculated_at DESC) as rn
            FROM token_scores
            WHERE tournament_id = :tournament_id
            AND token_id = ANY(:token_ids)
        )
        SELECT token_id, price_change_percent
        FROM latest_scores
        WHERE rn = 1
    """)

    changes_result = await db.execute(token_changes_query, {"tournament_id": tournament_id, "token_ids": token_ids})
    changes_rows = changes_result.fetchall()

    # Словарь {token_id: price_change_percent}
    token_changes = {row.token_id: float(row.price_change_percent) for row in changes_rows}

    scores_dict = {}

    if card_scores:
        if isinstance(card_scores, dict):
            # Формат: {"card_id": score}
            for card_id_str, score_value in card_scores.items():
                scores_dict[int(card_id_str)] = float(score_value)
        elif isinstance(card_scores, list):
            # Формат: [score1, score2, score3]
            # Сопоставляем индексы с user_card_ids (порядок важен!)
            for idx, user_card_id in enumerate(user_card_ids):
                if idx < len(card_scores):
                    # Находим card_id по user_card_id
                    for row in cards_rows:
                        if row.user_card_id == user_card_id:
                            scores_dict[row.card_id] = float(card_scores[idx])
                            break

    # 5. Формируем результат
    cards_dict = {}
    for row in cards_rows:
        card_id = row.card_id
        token_id = row.token_id

        cards_dict[row.user_card_id] = CardInDeckInfo(
            user_card_id=row.user_card_id,
            card_id=card_id,
            token_symbol=row.token_symbol,
            token_name=row.token_name,
            token_image_url=row.token_image_url,
            token_weight=row.token_weight,
            rarity_name=row.rarity_name,
            rarity_color=row.rarity_color,
            design_type=row.design_type,
            rendered_image_url=row.rendered_image_url,
            tournament_change=token_changes.get(token_id),
            calculated_score=scores_dict.get(card_id, 0.0),
        )

    # Возвращаем в том же порядке
    return [cards_dict[card_id] for card_id in user_card_ids if card_id in cards_dict]


@router.get(
    "/{tournament_id}/decks/{deck_id}",
    response_model=DeckDetailResponse,
    summary="Get specific deck details",
    description="Get full deck information by deck_id with historical scores",
)
async def get_deck_details(
    tournament_id: int,
    deck_id: int,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        # 1. Проверяем турнир
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament_result = await db.execute(tournament_query)
        tournament = tournament_result.scalar_one_or_none()

        if not tournament:
            raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

        # 2. Получаем деку + результат + пользователя
        deck_query = (
            select(
                TournamentDeck,
                User.wallet_address,
                User.nickname,
                User.avatar_url,
                TournamentResult.final_position,
                TournamentResult.final_score,
                TournamentResult.card_scores,
                TournamentResult.prizes,
            )
            .join(User, TournamentDeck.user_id == User.id)
            .outerjoin(TournamentResult, TournamentResult.tournament_deck_id == TournamentDeck.id)
            .where(
                TournamentDeck.id == deck_id,
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.is_active == True,
            )
        )

        deck_result = await db.execute(deck_query)
        deck_row = deck_result.first()

        if not deck_row:
            raise HTTPException(status_code=404, detail=f"Deck {deck_id} not found")

        deck, wallet_address, nickname, avatar_url, position, score, card_scores, prizes_json = deck_row

        # 3. Проверка доступа
        user_id = current_user.get("user_id") if current_user else None
        is_own_deck = user_id == deck.user_id

        if not is_own_deck:
            if tournament.status not in [TournamentStatus.ONGOING, TournamentStatus.FINISHED]:
                raise HTTPException(
                    status_code=403, detail=f"Cannot view other players' decks during '{tournament.status}' phase"
                )

        # 4. Парсим deck_composition
        card_ids = []
        if deck.deck_composition:
            for card_entry in deck.deck_composition:
                if isinstance(card_entry, dict):
                    card_ids.append(card_entry.get("card_id"))
                elif isinstance(card_entry, int):
                    card_ids.append(card_entry)

        if not card_ids:
            raise HTTPException(status_code=404, detail="Deck composition is empty")

        cards_info = await get_historical_cards_info(
            user_card_ids=card_ids, card_scores=card_scores, tournament_id=tournament_id, db=db
        )

        # 6. Получаем призы
        prizes_info = None
        if prizes_json:
            prizes_info = await get_prizes_info(prizes_json, db)

        # 7. Формируем ответ
        return DeckDetailResponse(
            deck_id=deck.id,
            tournament_id=tournament.id,
            tournament_number=tournament.tournament_number,
            tournament_status=tournament.status,
            user_id=deck.user_id,
            wallet_address=wallet_address,
            nickname=nickname,
            avatar_url=avatar_url,
            deck_composition=card_ids,
            cards=cards_info,
            total_weight=float(deck.total_weight),
            submitted_at=deck.submitted_at,
            position=position,
            final_score=float(score) if score else None,
            prizes=prizes_info,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting deck {deck_id} details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve deck details: {str(e)}"
        )


@router.get(
    "/{tournament_id}/leaderboard",
    response_model=LeaderboardResponse,
    summary="Get tournament leaderboard",
    description="Get paginated leaderboard with optional user position highlight",
)
async def get_tournament_leaderboard(
    tournament_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get tournament leaderboard with pagination and prizes
    - **tournament_id**: Tournament ID
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 50, max: 100)
    - **Authorization** (optional): If provided, returns user's position even if not in top 50

    Returns:
    - Top N participants for current page with full card info and prizes
    - Total participants count
    - Pagination info
    - User's position (if authenticated and has registered deck)
    - Last calculation timestamp
    """
    try:
        # Проверяем что турнир существует
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament_result = await db.execute(tournament_query)
        tournament = tournament_result.scalar_one_or_none()

        if not tournament:
            raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

        # Получаем общее количество участников с результатами
        total_query = (
            select(func.count()).select_from(TournamentResult).where(TournamentResult.tournament_id == tournament_id)
        )
        total_result = await db.execute(total_query)
        total_participants = total_result.scalar() or 0

        if total_participants == 0:
            return LeaderboardResponse(
                tournament_id=tournament.id,
                tournament_number=tournament.tournament_number,
                status=tournament.status,
                leaderboard=[],
                total_participants=0,
                page=page,
                limit=limit,
                has_next=False,
                has_prev=False,
                my_position=None,
                last_updated=None,
            )

        # Получаем время последнего обновления
        last_updated_query = select(func.max(TournamentResult.calculated_at)).where(
            TournamentResult.tournament_id == tournament_id
        )
        last_updated_result = await db.execute(last_updated_query)
        last_updated = last_updated_result.scalar()

        # Получаем лидерборд с пагинацией
        offset = (page - 1) * limit

        leaderboard_query = (
            select(TournamentResult, TournamentDeck, User.wallet_address, User.nickname, User.avatar_url)
            .join(TournamentDeck, TournamentResult.tournament_deck_id == TournamentDeck.id)
            .join(User, TournamentDeck.user_id == User.id)
            .where(TournamentResult.tournament_id == tournament_id)
            .order_by(TournamentResult.final_position.asc())
            .offset(offset)
            .limit(limit)
        )

        leaderboard_result = await db.execute(leaderboard_query)
        leaderboard_rows = leaderboard_result.all()

        # Формируем список лидеров
        leaderboard = []
        for result, deck, wallet_address, nickname, avatar_url in leaderboard_rows:
            # Поддержка двух форматов deck_composition
            card_ids = []
            if deck.deck_composition:
                for card_entry in deck.deck_composition:
                    if isinstance(card_entry, dict):
                        card_ids.append(card_entry.get("card_id"))
                    elif isinstance(card_entry, int):
                        card_ids.append(card_entry)

            # Получаем детальную информацию о картах
            cards_info = await get_cards_info(card_ids, db)

            # Получаем информацию о призах
            prizes_info = await get_prizes_info(result.prizes, db)

            leaderboard.append(
                LeaderboardEntry(
                    position=result.final_position,
                    deck_id=deck.id,
                    user_id=deck.user_id,
                    wallet_address=wallet_address,
                    nickname=nickname,
                    avatar_url=avatar_url,
                    final_score=float(result.final_score),
                    deck_composition=card_ids,
                    cards=cards_info,
                    prizes=prizes_info,
                    calculated_at=result.calculated_at,
                )
            )

        # Получаем позицию текущего пользователя (если authenticated)
        my_position = None
        user_id = current_user.get("user_id") if current_user else None

        if user_id:
            user_deck_query = (
                select(TournamentDeck, User.wallet_address, User.nickname, User.avatar_url)
                .join(User, TournamentDeck.user_id == User.id)
                .where(
                    TournamentDeck.tournament_id == tournament_id,
                    TournamentDeck.user_id == user_id,
                    TournamentDeck.is_active == True,
                )
            )
            user_deck_result = await db.execute(user_deck_query)
            user_deck_row = user_deck_result.first()

            if user_deck_row:
                user_deck, user_wallet, user_nickname, user_avatar = user_deck_row

                # Получаем результат пользователя
                user_result_query = select(TournamentResult).where(TournamentResult.tournament_deck_id == user_deck.id)
                user_result_result = await db.execute(user_result_query)
                user_result = user_result_result.scalar_one_or_none()

                if user_result:
                    # Парсим card_ids из дека пользователя
                    user_card_ids = []
                    if user_deck.deck_composition:
                        for card_entry in user_deck.deck_composition:
                            if isinstance(card_entry, dict):
                                user_card_ids.append(card_entry.get("card_id"))
                            elif isinstance(card_entry, int):
                                user_card_ids.append(card_entry)

                    # Получаем детальную информацию о картах пользователя
                    user_cards_info = await get_cards_info(user_card_ids, db)

                    # Получаем призы пользователя
                    user_prizes_info = await get_prizes_info(user_result.prizes, db)

                    my_position = LeaderboardEntry(
                        position=user_result.final_position,
                        deck_id=user_deck.id,
                        user_id=user_deck.user_id,
                        wallet_address=user_wallet,
                        nickname=user_nickname,
                        avatar_url=user_avatar,
                        final_score=float(user_result.final_score),
                        deck_composition=user_card_ids,
                        cards=user_cards_info,
                        prizes=user_prizes_info,
                        calculated_at=user_result.calculated_at,
                    )

        return LeaderboardResponse(
            tournament_id=tournament.id,
            tournament_number=tournament.tournament_number,
            status=tournament.status,
            leaderboard=leaderboard,
            total_participants=total_participants,
            page=page,
            limit=limit,
            has_next=(offset + limit) < total_participants,
            has_prev=page > 1,
            my_position=my_position,
            last_updated=last_updated,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leaderboard for tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve leaderboard: {str(e)}"
        )


# ==================== Blockchain-Verified Registration ====================


@router.post(
    "/{tournament_id}/validate-deck",
    response_model=DeckValidateResponse,
    summary="Validate deck before registration (Pre-validation)",
    description="Validates deck composition and returns deck_hash for smart contract call",
)
async def validate_deck_for_registration(
    tournament_id: int,
    request: DeckValidateRequest,
    current_user: dict = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_async_db),
):
    """
    ШАГ 1: Пре-валидация деки БЕЗ записи в БД

    Фронтенд должен:
    1. Вызвать этот эндпоинт
    2. Получить deck_hash
    3. Вызвать контракт: registerDeck(tournamentId, deck_hash)
    4. После успеха контракта вызвать POST /register с tx_hash
    """
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user data in token")

        # Пре-валидация без записи в БД
        validation_result = await TournamentRegistrationService.validate_deck_preview(
            db=db, tournament_id=tournament_id, user_id=user_id, deck_composition=request.deck_composition
        )

        # Рекомендация сети по балансу газа (Abstract vs Avalanche)
        wallet = (current_user.get("wallet_address") or "").strip()
        if not wallet:
            user_wallet = (await db.execute(select(User.wallet_address).where(User.id == user_id))).scalar_one_or_none()
            if user_wallet:
                wallet = (user_wallet or "").strip()
            if not wallet:
                logger.warning("validate-deck: no wallet_address in JWT and user %s has no wallet in DB", user_id)
        network_rec = await TournamentRegistrationService.get_registration_network_recommendation(wallet)
        message = network_rec.get("message") or validation_result["message"]

        # Форматируем ответ
        cards_info = [
            CardInDeckResponse(
                user_card_id=card["user_card_id"],
                card_name=card["card_name"],
                rarity=card["rarity"],
                weight=card["weight"],
            )
            for card in validation_result["cards"]
        ]

        return DeckValidateResponse(
            valid=validation_result["valid"],
            deck_hash=validation_result["deck_hash"],
            total_weight=validation_result["total_weight"],
            weight_limit=validation_result["weight_limit"],
            cards=cards_info,
            message=message,
            preferred_network=network_rec["preferred_network"],
            switch_network_required=network_rec["switch_network_required"],
            avalanche_chain_id=network_rec.get("avalanche_chain_id"),
            avalanche_contract_address=network_rec.get("avalanche_contract_address"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating deck for tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to validate deck: {str(e)}"
        )


@router.post(
    "/{tournament_id}/register",
    response_model=DeckRegisterResponse,
    summary="Register for tournament with blockchain verification",
    description="Finalizes registration after smart contract transaction is confirmed",
)
async def register_for_tournament(
    tournament_id: int,
    request: DeckRegisterRequest,
    current_user: dict = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_async_db),
):
    """
    ШАГ 2: Финальная регистрация с проверкой блокчейн-транзакции

    Вызывается ПОСЛЕ того как юзер успешно вызвал registerDeck в контракте.
    Проверяет транзакцию, блокирует карты, сохраняет в БД.
    """
    try:
        user_id = current_user.get("user_id")
        user_wallet = current_user.get("wallet_address")

        if not user_id or not user_wallet:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data in token. Missing user_id or wallet_address",
            )

        # Логируем сеть для отладки
        logger.info(f"Registering for tournament {tournament_id}: tx_hash={request.tx_hash}, network={request.network}")

        # Финальная регистрация с проверкой транзакции (сеть: abstract или avalanche)
        tournament_deck = await TournamentRegistrationService.register_deck_with_verification(
            db=db,
            tournament_id=tournament_id,
            user_id=user_id,
            user_wallet=user_wallet,
            deck_composition=request.deck_composition,
            tx_hash=request.tx_hash,
            network=request.network,
        )

        # Получаем информацию о картах для ответа
        cards_query = (
            select(UserCard, Card, Token, Rarity)
            .join(Card, UserCard.card_id == Card.id)
            .join(Token, Card.token_id == Token.id)
            .join(Rarity, Card.rarity_id == Rarity.id)
            .where(UserCard.id.in_(request.deck_composition))
        )

        cards_result = (await db.execute(cards_query)).all()

        cards_info = [
            CardInDeckResponse(
                user_card_id=user_card.id, card_name=token.name, rarity=rarity.name, weight=float(token.weight)
            )
            for user_card, card, token, rarity in cards_result
        ]

        return DeckRegisterResponse(
            success=True,
            deck_id=tournament_deck.id,
            deck_hash=tournament_deck.deck_hash,
            tx_hash=tournament_deck.transaction_hash,
            total_weight=float(tournament_deck.total_weight),
            cards=cards_info,
            message="Successfully registered for tournament. Your cards are now locked.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering for tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to register for tournament: {str(e)}"
        )


@router.delete(
    "/{tournament_id}/unregister",
    response_model=DeckUnregisterResponse,
    summary="Unregister from tournament with blockchain verification",
    description="Cancels registration after smart contract unregister transaction",
)
async def unregister_from_tournament(
    tournament_id: int,
    request: DeckUnregisterRequest,
    current_user: dict = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Отмена регистрации с проверкой блокчейн-транзакции

    Юзер должен:
    1. Вызвать контракт: unregisterDeck(tournamentId)
    2. Вызвать этот эндпоинт с tx_hash
    3. Карты разблокируются после проверки транзакции
    """
    try:
        user_id = current_user.get("user_id")
        user_wallet = current_user.get("wallet_address")

        if not user_id or not user_wallet:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user data in token")

        # Отмена регистрации с проверкой транзакции (сеть: abstract или avalanche)
        result = await TournamentRegistrationService.unregister_deck_with_verification(
            db=db,
            tournament_id=tournament_id,
            user_id=user_id,
            user_wallet=user_wallet,
            tx_hash=request.tx_hash,
            network=request.network,
        )

        return DeckUnregisterResponse(
            success=result["success"],
            cards_unlocked=result["cards_unlocked"],
            tx_hash=result["tx_hash"],
            message=result["message"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unregistering from tournament {tournament_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to unregister from tournament: {str(e)}"
        )
