# services/card_score_service.py

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)


class CardScoreService:
    """Service for managing card scores and materialized view"""

    async def refresh_cards_view(self, db: AsyncSession = None):
        """Refresh materialized view with latest card data and scores"""
        try:
            if db is None:
                async with AsyncSessionLocal() as db:
                    await db.execute(text("REFRESH MATERIALIZED VIEW active_cards_with_score"))
                    await db.commit()
            else:
                await db.execute(text("REFRESH MATERIALIZED VIEW active_cards_with_score"))
                await db.commit()
            
            logger.info("✅ Materialized view 'active_cards_with_score' refreshed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error refreshing materialized view: {e}")
            return False

    async def create_tournament_snapshot(self, tournament_id: int, db: AsyncSession):
        """Create price snapshot for tournament start"""
        try:
            # Insert snapshot prices from latest token prices
            query = text("""
                INSERT INTO tournament_token_snapshots (tournament_id, token_id, snapshot_price, snapshot_time)
                SELECT 
                    :tournament_id,
                    tp.token_id,
                    tp.price,
                    tp.timestamp
                FROM (
                    SELECT DISTINCT ON (token_id) 
                        token_id, price, timestamp
                    FROM token_prices
                    ORDER BY token_id, timestamp DESC
                ) tp
                ON CONFLICT DO NOTHING
            """)
            
            await db.execute(query, {"tournament_id": tournament_id})
            await db.commit()
            
            logger.info(f"✅ Tournament snapshot created for tournament_id={tournament_id}")
            
            # Refresh view after snapshot
            await self.refresh_cards_view(db)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating tournament snapshot: {e}")
            await db.rollback()
            return False


# Singleton instance
card_score_service = CardScoreService()