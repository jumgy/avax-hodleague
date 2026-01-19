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
    
    def calculate_dynamic_prize_pool(self, base_prize_pool: float, total_participants: int) -> float:
        """
        Рассчитывает финальный prize pool с учётом количества участников.
        
        Логика:
        - До 250 участников: базовый prize_pool
        - 251-500: за каждого добавляем (base/250) × 0.75
        - 501-750: за каждого добавляем (base/250) × 0.5
        - 751-2000: за каждого добавляем (base/250) × 0.25
        - Больше 2000: ничего не добавляем
        """
        if total_participants <= 250:
            return base_prize_pool
        
        base_per_participant = base_prize_pool / 250
        additional_pool = 0.0
        
        # 251-500 участников: ×0.75
        if total_participants > 250:
            tier1_count = min(total_participants - 250, 250)  # max 250 участников в этом диапазоне
            additional_pool += tier1_count * base_per_participant * 0.75
            logger.debug(f"  Tier 1 (251-500): {tier1_count} participants × {base_per_participant * 0.75:.2f} = {tier1_count * base_per_participant * 0.75:.2f}")
        
        # 501-750 участников: ×0.5
        if total_participants > 500:
            tier2_count = min(total_participants - 500, 250)
            additional_pool += tier2_count * base_per_participant * 0.5
            logger.debug(f"  Tier 2 (501-750): {tier2_count} participants × {base_per_participant * 0.5:.2f} = {tier2_count * base_per_participant * 0.5:.2f}")
        
        # 751-2000 участников: ×0.25
        if total_participants > 750:
            tier3_count = min(total_participants - 750, 1250)
            additional_pool += tier3_count * base_per_participant * 0.25
            logger.debug(f"  Tier 3 (751-2000): {tier3_count} participants × {base_per_participant * 0.25:.2f} = {tier3_count * base_per_participant * 0.25:.2f}")
        
        # Больше 2000: ничего не добавляем
        
        final_pool = base_prize_pool + additional_pool
        logger.info(
            f"💰 Prize pool calculation: base={base_prize_pool}, "
            f"participants={total_participants}, additional={additional_pool:.2f}, "
            f"final={final_pool:.2f}"
        )
        
        return final_pool

    async def generate_and_save_prize_structure(
        self, 
        tournament_id: int, 
        reward_type_id: int, 
        base_prize_pool: float,  # ПЕРЕИМЕНОВАЛ: теперь это базовый prize pool
        total_participants: int
    ) -> int:
        """
        Генерирует структуру призов и сохраняет в TournamentPrizeConfig.
        Prize pool динамически увеличивается в зависимости от количества участников.
        
        Returns:
            Количество созданных записей
        """
        # Рассчитываем финальный prize pool
        final_prize_pool = self.calculate_dynamic_prize_pool(base_prize_pool, total_participants)
        
        logger.info(
            f"📊 Generating prize structure for tournament {tournament_id}, "
            f"reward_type {reward_type_id}, base_pool: {base_prize_pool}, "
            f"final_pool: {final_prize_pool:.2f}, participants: {total_participants}"
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
        
        # Генерируем структуру призов с финальным pool
        prize_table = distribute_prizes(final_prize_pool, total_participants, verbose=False)
        
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