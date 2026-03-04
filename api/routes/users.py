# api/routes/users.py
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.sql import text
from enum import Enum
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

class BalanceDetail(BaseModel):
    reward_type_id: int
    name: str
    category: str
    currency_type: str
    available: float
    pending: float
    pending_count: int
    claimed_count: int
    last_earned: Optional[str] = None

class UserStats(BaseModel):
    total_cards: int
    tournaments_participated: int
    best_position: Optional[int]
    best_score: Optional[float]
    balances: List[BalanceDetail]


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
    expires_at: Optional[str]
    status: str


class UserProfileResponse(BaseModel):
    user_id: int
    wallet_address: str
    nickname: str
    avatar_url: Optional[str] = None
    referral_route: str
    referral_link: Optional[str] = None
    referral_count: Optional[int] = None
    created_at: str
    onboarding_steps: Optional[Dict[str, bool]] = None
    stats: UserStats
    cards: Optional[List[UserCard]] = None


class LeaderboardUserEntry(BaseModel):
    """Public user data for leaderboard and active balances."""

    user_id: int
    wallet_address: str
    nickname: str
    avatar_url: Optional[str] = None
    referral_route: str
    created_at: str
    balances: List[BalanceDetail]


class PaginationMeta(BaseModel):
    limit: int
    offset: int
    total: int


class LeaderboardResponse(BaseModel):
    success: bool = True
    data: List[LeaderboardUserEntry]
    pagination: PaginationMeta

class UpdateOnboardingRequest(BaseModel):
    """Request to update onboarding step completion."""
    step: str  # "1", "2", "3"
    completed: bool

# ============================================
# MODELS - New for Tournament History
# ============================================

class TournamentCardInfo(BaseModel):
    """Card info in a tournament deck."""
    user_card_id: int
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    rendered_image_url: Optional[str]
    design_type: str
    rarity_name: str


class TournamentRewardInfo(BaseModel):
    """Reward information."""
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
    """User participation in a tournament."""
    tournament_id: int
    tournament_number: int
    status: str
    start_date: str
    end_date: str
    
    # User results
    position: int
    final_score: float
    deck_id: int
    deck_composition: List[int]  # user_card_ids
    cards: List[TournamentCardInfo]
    
    # Prizes
    prizes: List[TournamentRewardInfo]
    
    # Dates
    registered_at: str
    calculated_at: Optional[str]


class UserTournamentsResponse(BaseModel):
    """List of user tournaments."""
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
            "referral_link": f"https://hodleague.com?ref={user.referral_route}",
            "referral_count": user.referral_count or 0,
            "created_at": user.created_at.isoformat(),
            "onboarding_steps": user.onboarding_steps or {},
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
    
