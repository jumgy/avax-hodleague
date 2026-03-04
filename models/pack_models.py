from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Numeric, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class PackType(Base):
    """
    Pack types with different configurations and prices.
    """
    __tablename__ = 'pack_types'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=False)
    header_image_url = Column(String(500), nullable=False)
    cards_per_pack = Column(Integer, nullable=False, default=5)
    price = Column(Numeric(10, 2), nullable=False, default=0.00)
    currency = Column(String(20), nullable=False, default="USD")
    supply = Column(Integer, nullable=True)
    available_from = Column(DateTime(timezone=True), nullable=True)
    available_until = Column(DateTime(timezone=True), nullable=True)
    guaranteed_slots = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, 
                   default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, 
                    default=lambda: datetime.now(timezone.utc),
                    onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    rarity_configs = relationship("PackRarityConfig", back_populates="pack_type", cascade="all, delete-orphan")
    user_packs = relationship("UserPack", back_populates="pack_type")
    
    def __repr__(self):
        return f"<PackType(id={self.id}, name='{self.name}', price={self.price})>"