# api/routes/users.py
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.sql import text
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from models.database import get_async_db
from services.user_profile_service import user_profile_service
from api.routes.auth import verify_jwt_dependency
from models.tournament_models import Tournament
from models.tournament_deck_models import TournamentDeck, TournamentResult
from models.reward_models import RewardType, UserReward, ClaimStatus

import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# MODELS - Existing
# ============================================

class UserStats(BaseModel):
    total_cards: int
    tournaments_participated: int
    best_position: Optional[int]
    best_score: Optional[float]
    balances: Dict[str, float]


class UserCard(BaseModel):
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
    calculated_score: float
    current_price: Optional[float]
    market_cap: Optional[int]
    tournament_change: Optional[float]
    obtained_at: Optional[str]
    status: str


class UserProfileResponse(BaseModel):
    user_id: int
    wallet_address: str
    nickname: str
    avatar_url: str
    referral_route: str
    created_at: str
    stats: UserStats
    cards: Optional[List[UserCard]] = None


# ============================================
# MODELS - New for Tournament History
# ============================================

class TournamentCardInfo(BaseModel):
    """Информация о карте в турнирном деке"""
    user_card_id: int
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    rendered_image_url: Optional[str]
    design_type: str
    rarity_name: str


class TournamentRewardInfo(BaseModel):
    """Информация о награде"""
    reward_type_id: int
    reward_name: str
    reward_category: str
    currency_type: str
    amount: str
    claim_status: str  # pending, claimed, expired, cancelled
    earned_at: Optional[str]
    claimed_at: Optional[str]
    expires_at: Optional[str]


class UserTournamentHistory(BaseModel):
    """История участия в турнире"""
    tournament_id: int
    tournament_number: int
    status: str
    start_date: str
    end_date: str
    
    # Результаты пользователя
    position: int
    final_score: float
    deck_id: int
    deck_composition: List[int]  # user_card_ids
    cards: List[TournamentCardInfo]
    
    # Награды
    prizes: List[TournamentRewardInfo]
    
    # Даты
    registered_at: str
    calculated_at: Optional[str]


class UserTournamentsResponse(BaseModel):
    """Список турниров пользователя"""
    user_id: int
    wallet_address: str
    tournaments: List[UserTournamentHistory]
    total_tournaments: int
    best_position: Optional[int]
    best_score: Optional[float]


# ============================================
# ROUTES - Existing
# ============================================

@router.get(
    "/users/me",
    response_model=UserProfileResponse,
    summary="Get my profile",
    description="Get authenticated user's profile. Requires JWT token. Use ?include_cards=true to include card collection."
)
async def get_my_profile(
    include_cards: bool = Query(False, description="Include user's card collection"),
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get authenticated user's own profile
    - **include_cards**: Optional flag to include cards collection
    - Requires JWT authentication
    """
    try:
        wallet_address = current_user["wallet_address"]
        
        # Find user
        user = await user_profile_service.get_user_by_wallet(wallet_address, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get user stats
        stats = await user_profile_service.get_user_stats(user.id, db)
        
        # Prepare response
        response_data = {
            "user_id": user.id,
            "wallet_address": user.wallet_address,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "referral_route": user.referral_route,
            "created_at": user.created_at.isoformat(),
            "stats": stats
        }
        
        # Include cards if requested
        if include_cards:
            cards = await user_profile_service.get_user_cards(user.id, db)
            response_data["cards"] = cards
        
        return UserProfileResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile for authenticated user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile"
        )


@router.get(
    "/users/{wallet_address}",
    response_model=UserProfileResponse,
    summary="Get user profile",
    description="Get public user profile by wallet address. Use ?include_cards=true to include user's card collection."
)
async def get_user_profile(
    wallet_address: str,
    include_cards: bool = Query(False, description="Include user's card collection"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user public profile by wallet address
    - **wallet_address**: Ethereum wallet address (0x...)
    - **include_cards**: Optional flag to include user's cards collection
    """
    try:
        # Find user
        user = await user_profile_service.get_user_by_wallet(wallet_address, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with wallet address {wallet_address} not found"
            )
        
        # Get user stats
        stats = await user_profile_service.get_user_stats(user.id, db)
        
        # Prepare response
        response_data = {
            "user_id": user.id,
            "wallet_address": user.wallet_address,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "referral_route": user.referral_route,
            "created_at": user.created_at.isoformat(),
            "stats": stats
        }
        
        # Include cards if requested
        if include_cards:
            cards = await user_profile_service.get_user_cards(user.id, db)
            response_data["cards"] = cards
        
        return UserProfileResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user profile for {wallet_address}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )


# ============================================
# ROUTES - New Tournament History
# ============================================

