from sqlalchemy import Column, String, DateTime, Index
from datetime import datetime, timezone
from .database import Base

class JobLock(Base):
    """
    Distributed locks для фоновых задач
    """
    __tablename__ = 'job_locks'
    
    job_name = Column(String(100), primary_key=True, nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=False)
    locked_by = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    __table_args__ = (
        Index('idx_job_locks_expires', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<JobLock(job='{self.job_name}', locked_by='{self.locked_by}')>"