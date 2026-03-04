"""
Job to compare on-chain pack balances with user_packs inventory.

For each user with a wallet address and each active PackType, this job compares:
- on-chain ERC-1155 balanceOf(user, packTypeId)
- count of unopened UserPack records in the database

Differences are logged as warnings so operators can investigate or fix them.
"""

import logging
from typing import List, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from models.database import AsyncSessionLocal
from models.user_models import User
from models.pack_models import PackType
from models.user_pack_models import UserPack
from services.pack_mint_service import get_on_chain_pack_balance

logger = logging.getLogger("pack_health")


async def _load_users_and_pack_types(db: AsyncSession) -> Tuple[List[Tuple[int, str]], List[int]]:
    """Load users with wallet addresses and active pack type IDs."""
    users_result = await db.execute(
        select(User.id, User.wallet_address).where(User.wallet_address.isnot(None))
    )
    users: List[Tuple[int, str]] = [
        (row[0], (row[1] or "").strip()) for row in users_result.all() if (row[1] or "").strip()
    ]

    packs_result = await db.execute(select(PackType.id).where(PackType.is_active == True))
    pack_type_ids: List[int] = [row[0] for row in packs_result.all()]

    return users, pack_type_ids


async def run_pack_inventory_health_check() -> None:
    """
    Compare on-chain pack balances with user_packs for all users.

    Logs warnings when the counts are not equal. Does not mutate database or contracts.
    """
    if not (Config.PACKS_CONTRACT_ADDRESS or "").strip():
        return

    async with AsyncSessionLocal() as db:
        try:
            users, pack_type_ids = await _load_users_and_pack_types(db)
            if not users or not pack_type_ids:
                return

            for user_id, wallet in users:
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

                    if on_chain != db_unopened:
                        logger.warning(
                            "Pack inventory mismatch: user_id=%s wallet=%s pack_type_id=%s "
                            "on_chain=%s db_unopened=%s diff=%s",
                            user_id,
                            wallet[:10],
                            pack_type_id,
                            on_chain,
                            db_unopened,
                            on_chain - db_unopened,
                        )
        except Exception as e:
            logger.exception("Pack inventory health check failed: %s", e)

