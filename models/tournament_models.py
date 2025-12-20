from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
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
    gameplay_start_date = Column(DateTime, nullable=True)  # Когда начинается игра и фиксируются цены
    weight_limit = Column(Integer, nullable=False, default=30)  # Maximum deck weight limit
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Tournament(id={self.id}, number={self.tournament_number}, status='{self.status}', weight_limit={self.weight_limit})>"
    
    @property
    def is_active(self):
        """Check if tournament is currently active (registration or ongoing)"""
        return self.status in ["registration", "ongoing"]
    
    @property
    def duration_days(self):
        """Calculate tournament duration in days"""
        return (self.end_date - self.start_date).days
    
class TournamentTokenSnapshot(Base):
    """Snapshot цен токенов на момент старта турнира"""
    __tablename__ = 'tournament_token_snapshots'
    
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'))
    token_id = Column(Integer, ForeignKey('tokens.id'))
    snapshot_price = Column(Numeric(20, 8), nullable=False)
    snapshot_time = Column(DateTime, nullable=False)
    
class TournamentStatus:
    REGISTRATION = "registration"
    ONGOING = "ongoing"
    FINISHED = "finished"
    ALL_STATUSES = [REGISTRATION, ONGOING, FINISHED]
    
    @classmethod
    def is_valid(cls, status):
        return status in cls.ALL_STATUSES
    
class RarityType:
    """Constants for rarity types"""
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    
    ALL_RARITIES = [COMMON, RARE, EPIC, LEGENDARY]
    
    @classmethod
    def is_valid(cls, rarity):
        return rarity in cls.ALL_RARITIES