# models/token_score_models.py

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class TokenScore(Base):
    """
    Historical token scores calculated during tournaments.
    Stores snapshots every N minutes to determine final rankings.
    """
    __tablename__ = 'token_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=True)
    token_id = Column(Integer, ForeignKey('tokens.id'), nullable=False)
    
    # Score calculation
    calculated_score = Column(Numeric(20, 4), nullable=False)

    weight = Column(Integer, nullable=True)
    
    # Price data at calculation time (for debugging/audit)
    current_price = Column(Numeric(20, 8), nullable=True)
    snapshot_price = Column(Numeric(20, 8), nullable=True)
    price_change_percent = Column(Numeric(10, 4), nullable=True)
    
    # Timestamp
    calculated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    tournament = relationship("Tournament")
    token = relationship("Token")

    # Indexes for fast querying
    __table_args__ = (
        # Get all scores for a tournament, ordered by time
        Index('idx_token_scores_tournament_time', 'tournament_id', 'token_id', 'calculated_at'),
        # Get latest score for a token across tournaments
        Index('idx_token_scores_token_time', 'token_id', 'calculated_at'),
        # Get all scores at specific time
        Index('idx_token_scores_calculated_at', 'calculated_at'),
    )

    def __repr__(self):
        return (
            f"<TokenScore(id={self.id}, tournament_id={self.tournament_id}, "
            f"token_id={self.token_id}, score={self.calculated_score}, "
            f"calculated_at={self.calculated_at})>"
        )