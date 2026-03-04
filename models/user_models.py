# models/user_models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class User(Base):
    """
    Game users with wallet addresses and referral system
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42), nullable=False, unique=True)
    nickname = Column(String(50), nullable=False, unique=True)
    referral_route = Column(String(100), nullable=False, unique=True)
    avatar_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    referred_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    referral_count = Column(Integer, nullable=False, default=0)
    
    # Onboarding: {"1": true, "2": false, "3": true}
    onboarding_steps = Column(JSON, nullable=True, default=dict)
    
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
    rewards = relationship("UserReward", back_populates="user")
    referrer = relationship("User", remote_side=[id], foreign_keys=[referred_by_id], backref="referrals")
    
    def __repr__(self):
        return f"<User(id={self.id}, nickname='{self.nickname}', wallet='{self.wallet_address[:10]}...')>"