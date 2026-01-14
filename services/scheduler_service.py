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
            
            # Job 1: Price monitoring (every 30 minutes)
            self.scheduler.add_job(
                func=self._price_and_score_job,
                trigger=IntervalTrigger(minutes=1),
                id='price_and_score',
                name='Price Update & Score Calculation',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300
            )

            # Job 2: Card rendering (every day at 3 AM)
            self.scheduler.add_job(
                func=self._render_cards_job,
                trigger=CronTrigger(hour=3, minute=0),
                id='card_render',
                name='Card Render Job',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=600
            )

            # Job 3: Check tournaments to start (every 1 minute)
            self.scheduler.add_job(
                func=self._check_tournaments_to_start,
                trigger=IntervalTrigger(minutes=1),
                id='tournament_start_checker',
                name='Tournament Start Checker',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60
            )

            # Job 4: Check tournaments to finish (every 1 minute)
            self.scheduler.add_job(
                func=self._check_tournaments_to_finish,
                trigger=IntervalTrigger(minutes=1),
                id='tournament_finish_checker',
                name='Tournament Finish Checker',
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
            await self._check_tournaments_to_start()
            await self._check_tournaments_to_finish()

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
        """
        Combined job: Price update → Score calculation (sequential)
        Runs every 5 minutes:
        1. Update token prices (wait for completion)
        2. Calculate scores based on new prices
        3. Refresh materialized view
        """
        job_start = datetime.now()
        logger.info(f"🔄 Starting price update & score calculation at {job_start.strftime('%H:%M:%S')}")
        
        try:
            # ===== STEP 1: Update Prices =====
            price_start = datetime.now()
            logger.info("💰 [1/3] Updating token prices...")
            
            async with self.price_monitor:
                await self.price_monitor.monitor_and_update_prices()
            
            price_duration = (datetime.now() - price_start).total_seconds()
            logger.info(f"✅ [1/3] Prices updated in {price_duration:.2f}s")
            
            # ===== STEP 2: Calculate Scores =====
            score_start = datetime.now()
            logger.info("📊 [2/3] Calculating scores...")
            
            async with AsyncSessionLocal() as db:
                score_service = ScoreService(db)
                
                # Check for ONGOING tournament
                result = await db.execute(
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
            logger.info(f"✅ [2/3] Scores calculated in {score_duration:.2f}s")
            
            # ===== STEP 3: Summary =====
            total_duration = (datetime.now() - job_start).total_seconds()
            logger.info(
                f"✅ [3/3] Price update & score calculation completed in {total_duration:.2f}s "
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


    async def _check_tournaments_to_start(self):
        """Check if any tournaments should be started"""
        try:
            # Сначала найдем какие турниры надо стартовать
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                
                result = await db.execute(
                    select(Tournament).where(
                        and_(
                            Tournament.status == TournamentStatus.REGISTRATION,
                            Tournament.gameplay_start_date <= now
                        )
                    )
                )
                tournaments = result.scalars().all()
            
            if not tournaments:
                return
            
            logger.info(f"🏁 Found {len(tournaments)} tournament(s) ready to start")
            
            # Каждый турнир обрабатываем в ОТДЕЛЬНОЙ сессии
            for tournament in tournaments:
                try:
                    logger.info(
                        f"▶️  Starting tournament #{tournament.tournament_number} "
                        f"(scheduled: {tournament.gameplay_start_date.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"now: {now.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    
                    # Создаем новую сессию для этого турнира
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
        """Check if any tournaments should be finished"""
        try:
            # Сначала найдем какие турниры надо финишировать
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                
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
            
            logger.info(f"🏆 Found {len(tournaments)} tournament(s) ready to finish")
            
            # Каждый турнир обрабатываем в ОТДЕЛЬНОЙ сессии
            for tournament in tournaments:
                try:
                    logger.info(
                        f"🏁 Finishing tournament #{tournament.tournament_number} "
                        f"(scheduled: {tournament.end_date.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"now: {now.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    
                    # Создаем новую сессию для этого турнира
                    async with AsyncSessionLocal() as db:
                        await tournament_service.finish_tournament(tournament.id, db)
                    
                    logger.info(f"✅ Tournament #{tournament.tournament_number} finished successfully")
                except Exception as e:
                    logger.error(
                        f"❌ Failed to finish tournament #{tournament.tournament_number}: {e}",
                        exc_info=True
                    )
                    
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