# services/user_profile_service.py

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
from models.user_models import User
from models.user_card_models import UserCard
from models.tournament_deck_models import TournamentDeck, TournamentResult
from models.database import get_async_db
import logging

logger = logging.getLogger(__name__)


class UserProfileService:
    """Service for fetching user profiles and statistics"""

    async def get_user_by_wallet(self, wallet_address: str, db: AsyncSession) -> Optional[User]:
        """Find user by wallet address"""
        try:
            wallet_address = wallet_address.strip().lower()
            
            result = await db.execute(
                select(User).where(User.wallet_address == wallet_address)
            )
            user = result.scalar_one_or_none()
            return user
            
        except Exception as e:
            logger.error(f"Error finding user by wallet {wallet_address}: {e}")
            return None

    async def get_user_stats(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Get user statistics"""
        try:
            stats = {}
            
            # Total cards
            total_cards_result = await db.execute(
                select(func.count(UserCard.id))
                .where(UserCard.user_id == user_id)
                .where(UserCard.is_active == True)
            )
            stats['total_cards'] = total_cards_result.scalar() or 0
            
            # Tournaments participated
            tournaments_result = await db.execute(
                select(func.count(func.distinct(TournamentDeck.tournament_id)))
                .where(TournamentDeck.user_id == user_id)
                .where(TournamentDeck.is_active == True)
            )
            stats['tournaments_participated'] = tournaments_result.scalar() or 0
            
            # Best position and score from tournament results
            results_query = await db.execute(
                select(
                    func.min(TournamentResult.final_position).label('best_position'),
                    func.max(TournamentResult.final_score).label('best_score')
                )
                .join(TournamentDeck, TournamentResult.tournament_deck_id == TournamentDeck.id)
                .where(TournamentDeck.user_id == user_id)
            )
            result_data = results_query.one_or_none()
            
            stats['best_position'] = result_data.best_position if result_data else None
            stats['best_score'] = float(result_data.best_score) if result_data and result_data.best_score else None
            
            # Balances from view
            balances_query = text("""
                SELECT reward_category, 
                       SUM(available_balance) as total_available
                FROM user_balances_view
                WHERE user_id = :user_id
                GROUP BY reward_category
            """)
            
            balances_result = await db.execute(balances_query, {"user_id": user_id})
            balances = {}
            
            for row in balances_result:
                category = row.reward_category
                amount = float(row.total_available) if row.total_available else 0
                balances[category] = amount
            
            stats['balances'] = balances
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting stats for user {user_id}: {e}")
            return {
                'total_cards': 0,
                'tournaments_participated': 0,
                'best_position': None,
                'best_score': None,
                'balances': {}
            }

    async def get_user_cards(self, user_id: int, db: AsyncSession) -> List[Dict[str, Any]]:
        """Get user cards with scores from materialized view"""
        try:
            query = text("""
                SELECT 
                    uc.id as user_card_id,
                    uc.obtained_at,
                    uc.expires_at,
                    uc.status,
                    acs.card_id,
                    acs.token_symbol,
                    acs.token_name,
                    acs.token_image_url,
                    acs.token_weight,
                    acs.rarity_name,
                    acs.rarity_color,
                    acs.design_type,
                    acs.rendered_image_url,
                    acs.current_price,
                    acs.market_cap,
                    acs.tournament_change,
                    acs.calculated_score,
                    acs.active_tournament_id,
                    acs.tournament_status
                FROM user_cards uc
                JOIN active_cards_with_score acs ON uc.card_id = acs.card_id
                WHERE uc.user_id = :user_id
                AND uc.is_active = true
                ORDER BY acs.rarity_name DESC, acs.token_symbol ASC
            """)

            result = await db.execute(query, {"user_id": user_id})
            cards = []

            for row in result:
                card_data = {
                    "user_card_id": row.user_card_id,
                    "card_id": row.card_id,
                    "token_symbol": row.token_symbol,
                    "token_name": row.token_name,
                    "token_image_url": row.token_image_url,
                    "token_weight": row.token_weight,
                    "rarity_name": row.rarity_name,
                    "rarity_color": row.rarity_color,
                    "design_type": row.design_type,
                    "rendered_image_url": row.rendered_image_url,
                    "calculated_score": float(row.calculated_score) if row.calculated_score else 0,
                    "current_price": float(row.current_price) if row.current_price else None,
                    "market_cap": int(row.market_cap) if row.market_cap else None,
                    "tournament_change": float(row.tournament_change) if row.tournament_change else None,
                    "obtained_at": row.obtained_at.isoformat() if row.obtained_at else None,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "status": row.status
                }
                cards.append(card_data)

            return cards
            
        except Exception as e:
            logger.error(f"Error getting cards for user {user_id}: {e}")
            return []


# Singleton instance
user_profile_service = UserProfileService()