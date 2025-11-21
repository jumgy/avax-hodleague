# models/user_models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
from .database import Base

class User(Base):
    """
    Game users with wallet addresses and referral system
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42), nullable=False, unique=True)  # Ethereum address format
    nickname = Column(String(50), nullable=False, unique=True)
    referral_route = Column(String(20), nullable=False, unique=True)  # Short referral code
    avatar_url = Column(String(500), nullable=False)  # User avatar image
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User(id={self.id}, nickname='{self.nickname}', wallet='{self.wallet_address[:10]}...')>"