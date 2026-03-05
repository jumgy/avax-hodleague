"""
Admin endpoints for off-chain pack granting and (legacy) pack inventory debugging.
"""

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from pydantic import BaseModel

from models.database import get_async_db
from models.user_models import User
from models.pack_models import PackType
from models.user_pack_models import UserPack, PackSource
from services.user_pack_grant_service import user_pack_grant_service
from services.pack_mint_service import get_on_chain_pack_balance, set_pack_price
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
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


class SetPackPriceRequest(BaseModel):
    pack_type_id: int
    price_wei: int  # Price in wei (0 = not for sale)


class SetPackPriceResponse(BaseModel):
    tx_hash: str
    pack_type_id: int
    price_wei: int


class PackInventoryItem(BaseModel):
    pack_type_id: int
    db_unopened: int
    on_chain_balance: int
    diff: int


class DebugInventoryResponse(BaseModel):
    user_id: int
    wallet_address: str
    items: List[PackInventoryItem]


class UserPackItem(BaseModel):
    id: int
    pack_type_id: int
    is_opened: bool
    obtained_at: str


class UserPackListResponse(BaseModel):
    user_id: int
    packs: List[UserPackItem]


@router.post("/set-price", response_model=SetPackPriceResponse)
async def admin_set_pack_price(
    body: SetPackPriceRequest,
    admin: dict = Depends(verify_admin_token),
):
    """
    Set on-chain pack price for buyPack. Requires DEFAULT_ADMIN_ROLE.
    Price in wei; 0 means pack is not for sale.
    """
    if body.pack_type_id < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pack_type_id must be at least 1",
        )
    if body.price_wei < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="price_wei must be non-negative",
        )

    try:
        tx_hash = await set_pack_price(
            pack_type_id=body.pack_type_id,
            price_wei=body.price_wei,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Set pack price failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set pack price",
        )

    return SetPackPriceResponse(
        tx_hash=tx_hash,
        pack_type_id=body.pack_type_id,
        price_wei=body.price_wei,
    )


@router.get(
    "/debug-inventory/{user_id}",
    response_model=DebugInventoryResponse,
    summary="Debug pack inventory for a user",
    description="Compare on-chain ERC-1155 balances with user_packs (unopened) for a given user.",
)
async def debug_pack_inventory(
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
    wallet = (user.wallet_address or "").strip()
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no wallet_address",
        )
    if not (Config.PACKS_CONTRACT_ADDRESS or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PACKS_CONTRACT_ADDRESS is not configured",
        )

    packs_result = await db.execute(
        select(PackType.id).where(PackType.is_active == True)
    )
    pack_type_ids = [row[0] for row in packs_result.all()]
    items: List[PackInventoryItem] = []

    for pack_type_id in pack_type_ids:
        on_chain = await get_on_chain_pack_balance(wallet, pack_type_id)
        if on_chain is None:
            continue
        db_count_result = await db.execute(
            select(func.count(UserPack.id)).where(
                UserPack.user_id == user_id,
                UserPack.pack_type_id == pack_type_id,
                UserPack.is_opened == False,
            )
        )
        db_unopened = db_count_result.scalar() or 0
        diff = int(on_chain) - int(db_unopened)
        items.append(
            PackInventoryItem(
                pack_type_id=pack_type_id,
                db_unopened=int(db_unopened),
                on_chain_balance=int(on_chain),
                diff=diff,
            )
        )

    return DebugInventoryResponse(
        user_id=user.id,
        wallet_address=wallet,
        items=items,
    )


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
