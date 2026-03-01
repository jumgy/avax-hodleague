# services/lock_service.py
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)


class JobLockService:
    """Database-backed distributed lock to prevent concurrent job runs.

    Usage:
        async with JobLockService(db, "my_job", 300) as lock:
            if not lock.locked:
                return  # Job already running
            # ... do work ...
    """

    def __init__(self, db: AsyncSession, job_name: str, lock_timeout_seconds: int = 300):
        """Args:
            db: Database session.
            job_name: Unique job name (e.g. "tournament_lifecycle").
            lock_timeout_seconds: Max lock duration (guard against stuck jobs).
        """
        self.db = db
        self.job_name = job_name
        self.lock_id = str(uuid.uuid4())
        self.lock_timeout = lock_timeout_seconds
        self.locked = False
    
    async def __aenter__(self):
        """Acquire lock on context entry."""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock on context exit."""
        await self.release()
    
    async def acquire(self) -> bool:
        """Try to acquire lock. Returns True on success. Uses INSERT ON CONFLICT for atomicity."""
        try:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=self.lock_timeout)
            
            # Step 1: Remove expired locks
            await self.db.execute(
                text("DELETE FROM job_locks WHERE expires_at < :now"),
                {"now": now}
            )
            await self.db.commit()
            
            # Step 2: Try to insert lock (atomic)
            result = await self.db.execute(
                text("""
                    INSERT INTO job_locks (job_name, locked_at, locked_by, expires_at)
                    VALUES (:job_name, :locked_at, :locked_by, :expires_at)
                    ON CONFLICT (job_name) DO NOTHING
                    RETURNING job_name
                """),
                {
                    "job_name": self.job_name,
                    "locked_at": now,
                    "locked_by": self.lock_id,
                    "expires_at": expires_at
                }
            )
            await self.db.commit()
            
            # Row returned means we acquired the lock
            self.locked = result.fetchone() is not None
            
            if self.locked:
                logger.info(f"Lock acquired: '{self.job_name}' (id: {self.lock_id[:8]}...)")
            else:
                logger.warning(f"Lock busy: '{self.job_name}' is already running")
            
            return self.locked
            
        except Exception as e:
            logger.error(f"Failed to acquire lock '{self.job_name}': {e}")
            await self.db.rollback()
            return False
    
    async def release(self):
        """Release the lock."""
        if not self.locked:
            return
        
        try:
            await self.db.execute(
                text("DELETE FROM job_locks WHERE job_name = :job_name AND locked_by = :locked_by"),
                {"job_name": self.job_name, "locked_by": self.lock_id}
            )
            await self.db.commit()
            logger.info(f"Lock released: '{self.job_name}'")
            self.locked = False
        except Exception as e:
            logger.error(f"Failed to release lock '{self.job_name}': {e}")
            await self.db.rollback()