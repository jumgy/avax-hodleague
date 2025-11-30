# models/tournament_models.py
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from .database import Base

class Tournament(Base):
    """
    Game tournaments with registration, ongoing, and finished states.
    Only one active tournament at a time.
    """
    __tablename__ = 'tournaments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_number = Column(Integer, nullable=False, unique=True)  # Sequential tournament number
    
    status = Column(String(20), nullable=False, default="registration")  # "registration", "ongoing", "finished"
    
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Tournament(id={self.id}, number={self.tournament_number}, status='{self.status}')>"

    @property
    def is_active(self):
        """Check if tournament is currently active (registration or ongoing)"""
        return self.status in ["registration", "ongoing"]

    @property
    def duration_days(self):
        """Calculate tournament duration in days"""
        return (self.end_date - self.start_date).days

class TournamentStatus:
    REGISTRATION = "registration"
    ONGOING = "ongoing"
    FINISHED = "finished"
    
    ALL_STATUSES = [REGISTRATION, ONGOING, FINISHED]
    
    @classmethod
    def is_valid(cls, status):
        return status in cls.ALL_STATUSES
