# services/scheduler_service.py

import asyncio
import logging
from datetime import datetime, timezone, timedelta 
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, and_

from services.price_monitor_service import PriceMonitorService
from services.card_render_service import card_render_service
from services.tournament_service import tournament_service
from services.score_service import ScoreService
from models.tournament_models import Tournament, TournamentStatus
from models.database import AsyncSessionLocal
from models.user_pack_models import PackSource
from services.lock_service import JobLockService
from services.user_pack_grant_service import user_pack_grant_service
from config import Config

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.price_monitor = PriceMonitorService()
        self._started = False

    async def start(self):
        """Start the scheduler"""
        if self._started:
            logger.warning("Scheduler is already running")
            return
        
        try:
            logger.info("🕒 Starting scheduler...")
            
            # Job 1: Price & Score - каждые 5 минут, НЕ в :00 и :30
            self.scheduler.add_job(
                func=self._price_and_score_job,
                trigger=CronTrigger(minute='3,8,13,18,23,28,33,38,43,48,53,58'),
                id='price_and_score',
                name='Price Update & Score Calculation',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300
            )
            
            # Job 2: Card rendering
            self.scheduler.add_job(
                func=self._render_cards_job,
                trigger=CronTrigger(hour=3, minute=0),
                id='card_render',
                name='Card Render Job',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=600
            )
            
            # Job 3: Tournament Lifecycle (ОБЪЕДИНЁННЫЙ)
            self.scheduler.add_job(
                func=self._check_tournaments_lifecycle,
                trigger=CronTrigger(minute='0,30', second=30),  # :00:30 и :30:30
                id='tournament_lifecycle',
                name='Tournament Lifecycle Manager',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60
            )
            
            self.scheduler.start()
            self._started = True

            # Show schedule
            jobs = self.scheduler.get_jobs()
            logger.info(f"📅 Scheduled {len(jobs)} jobs:")
            for job in jobs:
                next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'N/A'
                logger.info(f"  - {job.name}: next run at {next_run}")

            # Run initial jobs
            logger.info("🚀 Running initial price monitoring...")
            await self._price_and_score_job()
            
            logger.info("🚀 Running initial card rendering...")
            await self._render_cards_job()
            
            logger.info("🚀 Running initial tournament checks...")
            await self._check_tournaments_lifecycle()

        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

    async def stop(self):
        """Stop the scheduler"""
        if not self._started:
            logger.warning("Scheduler is not running")
            return

        try:
            logger.info("🛑 Stopping scheduler...")
            self.scheduler.shutdown()
            self._started = False
            logger.info("✅ Scheduler stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
            raise

    async def _price_and_score_job(self):
        """Price update & score calculation с блокировкой"""
        async with AsyncSessionLocal() as db:
            async with JobLockService(db, "price_and_score", 300) as lock:
                if not lock.locked:
                    logger.warning("🚫 Price & score job already running, skipping")
                    return
                
                # ВСЯ РАБОТА ВНУТРИ БЛОКИРОВКИ! ✅
                try:
                    job_start = datetime.now()  # Переместил сюда
                    logger.info(f"🔄 Starting price update & score calculation at {job_start.strftime('%H:%M:%S')}")
                    
                    # ===== STEP 1: Update Prices =====
                    price_start = datetime.now()
                    logger.info("💰 [1/4] Updating token prices...")
                    async with self.price_monitor:
                        await self.price_monitor.monitor_and_update_prices()
                    price_duration = (datetime.now() - price_start).total_seconds()
                    logger.info(f"✅ [1/4] Prices updated in {price_duration:.2f}s")
                    
                    # ===== STEP 2: Calculate Scores =====
                    score_start = datetime.now()
                    logger.info("📊 [2/4] Calculating scores...")
                    async with AsyncSessionLocal() as score_db:
                        score_service = ScoreService(score_db)
                        
                        # Check for ONGOING tournament
                        result = await score_db.execute(
                            select(Tournament).where(
                                Tournament.status == TournamentStatus.ONGOING
                            )
                        )
                        tournament = result.scalar_one_or_none()
                        
                        # Calculate scores
                        if tournament:
                            logger.info(f"   ✅ Found ONGOING tournament #{tournament.tournament_number} (id={tournament.id})")
                            scores_count = await score_service.calculate_and_store_scores(tournament.id)
                            logger.info(f"   ✅ Calculated {scores_count} token scores for tournament #{tournament.tournament_number}")
                        else:
                            logger.info("   ℹ️  No active tournament - writing zero scores")
                            scores_count = await score_service.calculate_and_store_zero_scores()
                            logger.info(f"   ✅ Wrote zero scores for {scores_count} tokens")
                    
                    score_duration = (datetime.now() - score_start).total_seconds()
                    logger.info(f"✅ [2/4] Scores calculated in {score_duration:.2f}s")
                    
                    # ===== STEP 3: Update Leaderboard =====
                    leaderboard_start = datetime.now()
                    if tournament:
                        logger.info(f"🏆 [3/4] Updating leaderboard for tournament #{tournament.tournament_number}...")
                        async with AsyncSessionLocal() as leaderboard_db:
                            try:
                                participants_count = await tournament_service.calculate_results(tournament.id, leaderboard_db)
                                leaderboard_duration = (datetime.now() - leaderboard_start).total_seconds()
                                logger.info(
                                    f"✅ [3/4] Leaderboard updated: {participants_count} participants in {leaderboard_duration:.2f}s"
                                )
                            except Exception as e:
                                logger.error(f"❌ [3/4] Failed to update leaderboard: {e}", exc_info=True)
                    else:
                        logger.info("ℹ️  [3/4] No ongoing tournament - skipping leaderboard update")
                    
                    # ===== STEP 4: Summary =====
                    total_duration = (datetime.now() - job_start).total_seconds()
                    logger.info(
                        f"✅ [4/4] Complete job finished in {total_duration:.2f}s "
                        f"(prices: {price_duration:.2f}s, scores: {score_duration:.2f}s)"
                    )
                except Exception as e:
                    logger.error(f"❌ Price update & score calculation job failed: {e}", exc_info=True)

    async def _render_cards_job(self):
        """Job function for card rendering"""
        job_start = datetime.now()
        logger.info(f"🎨 Starting card rendering at {job_start.strftime('%H:%M:%S')}")
        
        try:
            result = await card_render_service.render_all_active_cards()
            duration = (datetime.now() - job_start).total_seconds()
            logger.info(
                f"✅ Card rendering completed in {duration:.2f}s. "
                f"Success: {result['success']}, Failed: {result['failed']}"
            )
        except Exception as e:
            logger.error(f"❌ Card rendering job failed: {e}", exc_info=True)

    async def _check_tournaments_lifecycle(self):
        """Обрабатывает весь lifecycle турниров с блокировкой"""
        async with AsyncSessionLocal() as db:
            async with JobLockService(db, "tournament_lifecycle", 180) as lock:
                if not lock.locked:
                    logger.warning("🚫 Tournament lifecycle job already running, skipping")
                    return
                
                try:
                    # Вызываем оба метода последовательно
                    await self._check_tournaments_to_start()
                    await self._check_tournaments_to_finish()
                except Exception as e:
                    logger.error(f"❌ Tournament lifecycle failed: {e}", exc_info=True)


    async def _check_tournaments_to_start(self):
        """
        Check tournaments lifecycle:
        1. FEATURED -> REGISTRATION (when start_date arrives)
        2. REGISTRATION -> ONGOING (when gameplay_start_date arrives)
        """
        try:
            now = datetime.now(timezone.utc)
            
            # ===== STEP 1: FEATURED -> REGISTRATION =====
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Tournament).where(
                        and_(
                            Tournament.status == TournamentStatus.FEATURED,
                            Tournament.start_date <= now,
                            Tournament.is_active == True
                        )
                    )
                )
                featured_tournaments = result.scalars().all()
            
            if featured_tournaments:
                logger.info(f"🆕 Found {len(featured_tournaments)} FEATURED tournament(s) ready for registration")
                
                for tournament in featured_tournaments:
                    try:
                        logger.info(
                            f"📝 Opening registration for tournament #{tournament.tournament_number} "
                            f"(scheduled: {tournament.start_date.strftime('%Y-%m-%d %H:%M:%S')}, "
                            f"now: {now.strftime('%Y-%m-%d %H:%M:%S')})"
                        )
                        
                        async with AsyncSessionLocal() as db:
                            await tournament_service.transition_featured_to_registration(tournament.id, db)
                        
                        logger.info(f"✅ Tournament #{tournament.tournament_number} opened for registration")
                    
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to open registration for tournament #{tournament.tournament_number}: {e}",
                            exc_info=True
                        )
            
            # ===== STEP 2: REGISTRATION -> ONGOING =====
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Tournament).where(
                        and_(
                            Tournament.status == TournamentStatus.REGISTRATION,
                            Tournament.gameplay_start_date <= now,
                            Tournament.is_active == True
                        )
                    )
                )
                registration_tournaments = result.scalars().all()
            
            if not registration_tournaments:
                return
            
            logger.info(f"🏁 Found {len(registration_tournaments)} REGISTRATION tournament(s) ready to start")
            
            for tournament in registration_tournaments:
                try:
                    logger.info(
                        f"▶️  Starting tournament #{tournament.tournament_number} "
                        f"(scheduled: {tournament.gameplay_start_date.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"now: {now.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    
                    async with AsyncSessionLocal() as db:
                        await tournament_service.start_tournament(tournament.id, db)
                    
                    logger.info(f"✅ Tournament #{tournament.tournament_number} started successfully")
                
                except Exception as e:
                    logger.error(
                        f"❌ Failed to start tournament #{tournament.tournament_number}: {e}",
                        exc_info=True
                    )
        
        except Exception as e:
            logger.error(f"❌ Tournament start checker failed: {e}", exc_info=True)


    async def _check_tournaments_to_finish(self):
        """Финализация турнира + мягкое удаление expired карт + выдача паков"""
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                
                # 1. Найти турниры для финализации
                result = await db.execute(
                    select(Tournament).where(
                        and_(
                            Tournament.status == TournamentStatus.ONGOING,
                            Tournament.end_date <= now
                        )
                    )
                )
                tournaments = result.scalars().all()
                
                if not tournaments:
                    return
                
                logger.info(f"🏆 Found {len(tournaments)} tournament(s) to finish")
                
                # 2. Финализируем турниры
                for tournament in tournaments:
                    try:
                        async with AsyncSessionLocal() as t_db:
                            await tournament_service.finish_tournament(tournament.id, t_db)
                        logger.info(f"✅ Tournament #{tournament.tournament_number} finished")
                    except Exception as e:
                        logger.error(f"❌ Failed to finish tournament: {e}", exc_info=True)
                
                # 3. 🗑️ МЯГКОЕ УДАЛЕНИЕ expired карт
                async with AsyncSessionLocal() as cleanup_db:
                    from sqlalchemy import update
                    from models.user_card_models import UserCard
                    
                    result = await cleanup_db.execute(
                        update(UserCard)
                        .where(UserCard.expires_at <= now)
                        .values(
                            is_active=False,
                            status="expired"
                        )
                    )
                    await cleanup_db.commit()
                    logger.info(f"🗑️  Marked {result.rowcount} cards as expired")
                
                # 4. 🎁 Выдаём новые паки ВСЕМ юзерам
                async with AsyncSessionLocal() as pack_db:
                    from models.user_models import User
                    
                    all_users = await pack_db.execute(
                        select(User).where(User.is_active == True)
                    )
                    
                    for user in all_users.scalars():
                        try:
                            await user_pack_grant_service.grant_all_active_packs_to_user(
                                user_id=user.id,
                                source=PackSource.WEEKLY
                            )
                            logger.info(f"🎁 Granted weekly packs to user {user.id}")
                        except Exception as e:
                            logger.error(f"❌ Failed to grant packs to user {user.id}: {e}")
                
        except Exception as e:
            logger.error(f"❌ Tournament finish checker failed: {e}", exc_info=True)

    async def run_price_and_score_now(self):
        """Manually trigger price update and score calculation"""
        logger.info("🔄 Manually triggering price update & score calculation...")
        await self._price_and_score_job()

    async def run_card_render_now(self):
        """Manually trigger card rendering"""
        logger.info("🔄 Manually triggering card rendering...")
        await self._render_cards_job()

    async def run_tournament_checks_now(self):
        """Manually trigger tournament checks"""
        logger.info("🔄 Manually triggering tournament checks...")
        await self._check_tournaments_to_start()
        await self._check_tournaments_to_finish()

    def get_status(self):
        """Get scheduler status"""
        if not self._started:
            return {"status": "stopped", "jobs": []}

        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

        return {
            "status": "running",
            "jobs": jobs_info
        }


scheduler_service = SchedulerService()
