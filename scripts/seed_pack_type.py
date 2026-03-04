"""
Seed a minimal pack type for local E2E testing.

Creates "Starter Pack" (id=1) with guaranteed_slots if no pack types exist.
Uses token symbols from tokens table; ensure tokens/cards are populated first.

Usage:
  python -m scripts.seed_pack_type
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_database
from models.pack_models import PackType
from models.token_models import Token


async def seed() -> None:
    await init_database()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PackType).limit(1))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Pack type already exists: {existing.name} (id={existing.id})")
            return

        result = await db.execute(
            select(Token.symbol)
            .where(Token.is_active.is_(True))
            .limit(10)
        )
        symbols = [r[0] for r in result.all()]
        if not symbols:
            print("No active tokens found. Run populate_tokens first.")
            sys.exit(1)
        symbols = symbols[:5]

        pack = PackType(
            name="Starter Pack",
            description="Test pack for local E2E",
            image_url="https://example.com/pack.png",
            header_image_url="https://example.com/header.png",
            cards_per_pack=len(symbols),
            price=0,
            currency="USD",
            is_active=True,
            guaranteed_slots={
                "card_pools": {"common": symbols},
                "drop_rules": {"common": len(symbols)},
            },
        )
        db.add(pack)
        await db.commit()
        await db.refresh(pack)
        print(f"Created pack type: {pack.name} (id={pack.id}), tokens: {symbols}")


if __name__ == "__main__":
    asyncio.run(seed())
