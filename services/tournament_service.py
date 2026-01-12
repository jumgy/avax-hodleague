# services/tournament_service.py

from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import logging

from models.tournament_models import Tournament, TournamentStatus
from models.tournament_deck_models import TournamentDeck, TournamentResult, TournamentPrizeConfig
from models.reward_models import UserReward, ClaimStatus

logger = logging.getLogger(__name__)


class TournamentService:
    """Service for managing tournament lifecycle"""

    async def create_tournament_snapshot(self, tournament_id: int, db: AsyncSession) -> bool:
        """
        Create price snapshot for tournament start
        Saves current token prices to tournament_token_snapshots table
        """
        try:
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
            return True

        except Exception as e:
            logger.error(f"❌ Error creating tournament snapshot: {e}")
            await db.rollback()
            return False

    async def start_tournament(self, tournament_id: int, db: AsyncSession) -> Tournament:
        """
        Start tournament: registration -> ongoing
        Creates token price snapshot
        """
        try:
            result = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = result.scalar_one_or_none()
            
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            if tournament.status != TournamentStatus.REGISTRATION:
                raise ValueError(
                    f"Cannot start: status is '{tournament.status}', expected 'registration'"
                )
            
            logger.info(f"Creating token snapshot for tournament #{tournament.tournament_number}...")
            snapshot_success = await self.create_tournament_snapshot(tournament.id, db)
            
            if not snapshot_success:
                raise Exception("Failed to create tournament snapshot")
            
            tournament.status = TournamentStatus.ONGOING
            tournament.updated_at = datetime.now(timezone.utc)
            
            await db.commit()
            await db.refresh(tournament)
            
            logger.info(f"✅ Tournament #{tournament.tournament_number} started (id={tournament.id})")
            return tournament
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error starting tournament {tournament_id}: {e}")
            raise

    async def finish_tournament(self, tournament_id: int, db: AsyncSession) -> Tournament:
        """
        Finish tournament: ongoing -> finished
        Calculates final results and distributes rewards
        """
        try:
            result = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = result.scalar_one_or_none()
            
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            if tournament.status != TournamentStatus.ONGOING:
                raise ValueError(
                    f"Cannot finish: status is '{tournament.status}', expected 'ongoing'"
                )
            
            logger.info(f"Calculating results for tournament #{tournament.tournament_number}...")
            participants_count = await self.calculate_results(tournament_id, db)
            
            logger.info(f"Distributing rewards for tournament #{tournament.tournament_number}...")
            rewards_count = await self.distribute_rewards(tournament_id, db)
            
            tournament.status = TournamentStatus.FINISHED
            tournament.updated_at = datetime.now(timezone.utc)
            
            await db.commit()
            await db.refresh(tournament)
            
            logger.info(
                f"✅ Tournament #{tournament.tournament_number} finished "
                f"(participants: {participants_count}, rewards: {rewards_count})"
            )
            return tournament
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error finishing tournament {tournament_id}: {e}")
            raise

    async def calculate_results(self, tournament_id: int, db: AsyncSession) -> int:
        """
        Calculate final tournament results
        Reads calculated_score from active_cards_with_score view
        """
        try:
            logger.info(f"🔍 Starting calculate_results for tournament {tournament_id}")
            
            # Шаг 1: Получаем деки
            logger.info(f"Step 1: Fetching valid decks...")
            decks_result = await db.execute(
                select(TournamentDeck)
                .where(
                    and_(
                        TournamentDeck.tournament_id == tournament_id,
                        TournamentDeck.is_active == True,
                        TournamentDeck.is_valid == True
                    )
                )
            )
            decks = decks_result.scalars().all()
            
            if not decks:
                logger.warning(f"⚠️ No valid participants in tournament {tournament_id}")
                return 0
            
            logger.info(f"✅ Found {len(decks)} valid decks")
            
            deck_scores = []
            
            # Шаг 2: Считаем скоры для каждого дека
            for idx, deck in enumerate(decks, start=1):
                logger.info(f"Step 2.{idx}: Processing deck {deck.id} for user {deck.user_id}")
                
                deck_composition = deck.deck_composition
                logger.info(f"  Deck composition: {deck_composition}")
                logger.info(f"  Deck composition type: {type(deck_composition)}")
                
                total_score = 0.0
                
                for card_idx, card_entry in enumerate(deck_composition, start=1):
                    # Поддержка двух форматов:
                    # 1. [265, 266, 267] - просто массив card_id
                    # 2. [{"card_id": 265}, {"card_id": 266}] - массив объектов
                    
                    if isinstance(card_entry, dict):
                        card_id = card_entry.get('card_id')
                    elif isinstance(card_entry, int):
                        card_id = card_entry
                    else:
                        logger.error(f"  ❌ Unknown card_entry format: {type(card_entry)} = {card_entry}")
                        continue
                    
                    logger.info(f"  Processing card {card_idx}/{len(deck_composition)}: card_id={card_id}")
                    
                    try:
                        score_query = text("""
                            SELECT calculated_score 
                            FROM active_cards_with_score 
                            WHERE card_id = :card_id 
                            AND active_tournament_id = :tournament_id
                        """)
                        
                        score_result = await db.execute(
                            score_query, 
                            {"card_id": card_id, "tournament_id": tournament_id}
                        )
                        score_row = score_result.first()
                        
                        if score_row:
                            card_score = float(score_row[0] or 0)
                            logger.info(f"    ✅ Card {card_id} score: {card_score}")
                            total_score += card_score
                        else:
                            logger.warning(f"    ⚠️ No score found for card {card_id} in view")
                            
                    except Exception as card_error:
                        logger.error(f"    ❌ Error getting score for card {card_id}: {card_error}", exc_info=True)
                        raise
                
                logger.info(f"  Total score for deck {deck.id}: {total_score}")
                
                deck_scores.append({
                    'deck_id': deck.id,
                    'user_id': deck.user_id,
                    'total_score': total_score
                })
            
            # Шаг 3: Сортируем по скору
            logger.info(f"Step 3: Sorting {len(deck_scores)} decks by score...")
            deck_scores.sort(key=lambda x: x['total_score'], reverse=True)
            logger.info(f"✅ Sorting complete. Top score: {deck_scores[0]['total_score'] if deck_scores else 0}")
            
            # Шаг 4: Сохраняем результаты
            logger.info(f"Step 4: Saving results to database...")
            for position, deck_info in enumerate(deck_scores, start=1):
                logger.info(f"  Position {position}: deck_id={deck_info['deck_id']}, score={deck_info['total_score']}")
                
                existing_result = await db.execute(
                    select(TournamentResult).where(
                        TournamentResult.tournament_deck_id == deck_info['deck_id']
                    )
                )
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    logger.info(f"    Updating existing result...")
                    existing.final_position = position
                    existing.final_score = deck_info['total_score']
                    existing.calculated_at = datetime.now(timezone.utc)
                else:
                    logger.info(f"    Creating new result...")
                    tournament_result = TournamentResult(
                        tournament_id=tournament_id,
                        tournament_deck_id=deck_info['deck_id'],
                        final_position=position,
                        final_score=deck_info['total_score'],
                        calculated_at=datetime.now(timezone.utc)
                    )
                    db.add(tournament_result)
            
            logger.info("Step 5: Committing results...")
            await db.commit()
            logger.info(f"✅ Results calculated for {len(deck_scores)} participants")
            return len(deck_scores)
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error calculating results: {e}", exc_info=True)
            raise

    async def distribute_rewards(self, tournament_id: int, db: AsyncSession) -> int:
        """
        Distribute rewards to tournament winners
        Creates UserReward records based on TournamentPrizeConfig
        """
        try:
            results_query = await db.execute(
                select(TournamentResult)
                .where(TournamentResult.tournament_id == tournament_id)
                .order_by(TournamentResult.final_position)
            )
            results = results_query.scalars().all()
            
            if not results:
                logger.warning(f"⚠️ No results found for tournament {tournament_id}")
                return 0
            
            prize_configs_query = await db.execute(
                select(TournamentPrizeConfig)
                .where(TournamentPrizeConfig.tournament_id == tournament_id)
                .order_by(TournamentPrizeConfig.position_from)
            )
            prize_configs = prize_configs_query.scalars().all()
            
            if not prize_configs:
                logger.warning(f"⚠️ No prize configuration for tournament {tournament_id}")
                return 0
            
            rewards_created = 0
            
            for result in results:
                position = result.final_position
                
                matching_config = None
                for config in prize_configs:
                    if config.position_from <= position <= config.position_to:
                        matching_config = config
                        break
                
                if not matching_config:
                    continue
                
                deck_query = await db.execute(
                    select(TournamentDeck).where(TournamentDeck.id == result.tournament_deck_id)
                )
                deck = deck_query.scalar_one_or_none()
                
                if not deck:
                    logger.error(f"❌ Deck {result.tournament_deck_id} not found")
                    continue
                
                existing_reward_query = await db.execute(
                    select(UserReward).where(
                        and_(
                            UserReward.user_id == deck.user_id,
                            UserReward.tournament_result_id == result.id
                        )
                    )
                )
                existing_reward = existing_reward_query.scalar_one_or_none()
                
                if existing_reward:
                    continue
                
                tournament_query = await db.execute(
                    select(Tournament).where(Tournament.id == tournament_id)
                )
                tournament = tournament_query.scalar_one()
                
                user_reward = UserReward(
                    user_id=deck.user_id,
                    reward_type_id=matching_config.reward_type_id,
                    amount=matching_config.reward_amount,
                    tournament_result_id=result.id,
                    earned_at=datetime.now(timezone.utc),
                    claim_status=ClaimStatus.PENDING,
                    extra_data={
                        'tournament_id': tournament_id,
                        'tournament_number': tournament.tournament_number,
                        'final_position': position,
                        'final_score': str(result.final_score)
                    }
                )
                
                db.add(user_reward)
                rewards_created += 1
            
            await db.commit()
            logger.info(f"✅ Created {rewards_created} rewards for tournament {tournament_id}")
            return rewards_created
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error distributing rewards: {e}")
            raise


tournament_service = TournamentService()