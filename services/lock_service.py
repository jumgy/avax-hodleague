# services/lock_service.py
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)


class JobLockService:
    """
    Distributed lock через БД для предотвращения одновременного запуска джобов
    
    Usage:
        async with JobLockService(db, "my_job", 300) as lock:
            if not lock.locked:
                return  # Джоб уже выполняется
            # ... выполнить работу ...
    """
    
    def __init__(self, db: AsyncSession, job_name: str, lock_timeout_seconds: int = 300):
        """
        Args:
            db: Database session
            job_name: Уникальное имя джоба (например, "tournament_lifecycle")
            lock_timeout_seconds: Максимальное время блокировки (защита от зависших джобов)
        """
        self.db = db
        self.job_name = job_name
        self.lock_id = str(uuid.uuid4())
        self.lock_timeout = lock_timeout_seconds
        self.locked = False
    
    async def __aenter__(self):
        """Acquire lock при входе в контекст"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock при выходе из контекста"""
        await self.release()
    
    async def acquire(self) -> bool:
        """
        Пытается получить блокировку. Возвращает True если успешно.
        Использует INSERT ON CONFLICT для атомарности.
        """
        try:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=self.lock_timeout)
            
            # Шаг 1: Удаляем просроченные блокировки
            await self.db.execute(
                text("DELETE FROM job_locks WHERE expires_at < :now"),
                {"now": now}
            )
            await self.db.commit()
            
            # Шаг 2: Пытаемся вставить блокировку (атомарная операция)
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
            
            # Если вернулась строка — мы захватили лок
            self.locked = result.fetchone() is not None
            
            if self.locked:
                logger.info(f"🔒 Lock acquired: '{self.job_name}' (id: {self.lock_id[:8]}...)")
            else:
                logger.warning(f"⏳ Lock busy: '{self.job_name}' is already running")
            
            return self.locked
            
        except Exception as e:
            logger.error(f"❌ Failed to acquire lock '{self.job_name}': {e}")
            await self.db.rollback()
            return False
    
    async def release(self):
        """Освобождает блокировку"""
        if not self.locked:
            return
        
        try:
            await self.db.execute(
                text("DELETE FROM job_locks WHERE job_name = :job_name AND locked_by = :locked_by"),
                {"job_name": self.job_name, "locked_by": self.lock_id}
            )
            await self.db.commit()
            logger.info(f"🔓 Lock released: '{self.job_name}'")
            self.locked = False
        except Exception as e:
            logger.error(f"❌ Failed to release lock '{self.job_name}': {e}")
            await self.db.rollback()