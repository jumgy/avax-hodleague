from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, JSON, Text, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class TournamentDeck(Base):
    """
    Player deck submissions for tournaments.
    """
    __tablename__ = 'tournament_decks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    deck_composition = Column(JSON, nullable=False)
    deck_hash = Column(String(64), nullable=False)
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_valid = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    validation_errors = Column(Text, nullable=True)
    transaction_hash = Column(String(66), nullable=True)
    
    # Relationships
    tournament = relationship("Tournament")
    user = relationship("User")
    result = relationship("TournamentResult", back_populates="tournament_deck", uselist=False)
    
    def __repr__(self):
        return f"<TournamentDeck(id={self.id}, tournament_id={self.tournament_id}, user_id={self.user_id}, valid={self.is_valid})>"

class TournamentPrizeConfig(Base):
    """
    Prize distribution configuration for tournaments.
    """
    __tablename__ = 'tournament_prize_config'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    position_from = Column(Integer, nullable=False)
    position_to = Column(Integer, nullable=False)
    reward_type_id = Column(Integer, ForeignKey('reward_types.id'), nullable=False)
    reward_amount = Column(Numeric(20, 8), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship("Tournament")
    reward_type = relationship("RewardType")
    
    def __repr__(self):
        return f"<TournamentPrizeConfig(tournament_id={self.tournament_id}, positions={self.position_from}-{self.position_to}, amount={self.reward_amount})>"

class TournamentResult(Base):
    """
    Final results and rankings for tournament participants.
    """
    __tablename__ = 'tournament_results'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    tournament_deck_id = Column(Integer, ForeignKey('tournament_decks.id'), nullable=False)
    
    final_position = Column(Integer, nullable=False)
    final_score = Column(Numeric(20, 4), nullable=False)
    
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship("Tournament")
    tournament_deck = relationship("TournamentDeck", back_populates="result")
    rewards = relationship("UserReward", back_populates="tournament_result")
    
    def __repr__(self):
        return f"<TournamentResult(id={self.id}, tournament_id={self.tournament_id}, position={self.final_position})>"