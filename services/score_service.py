# services/score_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, distinct
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Tuple
import math

from models.token_score_models import TokenScore
from models.token_models import Token, TokenPrice
from models.tournament_models import Tournament, TournamentTokenSnapshot


class ScoreService:
    """
    Service for calculating and storing historical token scores during tournaments.
    Uses the same formula as the crypto simulation.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_and_store_scores(self, tournament_id: int) -> int:
        """
        Calculate scores for all active tokens in a tournament and store them.
        """
        # Get tournament
        tournament = await self._get_tournament(tournament_id)
        if not tournament:
            raise ValueError(f"Tournament {tournament_id} not found")
        if tournament.status != "ongoing":
            raise ValueError(f"Tournament {tournament_id} is not in ONGOING status (current: {tournament.status})")

        # Get all active tokens with their current prices and snapshots
        token_data = await self._get_token_data_for_tournament(tournament_id)
        if not token_data:
            return 0

        # Calculate period_change and activity for each token
        scored_tokens = []
        for data in token_data:
            period_change = self._calculate_period_change(
                data['current_price'], 
                data['snapshot_price']
            )
            activity = await self._calculate_activity(
                data['token_id'],
                tournament.start_date
            )

            scored_tokens.append({
                'token_id': data['token_id'],
                'current_price': data['current_price'],
                'snapshot_price': data['snapshot_price'],
                'market_cap': data['market_cap'],
                'period_change': period_change,
                'activity': activity,
            })

        all_zero_change = all(t['period_change'] == 0 for t in scored_tokens)
        all_zero_activity = all(t['activity'] == 0 for t in scored_tokens)
        
        calculated_at = datetime.now(timezone.utc)
        scores_to_insert = []
        
        if all_zero_change and all_zero_activity:
            for token in scored_tokens:
                token_score = TokenScore(
                    tournament_id=tournament_id,
                    token_id=token['token_id'],
                    calculated_score=Decimal('0'),  # Everyone gets 0 at start
                    current_price=token['current_price'],
                    snapshot_price=token['snapshot_price'],
                    price_change_percent=token['period_change'],
                    calculated_at=calculated_at
                )
                scores_to_insert.append(token_score)
        else:
            # Normal scoring logic
            # Rank tokens
            scored_tokens = self._rank_tokens(scored_tokens)

            # Calculate market cap factors
            all_market_caps = [t['market_cap'] for t in scored_tokens]

            # Calculate raw scores
            total_tokens = len(scored_tokens)
            raw_scores = []
            for token in scored_tokens:
                mc_factor = self._calculate_mc_factor(token['market_cap'], all_market_caps)
                weekly_points = total_tokens - token['change_rank'] + 1
                activity_points = total_tokens - token['activity_rank'] + 1
                raw_score = (weekly_points * mc_factor * 4) + (activity_points * mc_factor * 1)
                token['raw_score'] = raw_score
                raw_scores.append(raw_score)

            # Normalize scores to 1000
            min_raw = min(raw_scores)
            max_raw = max(raw_scores)
            range_raw = max_raw - min_raw

            for token in scored_tokens:
                if range_raw == 0:
                    final_score = 0  # All equal → 0 score
                else:
                    normalized = (token['raw_score'] - min_raw) / range_raw
                    final_score = min(int(1000 * (normalized ** 0.7)), 1000)

                # Create TokenScore record
                token_score = TokenScore(
                    tournament_id=tournament_id,
                    token_id=token['token_id'],
                    calculated_score=Decimal(str(final_score)),
                    current_price=token['current_price'],
                    snapshot_price=token['snapshot_price'],
                    price_change_percent=token['period_change'],
                    calculated_at=calculated_at
                )
                scores_to_insert.append(token_score)

        # Bulk insert
        if scores_to_insert:
            self.db.add_all(scores_to_insert)
            await self.db.commit()
            
            await self.refresh_active_cards_view()

        return len(scores_to_insert)


    async def refresh_active_cards_view(self) -> None:
        """
        Refresh materialized view after updating token scores.
        Tries CONCURRENTLY first, falls back to blocking refresh if needed.
        """
        from sqlalchemy import text
        
        try:
            await self.db.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY active_cards_with_score")
            )
            await self.db.commit()
        except Exception as e:
            # Fallback to non-concurrent refresh
            await self.db.rollback()
            await self.db.execute(
                text("REFRESH MATERIALIZED VIEW active_cards_with_score")
            )
            await self.db.commit()
    
    def _calculate_period_change(self, current_price: Decimal, snapshot_price: Decimal) -> Decimal:
        """
        Calculate percentage change from snapshot to current price.
        """
        if snapshot_price == 0:
            return Decimal(0)
        
        return ((current_price - snapshot_price) / snapshot_price) * 100
    
    async def _calculate_activity(self, token_id: int, tournament_start: datetime) -> Decimal:
        """
        Calculate activity (volatility) as sum of absolute percentage changes.
        Matches simulation formula exactly: sum(abs((price[i] - price[i-1]) / price[i-1] * 100))
        
        Since all tokens participate equally with same update frequency,
        direct summation is fair and comparable.
        """
        result = await self.db.execute(
            select(TokenPrice.price)
            .where(
                and_(
                    TokenPrice.token_id == token_id,
                    TokenPrice.timestamp >= tournament_start
                )
            )
            .order_by(TokenPrice.timestamp.asc())
        )
        
        prices = [row[0] for row in result.all()]
        
        if len(prices) < 2:
            return Decimal(0)
        
        # Exact formula from simulation
        activity = Decimal(0)
        for i in range(1, len(prices)):
            if prices[i-1] > 0:  # Защита от деления на ноль
                # abs((новая - старая) / старая) * 100
                pct_change = abs((prices[i] - prices[i-1]) / prices[i-1]) * 100
                activity += pct_change
        
        return activity
    
    def _rank_tokens(self, tokens: List[Dict]) -> List[Dict]:
        """
        Rank tokens by period_change and activity.
        Uses stable sorting with token_id as tiebreaker.
        """
        # Rank by period_change (descending - higher is better)
        # Secondary sort by token_id for stability
        sorted_by_change = sorted(
            tokens, 
            key=lambda x: (x['period_change'], -x['token_id']),  # ← стабильная сортировка
            reverse=True
        )
        for rank, token in enumerate(sorted_by_change, start=1):
            token['change_rank'] = rank
        
        # Rank by activity (descending - higher is better)
        sorted_by_activity = sorted(
            tokens, 
            key=lambda x: (x['activity'], -x['token_id']),  # ← стабильная сортировка
            reverse=True
        )
        for rank, token in enumerate(sorted_by_activity, start=1):
            token['activity_rank'] = rank
        
        return tokens

    def _calculate_mc_factor(self, market_cap: int, all_market_caps: List[int]) -> float:
        """
        Calculate market cap factor using the EXACT formula from crypto_simulation.py
        
        Larger market cap = HIGHER factor = easier to get 1000 score
        Smaller market cap = LOWER factor = need bigger % gains
        
        Args:
            market_cap: Market cap in dollars (not billions)
            all_market_caps: List of all market caps in dollars
        """
        if not all_market_caps or market_cap <= 0:
            return 1.0
        
        # Convert to billions (assuming market_cap is in dollars)
        market_cap_billions = market_cap / 1_000_000_000
        all_market_caps_billions = [mc / 1_000_000_000 for mc in all_market_caps]
        
        # Calculate average market cap
        avg_market_cap_billions = sum(all_market_caps_billions) / len(all_market_caps_billions)
        
        # Relative to average
        rel = market_cap_billions / avg_market_cap_billions if avg_market_cap_billions > 0 else 1.0
        
        # EXACT formula from simulation
        mc_factor = (
            math.log(1 + rel * 2.5) * 12 +  # логарифмическое сглаживание отношения к средней капе
            math.sqrt(math.log10(market_cap_billions + 1)) * 15 +  # корень из логарифма абсолютной капы
            (rel / (1 + rel * 0.1)) * 8  # гиперболическое сглаживание для очень больших rel
        )
        
        return mc_factor
    
    async def get_scores_at_time(
        self, 
        tournament_id: int, 
        target_time: datetime,
        tolerance_minutes: int = 15
    ) -> List[TokenScore]:
        """
        Get scores closest to a target time (used for tournament finalization).
        Returns one score per token, the latest before target_time.
        """
        query = select(TokenScore).where(
            and_(
                TokenScore.tournament_id == tournament_id,
                TokenScore.calculated_at <= target_time
            )
        ).order_by(
            TokenScore.token_id,
            TokenScore.calculated_at.desc()
        )
        
        result = await self.db.execute(query)
        all_scores = result.scalars().all()
        
        # Get one score per token (the latest before target_time)
        scores_by_token = {}
        for score in all_scores:
            if score.token_id not in scores_by_token:
                scores_by_token[score.token_id] = score
        
        return list(scores_by_token.values())
    
    async def get_latest_scores(self, tournament_id: int) -> List[TokenScore]:
        """
        Get the most recent scores for all tokens in a tournament.
        Used for live leaderboard updates.
        """
        # Subquery to get max calculated_at per token
        subq = (
            select(
                TokenScore.token_id,
                func.max(TokenScore.calculated_at).label('max_time')
            )
            .where(TokenScore.tournament_id == tournament_id)
            .group_by(TokenScore.token_id)
            .subquery()
        )
        
        # Join to get full records
        query = (
            select(TokenScore)
            .join(
                subq,
                and_(
                    TokenScore.token_id == subq.c.token_id,
                    TokenScore.calculated_at == subq.c.max_time
                )
            )
            .where(TokenScore.tournament_id == tournament_id)
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    # Helper methods
    
    async def _get_tournament(self, tournament_id: int) -> Optional[Tournament]:
        result = await self.db.execute(
            select(Tournament).where(Tournament.id == tournament_id)
        )
        return result.scalar_one_or_none()
    
    async def _get_token_data_for_tournament(self, tournament_id: int) -> List[Dict]:
        """
        Get current price, snapshot price, and market cap for all active tokens.
        FIXED: Uses subquery to correctly get latest price for each token.
        """
        # Subquery to get latest price timestamp for each token
        latest_price_subq = (
            select(
                TokenPrice.token_id,
                func.max(TokenPrice.timestamp).label('max_timestamp')
            )
            .group_by(TokenPrice.token_id)
            .subquery()
        )
        
        # Join to get the actual latest price record
        query = (
            select(
                Token.id.label('token_id'),
                TokenPrice.price.label('current_price'),
                TokenPrice.market_cap.label('market_cap'),
                TournamentTokenSnapshot.snapshot_price.label('snapshot_price')
            )
            .join(
                latest_price_subq,
                Token.id == latest_price_subq.c.token_id
            )
            .join(
                TokenPrice,
                and_(
                    TokenPrice.token_id == latest_price_subq.c.token_id,
                    TokenPrice.timestamp == latest_price_subq.c.max_timestamp
                )
            )
            .join(
                TournamentTokenSnapshot,
                and_(
                    TournamentTokenSnapshot.token_id == Token.id,
                    TournamentTokenSnapshot.tournament_id == tournament_id
                )
            )
            .where(Token.is_active == True)
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'token_id': row.token_id,
                'current_price': row.current_price,
                'market_cap': row.market_cap,
                'snapshot_price': row.snapshot_price,
            }
            for row in rows
        ]