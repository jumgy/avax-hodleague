from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from models.tournament_deck_models import TournamentPrizeConfig
from utils.prize_distribution import distribute_prizes
from decimal import Decimal
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class PrizeConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_and_save_prize_structure(
        self, 
        tournament_id: int, 
        reward_type_id: int, 
        prize_pool: float, 
        total_participants: int
    ) -> int:
        """
        Генерирует структуру призов и сохраняет в TournamentPrizeConfig.
        
        Returns:
            Количество созданных записей
        """
        logger.info(
            f"📊 Generating prize structure for tournament {tournament_id}, "
            f"reward_type {reward_type_id}, pool: {prize_pool}, participants: {total_participants}"
        )
        
        # Удаляем старые записи для этого турнира и reward_type (если есть)
        await self.db.execute(
            delete(TournamentPrizeConfig).where(
                and_(
                    TournamentPrizeConfig.tournament_id == tournament_id,
                    TournamentPrizeConfig.reward_type_id == reward_type_id
                )
            )
        )
        
        # Генерируем структуру призов
        prize_table = distribute_prizes(prize_pool, total_participants, verbose=False)
        
        # Сохраняем в БД
        for position, amount in prize_table:
            config = TournamentPrizeConfig(
                tournament_id=tournament_id,
                position_from=position,
                position_to=position,
                reward_type_id=reward_type_id,
                reward_amount=Decimal(str(amount))
            )
            self.db.add(config)
        
        await self.db.commit()
        logger.info(f"✅ Saved {len(prize_table)} prize configs")
        return len(prize_table)
    
    async def calculate_avg_prize_for_tie(
        self,
        tournament_id: int,
        reward_type_id: int,
        position_from: int,
        position_to: int
    ) -> Decimal:
        """
        Вычисляет усреднённый приз для группы с одинаковым скором.
        Например: места 4 и 5 делят (приз_за_4 + приз_за_5) / 2
        """
        result = await self.db.execute(
            select(TournamentPrizeConfig.reward_amount).where(
                and_(
                    TournamentPrizeConfig.tournament_id == tournament_id,
                    TournamentPrizeConfig.reward_type_id == reward_type_id,
                    TournamentPrizeConfig.position_from >= position_from,
                    TournamentPrizeConfig.position_from <= position_to
                )
            )
        )
        amounts = result.scalars().all()
        
        if not amounts:
            logger.warning(
                f"⚠️ No prizes found for tournament {tournament_id}, "
                f"reward_type {reward_type_id}, positions {position_from}-{position_to}"
            )
            return Decimal('0')
        
        total = sum(amounts)
        count = position_to - position_from + 1
        avg = total / count if count > 0 else Decimal('0')
        
        logger.debug(
            f"Positions {position_from}-{position_to}: "
            f"total={total}, count={count}, avg={avg}"
        )
        
        return avg