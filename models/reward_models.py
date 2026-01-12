# models/reward_models.py

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Numeric, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class RewardType(Base):
    """
    Reference table for different reward types.
    """
    __tablename__ = 'reward_types'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    reward_category = Column(String(50), nullable=False)
    default_amount = Column(Numeric(20, 8), nullable=False, default=0.0)
    currency_type = Column(String(20), nullable=False, default="TOKENS")
    is_claimable = Column(Boolean, nullable=False, default=True)
    expires_after_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user_rewards = relationship("UserReward", back_populates="reward_type")

    def __repr__(self):
        return f"<RewardType(id={self.id}, name='{self.name}', category='{self.reward_category}')>"


class ClaimStatus:
    PENDING = "pending"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    ALL_STATUSES = [PENDING, CLAIMED, EXPIRED, CANCELLED]

    @classmethod
    def is_valid(cls, status):
        return status in cls.ALL_STATUSES


class UserReward(Base):
    """
    Rewards earned by users from tournaments or other sources
    """
    __tablename__ = 'user_rewards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    reward_type_id = Column(Integer, ForeignKey('reward_types.id'), nullable=False)
    amount = Column(Numeric(20, 8), nullable=False)
    tournament_result_id = Column(Integer, ForeignKey('tournament_results.id'), nullable=True)

    # Timestamps - ✅ Исправлено
    earned_at = Column(
        DateTime(timezone=True), 
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    claimed_at = Column(DateTime(timezone=True), nullable=True)

    claim_status = Column(
        String(20), 
        nullable=False, 
        default=ClaimStatus.PENDING
    )

    expires_at = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(JSON, nullable=True)

    # Relationships
    user = relationship("User", back_populates="rewards")
    reward_type = relationship("RewardType", back_populates="user_rewards")
    tournament_result = relationship("TournamentResult", back_populates="user_reward")

    def __repr__(self):
        return (
            f"<UserReward(id={self.id}, user_id={self.user_id}, "
            f"reward_type_id={self.reward_type_id}, amount={self.amount}, "
            f"status={self.claim_status})>"
        )


class RewardCategory:
    TOKENS = "tokens"
    PACKS = "packs"
    TOURNAMENT_PRIZE = "tournament_prize"
    ACHIEVEMENT = "achievement"
    DAILY_LOGIN = "daily_login"

    ALL_CATEGORIES = [TOKENS, PACKS, TOURNAMENT_PRIZE, ACHIEVEMENT, DAILY_LOGIN]

    @classmethod
    def is_valid(cls, category):
        return category in cls.ALL_CATEGORIES