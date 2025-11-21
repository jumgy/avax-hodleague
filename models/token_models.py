# models/token_models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Token(Base):
    """
    Tokens available in the fantasy game.
    Managed through admin interface.
    """
    __tablename__ = 'tokens'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # "Bitcoin"
    symbol = Column(String(20), nullable=False, unique=True)  # "BTC"  
    weight = Column(Integer, nullable=False)  # Tournament weight (1-10)
    image_url = Column(String(500), nullable=False)  # Token logo URL
    is_active = Column(Boolean, nullable=False, default=True)  # Active in game
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    prices = relationship("TokenPrice", back_populates="token", cascade="all, delete-orphan")
    cards = relationship("Card", back_populates="token", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Token(id={self.id}, symbol='{self.symbol}', name='{self.name}', weight={self.weight})>"


class TokenPrice(Base):
    """
    Historical price data for tokens.
    Updated every 30 minutes from exchange APIs.
    """
    __tablename__ = 'token_prices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_id = Column(Integer, ForeignKey('tokens.id'), nullable=False)
    price = Column(Float, nullable=False)  # Current price in USD
    market_cap = Column(Float, nullable=False)  # Market cap in USD
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    token = relationship("Token", back_populates="prices")
    
    def __repr__(self):
        return f"<TokenPrice(token_id={self.token_id}, price=${self.price:.2f}, created_at={self.created_at})>"