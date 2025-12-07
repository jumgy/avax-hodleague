from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
class Card(Base):
    """
    Game cards based on tokens with different rarities and designs.
    One token can have multiple card variants.
    """
    __tablename__ = 'cards'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_id = Column(Integer, ForeignKey('tokens.id'), nullable=False)
    rarity_id = Column(Integer, ForeignKey('rarities.id'), nullable=False)
    design_type = Column(String(50), nullable=False)  # "classic", "neon", "retro", etc.
    background_image_url = Column(String(500), nullable=False)  # Card background/design
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Timestamps  
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    token = relationship("Token")
    rarity = relationship("Rarity")
    
    def __repr__(self):
        return f"<Card(id={self.id}, token_id={self.token_id}, rarity_id={self.rarity_id}, design='{self.design_type}')>"