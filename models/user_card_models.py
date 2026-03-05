from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, BigInteger, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class UserCard(Base):
    """
    Individual card instances owned by users.
    On-chain flow: nft_token_id + chain_id + contract_address link to ERC-721 token.
    """
    __tablename__ = 'user_cards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    card_id = Column(Integer, ForeignKey('cards.id'), nullable=False)
    pack_opening_id = Column(Integer, ForeignKey('pack_openings.id'), nullable=True)
    obtained_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(20), nullable=False, default="pack_opening")
    status = Column(String(20), nullable=False, default="available")
    is_active = Column(Boolean, nullable=False, default=True)
    transaction_hash = Column(String(66), nullable=True)
    # Full 256-bit ERC-721 token id stored as NUMERIC(78,0) in PostgreSQL.
    nft_token_id = Column(Numeric(78, 0), nullable=True)
    chain_id = Column(Integer, nullable=True)
    contract_address = Column(String(42), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, 
                   default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User")
    card = relationship("Card", back_populates="user_cards")
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