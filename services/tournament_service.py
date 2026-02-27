# services/tournament_service.py

from sqlalchemy import select, and_, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from decimal import Decimal
import logging

from models.tournament_models import Tournament, TournamentStatus
from models.tournament_deck_models import TournamentDeck, TournamentResult, TournamentPrizeConfig
from models.reward_models import UserReward, ClaimStatus
from models.rarity_models import Rarity
from models.token_models import Token, TokenPrice
from models.card_models import Card

from .card_render_service import card_render_service
from .prize_config_service import PrizeConfigService

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

    async def transition_featured_to_registration(self, tournament_id: int, db: AsyncSession):
        """
        Переводит турнир из FEATURED в REGISTRATION
        Вызывается автоматически scheduler'ом при наступлении start_date
        
        Args:
            tournament_id: ID турнира
            db: Database session
            
        Raises:
            ValueError: если турнир не найден или не в статусе FEATURED
        """
        try:
            # Получаем турнир
            result = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = result.scalar_one_or_none()
            
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            # Проверка текущего статуса
            if tournament.status != TournamentStatus.FEATURED:
                raise ValueError(
                    f"Tournament {tournament_id} is in status '{tournament.status}', "
                    f"expected 'featured'"
                )
            
            # Проверка времени (опционально, для безопасности)
            now = datetime.now(timezone.utc)
            if tournament.start_date > now:
                raise ValueError(
                    f"Tournament {tournament_id} start_date "
                    f"({tournament.start_date}) has not arrived yet"
                )
            
            # Переводим в REGISTRATION
            tournament.status = TournamentStatus.REGISTRATION
            tournament.updated_at = datetime.now(timezone.utc)
            
            await db.commit()
            await db.refresh(tournament)
            
            logger.info(
                f"✅ Tournament #{tournament.tournament_number} (id={tournament_id}) "
                f"transitioned from FEATURED to REGISTRATION"
            )
            
            return tournament
            
        except Exception as e:
            await db.rollback()
            logger.error(
                f"❌ Error transitioning tournament {tournament_id} to registration: {e}"
            )
            raise


    async def recalculate_token_weights(self, tournament_id: int, db: AsyncSession) -> int:
        """
        Recalculate and update token weights based on tournament performance.
        Preserves weight distribution structure, but reassigns based on common card scores.
        
        Logic:
        1. Get current weight distribution (e.g., 3x weight-10, 3x weight-9, etc.)
        2. For each active token with active common card:
        - Get token's final score from token_scores at end_date
        - Get market cap for tiebreaking
        3. Sort tokens by: score DESC, then market_cap DESC
        4. Reassign weights preserving original distribution
        
        Returns: number of tokens updated
        """
        try:
            logger.info(f"🔄 Starting token weight recalculation for tournament {tournament_id}")
            
            # ========== STEP 1: Get current weight distribution ==========
            logger.info("Step 1: Getting current weight distribution...")
            
            weight_distribution_query = text("""
                SELECT weight, COUNT(*) as count
                FROM tokens
                WHERE is_active = true
                GROUP BY weight
                ORDER BY weight DESC
            """)
            
            weight_dist_result = await db.execute(weight_distribution_query)
            weight_distribution = []
            
            for row in weight_dist_result:
                weight = row[0]
                count = row[1]
                weight_distribution.extend([weight] * count)
                logger.info(f"  {count}x tokens with weight {weight}")
            
            if not weight_distribution:
                logger.warning("⚠️ No active tokens found, skipping weight recalculation")
                return 0
            
            logger.info(f"✅ Total weight slots: {len(weight_distribution)}")
            
            # ========== STEP 2: Get tournament end_date ==========
            logger.info("Step 2: Getting tournament end_date...")
            
            tournament_result = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = tournament_result.scalar_one_or_none()
            
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            end_date = tournament.end_date
            logger.info(f"✅ Tournament end_date: {end_date}")
            
            # ========== STEP 3: Get common rarity ID ==========
            logger.info("Step 3: Getting common rarity ID...")
            
            rarity_result = await db.execute(
                select(Rarity).where(Rarity.name == 'common')
            )
            common_rarity = rarity_result.scalar_one_or_none()
            
            if not common_rarity:
                raise ValueError("Common rarity not found in database")
            
            common_rarity_id = common_rarity.id
            logger.info(f"✅ Common rarity_id: {common_rarity_id}")
            
            # ========== STEP 4: Collect token scores DIRECTLY from token_scores ==========
            logger.info("Step 4: Collecting token performance data...")
            
            # Get all active tokens
            tokens_result = await db.execute(
                select(Token).where(Token.is_active == True)
            )
            active_tokens = tokens_result.scalars().all()
            logger.info(f"  Found {len(active_tokens)} active tokens")
            
            token_performance = []
            
            for token in active_tokens:
                logger.info(f"  Processing token: {token.symbol} (id={token.id})")
                
                # Get active common card for this token (most recent if multiple)
                card_result = await db.execute(
                    select(Card)
                    .where(
                        and_(
                            Card.token_id == token.id,
                            Card.rarity_id == common_rarity_id,
                            Card.is_active == True
                        )
                    )
                    .order_by(Card.created_at.desc())
                    .limit(1)
                )
                common_card = card_result.scalar_one_or_none()
                
                if not common_card:
                    logger.warning(f"    ⚠️ No active common card found for {token.symbol}, skipping")
                    continue
                
                logger.info(f"    Common card found: card_id={common_card.id}")
                
                # Get token's final score from token_scores (last before end_date)
                # This score already includes rarity bonus applied
                score_query = text("""
                    SELECT 
                        ts.calculated_score * r.score_bonus as final_score
                    FROM token_scores ts
                    JOIN tokens t ON t.id = ts.token_id
                    JOIN cards c ON c.token_id = t.id
                    JOIN rarities r ON r.id = c.rarity_id
                    WHERE ts.token_id = :token_id
                    AND ts.tournament_id = :tournament_id
                    AND ts.calculated_at <= :end_date
                    AND c.id = :card_id
                    ORDER BY ts.calculated_at DESC
                    LIMIT 1
                """)
                
                score_result = await db.execute(
                    score_query,
                    {
                        "token_id": token.id,
                        "tournament_id": tournament_id,
                        "end_date": end_date,
                        "card_id": common_card.id
                    }
                )
                score_row = score_result.first()
                
                if not score_row or score_row[0] is None:
                    logger.warning(f"    ⚠️ No tournament score found for {token.symbol}, skipping")
                    continue
                
                card_score = float(score_row[0])
                logger.info(f"    ✅ Card score: {card_score}")
                
                # Get market cap (last value before end_date)
                market_cap_query = text("""
                    SELECT market_cap
                    FROM token_prices
                    WHERE token_id = :token_id
                    AND timestamp <= :end_date
                    AND market_cap IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                
                mc_result = await db.execute(
                    market_cap_query,
                    {"token_id": token.id, "end_date": end_date}
                )
                mc_row = mc_result.first()
                
                market_cap = float(mc_row[0]) if mc_row and mc_row[0] else 0
                logger.info(f"    Market cap: ${market_cap:,.0f}")
                
                token_performance.append({
                    'token_id': token.id,
                    'symbol': token.symbol,
                    'score': card_score,
                    'market_cap': market_cap,
                    'old_weight': token.weight
                })
            
            if not token_performance:
                logger.warning("⚠️ No tokens with tournament scores found, skipping weight update")
                return 0
            
            logger.info(f"✅ Collected data for {len(token_performance)} tokens")
            
            # ========== STEP 5: Sort tokens by performance ==========
            logger.info("Step 5: Sorting tokens by performance...")
            
            # Sort by: score DESC, then market_cap DESC
            token_performance.sort(key=lambda x: (-x['score'], -x['market_cap']))
            
            logger.info("  Top 5 performers:")
            for i, tp in enumerate(token_performance[:5], 1):
                logger.info(f"    {i}. {tp['symbol']}: score={tp['score']:.2f}, mc=${tp['market_cap']/1e9:.2f}B")
            
            # ========== STEP 6: Assign new weights ==========
            logger.info("Step 6: Assigning new weights...")
            
            # Ensure we have enough weight slots
            num_tokens_to_update = min(len(token_performance), len(weight_distribution))
            
            if len(token_performance) < len(weight_distribution):
                logger.warning(
                    f"⚠️ Only {len(token_performance)} tokens have scores, "
                    f"but {len(weight_distribution)} weight slots exist"
                )
            
            updates_count = 0
            
            for i in range(num_tokens_to_update):
                token_data = token_performance[i]
                new_weight = weight_distribution[i]
                old_weight = token_data['old_weight']
                
                if new_weight != old_weight:
                    logger.info(
                        f"  {token_data['symbol']}: weight {old_weight} -> {new_weight} "
                        f"(score={token_data['score']:.2f})"
                    )
                    
                    # Update token weight
                    update_query = text("""
                        UPDATE tokens
                        SET weight = :new_weight,
                            updated_at = :updated_at
                        WHERE id = :token_id
                    """)
                    
                    await db.execute(
                        update_query,
                        {
                            "new_weight": new_weight,
                            "updated_at": datetime.now(timezone.utc),
                            "token_id": token_data['token_id']
                        }
                    )
                    
                    updates_count += 1
                else:
                    logger.info(f"  {token_data['symbol']}: weight unchanged ({old_weight})")
            
            await db.commit()
            
            logger.info(f"✅ Token weights recalculated: {updates_count} tokens updated")
            return updates_count
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error recalculating token weights: {e}", exc_info=True)
            raise

    async def finish_tournament(self, tournament_id: int, db: AsyncSession) -> Tournament:
        """
        Finish tournament: ongoing -> finished
        ALL operations happen in a SINGLE transaction - either everything succeeds or everything rolls back.
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
            
            logger.info(f"🏁 Finishing tournament #{tournament.tournament_number}...")
            
            # Шаг 1: Меняем статус
            logger.info(f"🏆 [1/6] Changing status to FINISHED...")
            tournament.status = TournamentStatus.FINISHED
            tournament.updated_at = datetime.now(timezone.utc)
            
            # Шаг 2: Рассчитываем результаты
            logger.info(f"📊 [2/6] Calculating final results...")
            participants_count = await self.calculate_results(tournament_id, db)
            logger.info(f"✅ Results calculated for {participants_count} participants")
            
            # Шаг 3: Распределяем награды (создаём UserReward)
            logger.info(f"💰 [3/6] Distributing rewards...")
            rewards_count = await self.distribute_rewards(tournament_id, db)
            logger.info(f"✅ Distributed {rewards_count} rewards")
            
            # Шаг 4: Пересчитываем веса токенов
            logger.info(f"⚖️  [4/6] Recalculating token weights...")
            weights_updated = await self.recalculate_token_weights(tournament_id, db)
            logger.info(f"✅ Updated {weights_updated} token weights")
            
            # Шаг 5: Коммитим 
            logger.info(f"💾 [5/6] Committing all changes...")
            await db.commit()
            await db.refresh(tournament)
            logger.info(f"✅ Transaction committed successfully")
            
            # Шаг 6: Рендерим карточки 
            logger.info(f"🎨 [6/6] Rendering cards with updated weights...")
            try:
                render_result = await card_render_service.render_all_active_cards()
                logger.info(
                    f"✅ Cards rendered: {render_result.get('success', 0)} success, "
                    f"{render_result.get('failed', 0)} failed"
                )
            except Exception as render_error:
                # Don't fail the whole tournament finalization if rendering fails
                logger.error(f"⚠️ Card rendering failed (non-critical): {render_error}", exc_info=True)
            
            logger.info(f"✅✅✅ Tournament #{tournament.tournament_number} finished successfully!")
            return tournament
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error finishing tournament {tournament_id}: {e}", exc_info=True)
            logger.error(f"   Tournament status, rewards, and weights have been rolled back")
            raise


    async def calculate_results(self, tournament_id: int, db: AsyncSession) -> int:
        """
        Calculate final tournament results with tie handling and prize distribution.
        Uses token scores closest to (but not after) tournament end_date.
        """
        try:
            logger.info(f"🔍 Starting calculate_results for tournament {tournament_id}")
            
            # Шаг 1: Получаем турнир и его end_date
            logger.info(f"Step 1: Fetching tournament...")
            tournament_result = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = tournament_result.scalar_one_or_none()
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            end_date = tournament.end_date
            logger.info(f"  Tournament #{tournament.tournament_number} ended at: {end_date}")
            
            # Шаг 2: Получаем деки
            logger.info(f"Step 2: Fetching valid decks...")
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
            total_participants = len(decks)
            
            deck_scores = []
            
            # Шаг 3: Считаем скоры для каждого дека
            for idx, deck in enumerate(decks, start=1):
                logger.info(f"Step 3.{idx}: Processing deck {deck.id} for user {deck.user_id}")
                deck_composition = deck.deck_composition
                logger.info(f"  Deck composition: {deck_composition}")
                
                total_score = 0.0
                card_scores_array = []
                
                for card_idx, card_entry in enumerate(deck_composition, start=1):
                    # Поддержка двух форматов
                    if isinstance(card_entry, dict):
                        card_id = card_entry.get('card_id')
                    elif isinstance(card_entry, int):
                        card_id = card_entry
                    else:
                        logger.error(f"  ❌ Unknown card_entry format: {type(card_entry)} = {card_entry}")
                        card_scores_array.append(0.0)
                        continue
                    
                    logger.info(f"  Processing card {card_idx}/{len(deck_composition)}: card_id={card_id}")
                    
                    try:
                        # Get score closest to end_date (but not after)
                        score_query = text("""
                            WITH ranked_scores AS (
                                SELECT 
                                    ts.calculated_score,
                                    ts.calculated_at,
                                    r.score_bonus as rarity_score_bonus,
                                    ROW_NUMBER() OVER (
                                        ORDER BY ts.calculated_at DESC
                                    ) as rn
                                FROM token_scores ts
                                JOIN user_cards uc ON uc.id = :user_card_id
                                JOIN cards c ON c.id = uc.card_id
                                JOIN rarities r ON r.id = c.rarity_id
                                WHERE ts.token_id = c.token_id
                                AND ts.tournament_id = :tournament_id
                                AND ts.calculated_at <= :end_date
                            )
                            SELECT 
                                calculated_score * rarity_score_bonus as final_score,
                                calculated_at
                            FROM ranked_scores
                            WHERE rn = 1
                        """)
                        
                        score_result = await db.execute(
                            score_query, 
                            {
                                "user_card_id": card_id,
                                "tournament_id": tournament_id,
                                "end_date": end_date
                            }
                        )
                        score_row = score_result.first()
                        
                        if score_row:
                            card_score = float(score_row[0] or 0)
                            score_timestamp = score_row[1]
                            logger.info(f"    ✅ Card {card_id} score: {card_score} (at {score_timestamp})")
                            total_score += card_score
                            card_scores_array.append(card_score)
                        else:
                            logger.warning(f"    ⚠️ No score found for card {card_id} before {end_date}")
                            card_scores_array.append(0.0)
                            
                    except Exception as card_error:
                        logger.error(f"    ❌ Error getting score for card {card_id}: {card_error}", exc_info=True)
                        card_scores_array.append(0.0)
                        raise
                
                logger.info(f"  Total score for deck {deck.id}: {total_score}")
                logger.info(f"  Card scores array: {card_scores_array}")
                
                deck_scores.append({
                    'deck_id': deck.id,
                    'user_id': deck.user_id,
                    'total_score': total_score,
                    'card_scores': card_scores_array
                })
            
            # Шаг 4: Сортируем по скору
            logger.info(f"Step 4: Sorting {len(deck_scores)} decks by score...")
            deck_scores.sort(key=lambda x: x['total_score'], reverse=True)
            logger.info(f"✅ Sorting complete. Top score: {deck_scores[0]['total_score'] if deck_scores else 0}")
            
            # Шаг 5: Генерируем структуры призов для каждого reward_type
            logger.info(f"Step 5: Generating prize structures...")
            prize_config_service = PrizeConfigService(db)
            
            # Получаем reward_types и prize_pools из турнира
            reward_types = tournament.reward_types or []
            prize_pools = tournament.prize_pools or {}
            
            if not reward_types:
                logger.warning(f"⚠️ No reward_types configured for tournament {tournament_id}")
            else:
                for reward_type_id in reward_types:
                    prize_pool = float(prize_pools.get(str(reward_type_id), 0))
                    if prize_pool > 0:
                        logger.info(
                            f"  Generating prize structure for reward_type {reward_type_id}, "
                            f"pool: {prize_pool}"
                        )
                        await prize_config_service.generate_and_save_prize_structure(
                            tournament_id=tournament_id,
                            reward_type_id=reward_type_id,
                            base_prize_pool=prize_pool,
                            total_participants=total_participants
                        )
                    else:
                        logger.warning(
                            f"  ⚠️ No prize pool configured for reward_type {reward_type_id}"
                        )
            
            # Шаг 6: Обрабатываем ties и вычисляем призы
            logger.info(f"Step 6: Handling ties and calculating prizes...")
            
            results_with_prizes = []
            i = 0
            
            while i < len(deck_scores):
                current_score = deck_scores[i]['total_score']
                
                # Находим всех с таким же скором
                same_score_group = []
                j = i
                while j < len(deck_scores) and deck_scores[j]['total_score'] == current_score:
                    same_score_group.append(deck_scores[j])
                    j += 1
                
                # Определяем диапазон мест
                start_place = i + 1
                end_place = i + len(same_score_group)
                
                logger.info(
                    f"  Places {start_place}-{end_place}: "
                    f"{len(same_score_group)} player(s) with score {current_score}"
                )
                
                # Вычисляем призы для каждого reward_type
                prizes_dict = {}
                for reward_type_id in reward_types:
                    avg_prize = await prize_config_service.calculate_avg_prize_for_tie(
                        tournament_id=tournament_id,
                        reward_type_id=reward_type_id,
                        position_from=start_place,
                        position_to=end_place
                    )
                    prizes_dict[str(reward_type_id)] = str(avg_prize)
                
                if prizes_dict:
                    logger.info(f"    Prizes: {prizes_dict}")
                
                # Добавляем информацию о призе для каждого в группе
                for deck_info in same_score_group:
                    results_with_prizes.append({
                        **deck_info,
                        'position': start_place,  # показываем первую позицию в группе
                        'prizes': prizes_dict
                    })
                
                i = j
            
            # Шаг 7: Сохраняем результаты
            logger.info(f"Step 7: Saving results to database...")
            for result_info in results_with_prizes:
                logger.info(
                    f"  Position {result_info['position']}: "
                    f"deck_id={result_info['deck_id']}, "
                    f"score={result_info['total_score']}, "
                    f"prizes={result_info['prizes']}"
                )
                
                existing_result = await db.execute(
                    select(TournamentResult).where(
                        TournamentResult.tournament_deck_id == result_info['deck_id']
                    )
                )
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    logger.info(f"    Updating existing result...")
                    existing.final_position = result_info['position']
                    existing.final_score = result_info['total_score']
                    existing.card_scores = result_info['card_scores']
                    existing.prizes = result_info['prizes']
                    existing.calculated_at = datetime.now(timezone.utc)
                else:
                    logger.info(f"    Creating new result...")
                    tournament_result = TournamentResult(
                        tournament_id=tournament_id,
                        tournament_deck_id=result_info['deck_id'],
                        final_position=result_info['position'],
                        final_score=result_info['total_score'],
                        card_scores=result_info['card_scores'],
                        prizes=result_info['prizes'],
                        calculated_at=datetime.now(timezone.utc)
                    )
                    db.add(tournament_result)
            
            logger.info("Step 8: Committing results...")
            await db.commit()
            logger.info(f"✅ Results calculated for {len(results_with_prizes)} participants")
            
            return len(results_with_prizes)
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error calculating results: {e}", exc_info=True)
            raise

    async def distribute_rewards(self, tournament_id: int, db: AsyncSession) -> int:
        """
        Distribute rewards to tournament winners based on calculated results.
        Creates UserReward records from TournamentResult.prizes (which already accounts for ties).
        
        Should be called after:
        1. Tournament status changed to FINISHED
        2. calculate_results() has been executed
        """
        try:
            logger.info(f"💰 Starting reward distribution for tournament {tournament_id}")
            
            # Проверяем статус турнира
            tournament_query = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = tournament_query.scalar_one_or_none()
            
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            if tournament.status != TournamentStatus.FINISHED:
                logger.warning(
                    f"⚠️ Tournament {tournament_id} is not FINISHED (status: {tournament.status}). "
                    "Rewards should only be distributed for finished tournaments."
                )
                # Можно либо raise, либо просто вернуть 0
                # return 0
            
            # Получаем все результаты турнира
            results_query = await db.execute(
                select(TournamentResult)
                .where(TournamentResult.tournament_id == tournament_id)
                .order_by(TournamentResult.final_position)
            )
            results = results_query.scalars().all()
            
            if not results:
                logger.warning(f"⚠️ No results found for tournament {tournament_id}")
                return 0
            
            rewards_created = 0
            
            for result in results:
                # Получаем дек для user_id
                deck_query = await db.execute(
                    select(TournamentDeck).where(TournamentDeck.id == result.tournament_deck_id)
                )
                deck = deck_query.scalar_one_or_none()
                
                if not deck:
                    logger.error(f"❌ Deck {result.tournament_deck_id} not found for result {result.id}")
                    continue
                
                # Парсим prizes из JSON: {"1": "12250.50", "2": "45000"}
                prizes = result.prizes or {}
                
                if not prizes:
                    logger.info(f"ℹ️ No prizes for position {result.final_position} (user {deck.user_id})")
                    continue
                
                logger.info(
                    f"  Processing position {result.final_position} (user {deck.user_id}): "
                    f"prizes={prizes}"
                )
                
                # Создаём UserReward для каждого reward_type
                for reward_type_id_str, amount_str in prizes.items():
                    reward_type_id = int(reward_type_id_str)
                    amount = Decimal(amount_str)

                    if amount <= 0:
                        continue
                    
                    # Проверяем, не создали ли уже такую награду
                    existing_reward_query = await db.execute(
                        select(UserReward).where(
                            and_(
                                UserReward.user_id == deck.user_id,
                                UserReward.tournament_result_id == result.id,
                                UserReward.reward_type_id == reward_type_id
                            )
                        )
                    )
                    existing_reward = existing_reward_query.scalar_one_or_none()
                    
                    if existing_reward:
                        logger.info(
                            f"    ⏭️  Reward already exists for user {deck.user_id}, "
                            f"reward_type {reward_type_id}"
                        )
                        continue
                    
                    # Создаём новую награду
                    user_reward = UserReward(
                        user_id=deck.user_id,
                        reward_type_id=reward_type_id,
                        amount=amount,
                        tournament_result_id=result.id,
                        earned_at=datetime.now(timezone.utc),
                        claim_status=ClaimStatus.PENDING,
                        extra_data={
                            'tournament_id': tournament_id,
                            'tournament_number': tournament.tournament_number,
                            'final_position': result.final_position,
                            'final_score': str(result.final_score)
                        }
                    )
                    
                    db.add(user_reward)
                    rewards_created += 1
                    
                    logger.info(
                        f"    ✅ Created reward: user={deck.user_id}, "
                        f"reward_type={reward_type_id}, amount={amount}"
                    )
            
            await db.commit()
            logger.info(f"✅ Created {rewards_created} rewards for tournament {tournament_id}")
            
            return rewards_created
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error distributing rewards for tournament {tournament_id}: {e}", exc_info=True)
            raise

    async def claim_tournament_rewards(
        self, user_id: int, tournament_id: int, db: AsyncSession
    ) -> dict:
        """
        Claim all pending user rewards for a given tournament.
        Finds all UserReward with claim_status=pending linked to this user and tournament,
        sets them to claimed and returns count + ids.

        Returns:
            {"claimed_count": int, "reward_ids": list[int]}
        """
        try:
            # Находим все pending награды пользователя по этому турниру (через tournament_result)
            subq = (
                select(UserReward.id)
                .join(
                    TournamentResult,
                    UserReward.tournament_result_id == TournamentResult.id,
                )
                .where(
                    UserReward.user_id == user_id,
                    TournamentResult.tournament_id == tournament_id,
                    UserReward.claim_status == ClaimStatus.PENDING,
                )
            )
            result = await db.execute(subq)
            reward_ids = [row[0] for row in result.fetchall()]

            if not reward_ids:
                return {"claimed_count": 0, "reward_ids": []}

            now = datetime.now(timezone.utc)
            await db.execute(
                update(UserReward)
                .where(UserReward.id.in_(reward_ids))
                .values(
                    claim_status=ClaimStatus.CLAIMED,
                    claimed_at=now,
                )
            )
            await db.commit()
            logger.info(
                f"✅ User {user_id} claimed {len(reward_ids)} rewards for tournament {tournament_id}"
            )
            return {"claimed_count": len(reward_ids), "reward_ids": reward_ids}
        except Exception as e:
            await db.rollback()
            logger.error(
                f"❌ Error claiming rewards for user {user_id} tournament {tournament_id}: {e}",
                exc_info=True,
            )
            raise


tournament_service = TournamentService()
