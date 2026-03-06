"""
Admin endpoints for off-chain pack granting.
"""

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from pydantic import BaseModel

from models.database import get_async_db
from models.user_models import User
from models.user_pack_models import UserPack, PackSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import verify_admin_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/panel/packs")


class MintPackRequest(BaseModel):
    user_id: int
    pack_type_id: int
    amount: int = 1


class MintPackResponse(BaseModel):
    user_id: int
    pack_type_id: int
    amount: int
    wallet_address: str


@router.post("/mint", response_model=MintPackResponse)
async def admin_mint_pack(
    body: MintPackRequest,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    """
    Grant packs to a user (off-chain only).
    Creates UserPack records; no on-chain mint is performed.
    """
    if body.amount < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be at least 1",
        )
    if body.pack_type_id < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pack_type_id must be at least 1",
        )

    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Pure off-chain grant: create UserPack rows without touching blockchain.
    for _ in range(body.amount):
        user_pack = UserPack(
            user_id=body.user_id,
            pack_type_id=body.pack_type_id,
            obtained_at=datetime.now(timezone.utc),
            expires_at=None,
            is_opened=False,
            source=PackSource.ADMIN,
        )
        db.add(user_pack)

    return MintPackResponse(
        user_id=body.user_id,
        pack_type_id=body.pack_type_id,
        amount=body.amount,
        wallet_address=user.wallet_address,
    )


class UserPackItem(BaseModel):
    id: int
    pack_type_id: int
    is_opened: bool
    obtained_at: str


class UserPackListResponse(BaseModel):
    user_id: int
    packs: List[UserPackItem]


@router.get(
    "/list/{user_id}",
    response_model=UserPackListResponse,
    summary="List user packs (admin-only)",
    description="Return all packs for a given user (off-chain UserPack records).",
)
async def list_user_packs(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    admin: dict = Depends(verify_admin_token),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    packs_result = await db.execute(
        select(UserPack).where(UserPack.user_id == user_id).order_by(UserPack.id)
    )
    user_packs = packs_result.scalars().all()

    items: List[UserPackItem] = []
    for p in user_packs:
        items.append(
            UserPackItem(
                id=p.id,
                pack_type_id=p.pack_type_id,
                is_opened=p.is_opened,
                obtained_at=p.obtained_at.isoformat() if p.obtained_at else "",
            )
        )

    return UserPackListResponse(user_id=user.id, packs=items)