@router.patch(
    "/users/me/onboarding",
    summary="Update onboarding step",
    description="Mark onboarding step as completed or not completed"
)
async def update_onboarding_step(
    request: UpdateOnboardingRequest,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update onboarding step completion status.
    step: step number ("1", "2", "3"); completed: true/false. Requires JWT.
    """
    try:
        wallet_address = current_user["wallet_address"]
        
        # Find user
        from models.user_models import User
        user_query = select(User).where(User.wallet_address == wallet_address)
        result = await db.execute(user_query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Initialize onboarding_steps if null
        if user.onboarding_steps is None:
            user.onboarding_steps = {}
        
        # Update the step
        user.onboarding_steps[request.step] = request.completed
        
        # Mark as updated (for onupdate trigger)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, "onboarding_steps")
        
        await db.commit()
        await db.refresh(user)
        
        return {
            "success": True,
            "onboarding_steps": user.onboarding_steps,
            "message": f"Step {request.step} updated to {request.completed}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating onboarding step: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update onboarding step"
        )


@router.get(
    "/users/me/onboarding",
    summary="Get onboarding status",
    description="Get current onboarding steps status"
)
async def get_onboarding_status(
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current onboarding status. Requires JWT. Returns onboarding_steps only.
    """
    try:
        wallet_address = current_user["wallet_address"]
        
        # Find user
        from models.user_models import User
        user_query = select(User).where(User.wallet_address == wallet_address)
        result = await db.execute(user_query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "onboarding_steps": user.onboarding_steps or {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get onboarding status"
        )


class LeaderboardSortBy(str, Enum):
    balance = "balance"
    created_at = "created_at"


class LeaderboardSortOrder(str, Enum):
    desc = "desc"
    asc = "asc"


@router.get(
    "/users/leaderboard",
    response_model=LeaderboardResponse,
    summary="Public user leaderboard",
    description="Paginated list of users with public info and active balances. Sort by balance (total available) or created_at. No auth required.",
)
async def get_leaderboard(
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    sort_by: LeaderboardSortBy = Query(
        default=LeaderboardSortBy.balance,
        description="Sort by total available balance or created_at",
    ),
    sort_order: LeaderboardSortOrder = Query(
        default=LeaderboardSortOrder.desc,
        description="Sort direction",
    ),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Public leaderboard: top by balance (sum of available per reward type) or by registration date.
    """
    from models.user_models import User

    try:
        count_query = select(func.count(User.id)).where(User.is_active == True)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        if sort_by == LeaderboardSortBy.balance:
            # Sort by sum of available_balance across reward types
            order_dir = "DESC" if sort_order == LeaderboardSortOrder.desc else "ASC"
            ids_query = text(
                "SELECT u.id FROM users u "
                "LEFT JOIN ("
                "  SELECT user_id, SUM(available_balance) AS total "
                "  FROM user_balances_view GROUP BY user_id"
                ") bal ON u.id = bal.user_id "
                "WHERE u.is_active = true "
                f"ORDER BY COALESCE(bal.total, 0) {order_dir} NULLS LAST, u.created_at DESC "
                "LIMIT :limit OFFSET :offset"
            )
            ids_result = await db.execute(ids_query, {"limit": limit, "offset": offset})
            user_ids = [row.id for row in ids_result.fetchall()]
            if not user_ids:
                return LeaderboardResponse(
                    success=True,
                    data=[],
                    pagination=PaginationMeta(limit=limit, offset=offset, total=total),
                )
            users_query = select(User).where(User.id.in_(user_ids))
            users_result = await db.execute(users_query)
            users_by_id = {u.id: u for u in users_result.scalars().all()}
            users = [users_by_id[uid] for uid in user_ids if uid in users_by_id]
        else:
            order_created = User.created_at.desc() if sort_order == LeaderboardSortOrder.desc else User.created_at.asc()
            users_query = (
                select(User)
                .where(User.is_active == True)
                .order_by(order_created)
                .limit(limit)
                .offset(offset)
            )
            result = await db.execute(users_query)
            users = result.scalars().all()

        if not users:
            return LeaderboardResponse(
                success=True,
                data=[],
                pagination=PaginationMeta(limit=limit, offset=offset, total=total),
            )

        user_ids = [u.id for u in users]
        balances_map = await user_profile_service.get_balances_batch(user_ids, db)

        data = []
        for user in users:
            balances = balances_map.get(user.id, [])
            data.append(
                LeaderboardUserEntry(
                    user_id=user.id,
                    wallet_address=user.wallet_address,
                    nickname=user.nickname,
                    avatar_url=user.avatar_url,
                    referral_route=user.referral_route,
                    created_at=user.created_at.isoformat(),
                    balances=[BalanceDetail(**b) for b in balances],
                )
            )

        return LeaderboardResponse(
            success=True,
            data=data,
            pagination=PaginationMeta(limit=limit, offset=offset, total=total),
        )
    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve leaderboard",
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


# ROUTES - New Tournament History

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
    Get current user's tournament participation history.
    Requires JWT. Returns all tournaments the user participated in, with position, score, cards, and reward claim status.
    """
    try:
        user_id = current_user.get('user_id')
        wallet_address = current_user.get('wallet_address')
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data in token"
            )
        
        # Load all FINISHED tournaments for user with results
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
            # Result is always present for finished tournaments
            
            # Load deck card info
            deck_card_ids = []
            if deck.deck_composition:
                for card_entry in deck.deck_composition:
                    if isinstance(card_entry, dict):
                        deck_card_ids.append(card_entry.get('card_id'))
                    elif isinstance(card_entry, int):
                        deck_card_ids.append(card_entry)
            
            cards_info = await _get_deck_cards_info(deck_card_ids, db)
            
            # Load prizes with claim status
            prizes_info = await _get_prizes_with_claim_status(
                tournament_result.id,
                user_id,
                db
            )
            
            # Update best position/score
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


# HELPER FUNCTIONS

async def _get_deck_cards_info(card_ids: List[int], db: AsyncSession) -> List[TournamentCardInfo]:
    """Get deck card info by card IDs."""
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
        
        # Return in same order as deck
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
    Get user rewards with claim status from user_rewards table.
    """
    try:
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