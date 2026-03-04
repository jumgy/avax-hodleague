# models/alpha_test_models.py
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from .database import Base

class AlphaTestAccess(Base):
    """Whitelist of addresses for alpha test access."""
    __tablename__ = 'alpha_test_access'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42), nullable=False, unique=True)  # Ethereum address
    created_at = Column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    
    def __repr__(self):
        return f"<AlphaTestAccess(id={self.id}, wallet='{self.wallet_address}')>"