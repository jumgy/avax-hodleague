from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class AuditLog(Base):
    """
    Audit trail for critical operations and changes.
    """
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    action_type = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    admin_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    transaction_hash = Column(String(66), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, 
                   default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    admin = relationship("User", foreign_keys=[admin_id])
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action_type}', entity='{self.entity_type}', entity_id={self.entity_id})>"

class AuditAction:
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    PACK_OPEN = "pack_open"
    TOURNAMENT_JOIN = "tournament_join"
    REWARD_CLAIM = "reward_claim"
    CARD_TRANSFER = "card_transfer"
    ADMIN_ACTION = "admin_action"
    ALL_ACTIONS = [CREATE, UPDATE, DELETE, PACK_OPEN, TOURNAMENT_JOIN, REWARD_CLAIM, CARD_TRANSFER, ADMIN_ACTION]
    
    @classmethod
    def is_valid(cls, action):
        return action in cls.ALL_ACTIONS

class AuditEntity:
    USER = "user"
    CARD = "card"
    PACK = "pack"
    TOURNAMENT = "tournament"
    REWARD = "reward"
    TOURNAMENT_DECK = "tournament_deck"
    ALL_ENTITIES = [USER, CARD, PACK, TOURNAMENT, REWARD, TOURNAMENT_DECK]
    
    @classmethod
    def is_valid(cls, entity):
        return entity in cls.ALL_ENTITIES