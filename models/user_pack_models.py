from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class UserPack(Base):
    """
    Pack instances owned by users.
    """
    __tablename__ = 'user_packs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    pack_type_id = Column(Integer, ForeignKey('pack_types.id'), nullable=False)
    obtained_at = Column(DateTime(timezone=True), nullable=False, 
                    default=lambda: datetime.now(timezone.utc))
    is_opened = Column(Boolean, nullable=False, default=False)
    source = Column(String(20), nullable=False, default="purchase")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, 
                   default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User")
    pack_type = relationship("PackType", back_populates="user_packs")
    opening = relationship("PackOpening", back_populates="pack", uselist=False)
    
    def __repr__(self):
        return f"<UserPack(id={self.id}, user_id={self.user_id}, pack_type_id={self.pack_type_id}, opened={self.is_opened})>"

class PackOpening(Base):
    """
    Pack opening logs and results.
    """
    __tablename__ = 'pack_openings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    pack_id = Column(Integer, ForeignKey('user_packs.id'), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, 
                  default=lambda: datetime.now(timezone.utc))
    cards_count = Column(Integer, nullable=False, default=0)
    transaction_hash = Column(String(66), nullable=True)
    
    # Relationships
    user = relationship("User")
    pack = relationship("UserPack", back_populates="opening")
    cards = relationship("UserCard", back_populates="pack_opening")

    
    def __repr__(self):
        return f"<PackOpening(id={self.id}, user_id={self.user_id}, pack_id={self.pack_id}, cards={self.cards_count})>"

class PackSource:
    PURCHASE = "purchase"
    REWARD = "reward"
    ADMIN = "admin"
    ALL_SOURCES = [PURCHASE, REWARD, ADMIN]
    
    @classmethod
    def is_valid(cls, source):
        return source in cls.ALL_SOURCES