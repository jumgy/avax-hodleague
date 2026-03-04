from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from datetime import datetime, timezone
from .database import Base

class Rarity(Base):
    """
    Reference table for card rarities with bonuses and UI settings.
    """
    __tablename__ = 'rarities'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(20), nullable=False, unique=True)  # "common", "rare", "epic", "legendary"
    description = Column(Text, nullable=False)  # Description of rarity
    score_bonus = Column(Integer, nullable=False, default=0)  # Points bonus for this rarity
    color = Column(String(7), nullable=False, default='#000000')  # HEX color for UI
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, 
                   default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, 
                    default=lambda: datetime.now(timezone.utc),
                    onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Rarity(id={self.id}, name='{self.name}', score_bonus={self.score_bonus})>"
    

