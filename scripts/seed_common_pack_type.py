"""
Seed a single common-only pack type that always drops 5 random common cards.

Logic:
- Reads all active cards where rarity.name = "common" (and rarity.is_active = True).
- Builds guaranteed_slots:
    {
        "card_pools": {"common": [<all token symbols with common active cards>]},
        "drop_rules": {"common": 5}
    }
- Updates an existing PackType (if any) to use this configuration and sets it active.
- Deactivates all other PackType rows (is_active = False), so there is only one active pack.

Usage (inside Docker or venv):

    python -m scripts.seed_common_pack_type
"""

import asyncio
import os
import sys
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_database
from models.token_models import Token
from models.card_models import Card
from models.rarity_models import Rarity
from models.pack_models import PackType


async def _collect_common_token_symbols(db: AsyncSession) -> List[str]:
    """Return all token symbols that have at least one active common card."""
    result = await db.execute(
        select(Token.symbol)
        .join(Card, Card.token_id == Token.id)
        .join(Rarity, Card.rarity_id == Rarity.id)
        .where(
            Token.is_active.is_(True),
            Card.is_active.is_(True),
            Rarity.is_active.is_(True),
            Rarity.name == "common",
        )
        .distinct()
        .order_by(Token.symbol)
    )
    rows = result.all()
    return [row[0] for row in rows]


async def seed() -> None:
    """Create or update a single common-only PackType with 5-card drops."""
    await init_database()

    async with AsyncSessionLocal() as db:
        symbols = await _collect_common_token_symbols(db)
        if len(symbols) < 5:
            raise ValueError(
                f"Expected at least 5 active common cards, got {len(symbols)}. "
                "Add more common cards before seeding the pack type."
            )

        slots = {
            "card_pools": {"common": symbols},
            "drop_rules": {"common": 5},
        }

        # Pick a primary PackType to act as the only active pack.
        result = await db.execute(select(PackType).order_by(PackType.id))
        pack_types: List[PackType] = result.scalars().all()

        if pack_types:
            # Use the lowest-id PackType as the main common pack.
            main_pack = pack_types[0]
            print(
                f"Using existing pack_type id={main_pack.id}, name='{main_pack.name}' "
                "as the single common pack."
            )
        else:
            # Create a new pack type if none exist.
            main_pack = PackType(
                name="Starter Pack",
                description="Pack with 5 random common cards.",
                image_url="https://example.com/pack.png",
                header_image_url="https://example.com/header.png",
                cards_per_pack=5,
                price=0,
                currency="USD",
                is_active=True,
                guaranteed_slots=slots,
            )
            db.add(main_pack)
            pack_types = [main_pack]
            print("Created new pack_type 'Starter Pack' as the single common pack.")

        # Configure main pack: 5 cards, common-only pool.
        main_pack.cards_per_pack = 5
        main_pack.guaranteed_slots = slots
        main_pack.is_active = True

        # Deactivate all other pack types.
        for other in pack_types:
            if other.id != main_pack.id and other.is_active:
                other.is_active = False

        await db.commit()

        print(
            f"Configured pack_type id={main_pack.id}, name='{main_pack.name}' "
            f"with {len(symbols)} common symbols; cards_per_pack=5."
        )
        print("All other pack_types have been set to is_active = False.")


if __name__ == "__main__":
    asyncio.run(seed())

