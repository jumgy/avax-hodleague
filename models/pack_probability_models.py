from sqlalchemy import Column, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class PackRarityConfig(Base):
    """
    Rarity drop rates for specific pack types.
    """
    __tablename__ = 'pack_rarity_configs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pack_type_id = Column(Integer, ForeignKey('pack_types.id'), nullable=False)
    rarity_id = Column(Integer, ForeignKey('rarities.id'), nullable=False)
    drop_rate = Column(Numeric(5, 4), nullable=False, default=0.0000)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, 
                   default=lambda: datetime.now(timezone.utc))
    
    updated_at = Column(DateTime(timezone=True), nullable=False, 
                    default=lambda: datetime.now(timezone.utc),
                    onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    pack_type = relationship("PackType", back_populates="rarity_configs")
    rarity = relationship("Rarity")
    
    def __repr__(self):
        return f"<PackRarityConfig(pack_type_id={self.pack_type_id}, rarity_id={self.rarity_id}, rate={self.drop_rate})>"

class CardWeight(Base):
    """
    Dynamic weights for individual cards within rarities.
    """
    __tablename__ = 'card_weights'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey('cards.id'), nullable=False)
    base_weight = Column(Numeric(8, 4), nullable=False, default=1.0000)
    current_multiplier = Column(Numeric(6, 4), nullable=False, default=1.0000)
    last_updated = Column(DateTime(timezone=True), nullable=False, 
                     default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    card = relationship("Card")
    
    def __repr__(self):
        return f"<CardWeight(card_id={self.card_id}, weight={self.base_weight}, multiplier={self.current_multiplier})>"
    
    @property
    def final_weight(self):
        return float(self.base_weight) * float(self.current_multiplier)