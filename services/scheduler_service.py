import asyncio
import logging
from datetime import datetime, timedelta 
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from services.price_monitor_service import PriceMonitorService
from services.card_render_service import card_render_service
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
                func=self._monitor_prices_job,
                trigger=IntervalTrigger(minutes=30),
                id='price_monitor',
                name='Price Monitor Job',
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
            await self._monitor_prices_job()
            
            logger.info("🚀 Running initial card rendering...")
            await self._render_cards_job()

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

    async def _monitor_prices_job(self):
        """Job function for price monitoring"""
        job_start = datetime.now()
        logger.info(f"🚀 Starting scheduled price monitoring job at {job_start.strftime('%H:%M:%S')}")

        try:
            async with self.price_monitor:
                await self.price_monitor.monitor_and_update_prices()

            duration = (datetime.now() - job_start).total_seconds()
            logger.info(f"✅ Price monitoring job completed in {duration:.2f} seconds")

        except Exception as e:
            logger.error(f"❌ Price monitoring job failed: {e}")
    
    async def _render_cards_job(self):  # <-- ДОБАВЬ
        """Job function for card rendering"""
        job_start = datetime.now()
        logger.info(f"🎨 Starting scheduled card rendering job at {job_start.strftime('%H:%M:%S')}")

        try:
            result = await card_render_service.render_all_active_cards()
            
            duration = (datetime.now() - job_start).total_seconds()
            logger.info(
                f"✅ Card rendering job completed in {duration:.2f} seconds. "
                f"Success: {result['success']}, Failed: {result['failed']}"
            )

        except Exception as e:
            logger.error(f"❌ Card rendering job failed: {e}", exc_info=True)

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

    async def run_price_monitor_now(self):
        """Manually trigger price monitoring"""
        logger.info("🔄 Manually triggering price monitoring...")
        await self._monitor_prices_job()
    
    async def run_card_render_now(self):  # <-- ДОБАВЬ
        """Manually trigger card rendering"""
        logger.info("🔄 Manually triggering card rendering...")
        await self._render_cards_job()

# Singleton instance
scheduler_service = SchedulerService()