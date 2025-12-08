from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class UserCard(Base):
    """
    Individual card instances owned by users.
    """
    __tablename__ = 'user_cards'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    card_id = Column(Integer, ForeignKey('cards.id'), nullable=False)
    pack_opening_id = Column(Integer, ForeignKey('pack_openings.id'), nullable=True)
    obtained_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    source = Column(String(20), nullable=False, default="pack_opening")
    status = Column(String(20), nullable=False, default="available")
    is_active = Column(Boolean, nullable=False, default=True)
    transaction_hash = Column(String(66), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    card = relationship("Card")
    pack_opening = relationship("PackOpening", back_populates="cards")
    
    def __repr__(self):
        return f"<UserCard(id={self.id}, user_id={self.user_id}, card_id={self.card_id}, status='{self.status}')>"

class UserCardStatus:
    AVAILABLE = "available"
    LOCKED = "locked"
    LISTED = "listed"
    ALL_STATUSES = [AVAILABLE, LOCKED, LISTED]
    
    @classmethod
    def is_valid(cls, status):
        return status in cls.ALL_STATUSES

class UserCardSource:
    PACK_OPENING = "pack_opening"
    REWARD = "reward"
    ADMIN = "admin"
    PURCHASE = "purchase"
    ALL_SOURCES = [PACK_OPENING, REWARD, ADMIN, PURCHASE]
    
    @classmethod
    def is_valid(cls, source):
        return source in cls.ALL_SOURCES