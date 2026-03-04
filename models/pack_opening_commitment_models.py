"""
Model for pack opening commit-reveal (prepare-open flow).
Tracks commitment_hash, server_seed, card_ids and status until event listener completes.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, LargeBinary, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from .database import Base


class PackOpeningCommitment(Base):
    """
    Commit-reveal record for on-chain pack opening.
    Created on prepare-open; server_seed revealed when user submits openPack tx.
    """
    __tablename__ = "pack_opening_commitments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pack_type_id = Column(Integer, ForeignKey("pack_types.id", ondelete="CASCADE"), nullable=False)
    commitment_hash = Column(String(66), nullable=False)
    server_seed = Column(LargeBinary(32), nullable=True)
    card_ids = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User")
    pack_type = relationship("PackType")
