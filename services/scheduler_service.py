# services/scheduler_service.py - исправленная версия
import asyncio
import logging
from datetime import datetime, timedelta  # ДОБАВИЛИ timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from services.price_monitor_service import PriceMonitorService
from config import Config

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.price_monitor = PriceMonitorService()
        self._running = False
        
    async def start(self):
        """Start the scheduler"""
        if self._running:
            logger.warning("Scheduler is already running")
            return
            
        try:
            logger.info("🕒 Starting price monitoring scheduler...")
            
            # Добавляем задачу мониторинга цен каждые 30 минут
            self.scheduler.add_job(
                func=self._monitor_prices_job,
                trigger=IntervalTrigger(minutes=30),
                id='price_monitor',
                name='Price Monitor Job',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300
            )
            
            # ИСПРАВИЛИ: запуск через 30 секунд от текущего времени
            startup_time = datetime.now() + timedelta(seconds=30)
            self.scheduler.add_job(
                func=self._monitor_prices_job,
                trigger='date',
                run_date=startup_time,  # ИСПРАВИЛИ: относительное время
                id='price_monitor_startup',
                name='Initial Price Monitor',
                replace_existing=True
            )
            
            self.scheduler.start()
            self._running = True
            
            # Показываем расписание
            jobs = self.scheduler.get_jobs()
            logger.info(f"📅 Scheduled {len(jobs)} jobs:")
            for job in jobs:
                next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'N/A'
                logger.info(f"  - {job.name}: next run at {next_run}")
                
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    async def stop(self):
        """Stop the scheduler"""
        if not self._running:
            logger.warning("Scheduler is not running")
            return
            
        try:
            logger.info("🛑 Stopping price monitoring scheduler...")
            self.scheduler.shutdown()
            self._running = False
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
    
    def get_status(self):
        """Get scheduler status"""
        if not self._running:
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

# Singleton instance
scheduler_service = SchedulerService()