@router.get(
    "/users/me/tournaments",
    response_model=UserTournamentsResponse,
    summary="Get my tournament history",
    description="Get authenticated user's tournament participation history with detailed results, cards, and reward claim status"
)
async def get_my_tournament_history(
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Получить историю участия в турнирах текущего пользователя
    - Требует JWT аутентификацию
    - Возвращает все турниры, в которых участвовал пользователь
    - Включает позицию, скор, карты, награды со статусом клейма
    """
    try:
        user_id = current_user.get('user_id')
        wallet_address = current_user.get('wallet_address')
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data in token"
            )
        
        # Получаем все ЗАВЕРШЕННЫЕ турниры пользователя с результатами
        tournaments_query = select(
            Tournament,
            TournamentDeck,
            TournamentResult
        ).join(
            TournamentDeck, 
            and_(
                TournamentDeck.tournament_id == Tournament.id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True
            )
        ).join(
            TournamentResult,
            TournamentResult.tournament_deck_id == TournamentDeck.id
        ).where(
            Tournament.status == 'finished'
        ).order_by(
            Tournament.start_date.desc()
        )
        
        result = await db.execute(tournaments_query)
        rows = result.all()
        
        tournaments_history = []
        best_position = None
        best_score = None
        
        for tournament, deck, tournament_result in rows:
            # Убираем проверку if not tournament_result, т.к. теперь результат всегда есть
            
            # Получаем информацию о картах деки
            deck_card_ids = []
            if deck.deck_composition:
                for card_entry in deck.deck_composition:
                    if isinstance(card_entry, dict):
                        deck_card_ids.append(card_entry.get('card_id'))
                    elif isinstance(card_entry, int):
                        deck_card_ids.append(card_entry)
            
            cards_info = await _get_deck_cards_info(deck_card_ids, db)
            
            # Получаем информацию о наградах со статусом клейма
            prizes_info = await _get_prizes_with_claim_status(
                tournament_result.id,
                user_id,
                db
            )
            
            # Обновляем лучшие показатели
            if tournament_result.final_position:
                if best_position is None or tournament_result.final_position < best_position:
                    best_position = tournament_result.final_position
            
            if tournament_result.final_score:
                score_value = float(tournament_result.final_score)
                if best_score is None or score_value > best_score:
                    best_score = score_value
            
            tournaments_history.append(UserTournamentHistory(
                tournament_id=tournament.id,
                tournament_number=tournament.tournament_number,
                status=tournament.status,
                start_date=tournament.start_date.isoformat(),
                end_date=tournament.end_date.isoformat(),
                position=tournament_result.final_position or 0,
                final_score=float(tournament_result.final_score) if tournament_result.final_score else 0.0,
                deck_id=deck.id,
                deck_composition=deck_card_ids,
                cards=cards_info,
                prizes=prizes_info,
                registered_at=deck.submitted_at.isoformat(),
                calculated_at=tournament_result.calculated_at.isoformat() if tournament_result.calculated_at else None
            ))
        
        return UserTournamentsResponse(
            user_id=user_id,
            wallet_address=wallet_address,
            tournaments=tournaments_history,
            total_tournaments=len(tournaments_history),
            best_position=best_position,
            best_score=best_score
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tournament history for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tournament history"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================

async def _get_deck_cards_info(card_ids: List[int], db: AsyncSession) -> List[TournamentCardInfo]:
    """Получить информацию о картах деки"""
    if not card_ids:
        return []
    
    try:
        cards_query = text("""
            SELECT 
                uc.id as user_card_id,
                c.id as card_id,
                t.symbol as token_symbol,
                t.name as token_name,
                t.image_url as token_image_url,
                c.rendered_image_url,
                c.design_type,
                r.name as rarity_name
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            JOIN tokens t ON c.token_id = t.id
            JOIN rarities r ON c.rarity_id = r.id
            WHERE uc.id = ANY(:card_ids)
            AND uc.is_active = true
        """)
        
        result = await db.execute(cards_query, {"card_ids": card_ids})
        rows = result.fetchall()
        
        cards_dict = {}
        for row in rows:
            cards_dict[row.user_card_id] = TournamentCardInfo(
                user_card_id=row.user_card_id,
                card_id=row.card_id,
                token_symbol=row.token_symbol,
                token_name=row.token_name,
                token_image_url=row.token_image_url,
                rendered_image_url=row.rendered_image_url,
                design_type=row.design_type,
                rarity_name=row.rarity_name
            )
        
        # Возвращаем в том же порядке, что и в деке
        return [cards_dict[card_id] for card_id in card_ids if card_id in cards_dict]
    
    except Exception as e:
        logger.error(f"Error getting deck cards info: {e}")
        return []


async def _get_prizes_with_claim_status(
    tournament_result_id: int,
    user_id: int,
    db: AsyncSession
) -> List[TournamentRewardInfo]:
    """
    Получить информацию о наградах пользователя со статусом клейма
    из таблицы user_rewards
    """
    try:
        # Получаем все награды пользователя за этот турнир
        rewards_query = select(
            UserReward,
            RewardType
        ).join(
            RewardType,
            UserReward.reward_type_id == RewardType.id
        ).where(
            and_(
                UserReward.user_id == user_id,
                UserReward.tournament_result_id == tournament_result_id
            )
        )
        
        result = await db.execute(rewards_query)
        rows = result.all()
        
        prize_list = []
        
        for user_reward, reward_type in rows:
            prize_list.append(TournamentRewardInfo(
                reward_type_id=reward_type.id,
                reward_name=reward_type.name,
                reward_category=reward_type.reward_category,
                currency_type=reward_type.currency_type,
                amount=str(user_reward.amount),
                claim_status=user_reward.claim_status,  # pending, claimed, expired, cancelled
                earned_at=user_reward.earned_at.isoformat() if user_reward.earned_at else None,
                claimed_at=user_reward.claimed_at.isoformat() if user_reward.claimed_at else None,
                expires_at=user_reward.expires_at.isoformat() if user_reward.expires_at else None
            ))
        
        return prize_list
    
    except Exception as e:
        logger.error(f"Error getting prizes with claim status: {e}", exc_info=True)
        return []