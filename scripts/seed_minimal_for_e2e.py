"""
Minimal seed for E2E and tests: tokens, rarities, cards, pack_types.
No external data/ module. Run inside Docker: python -m scripts.seed_minimal_for_e2e
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_database
from models.token_models import Token
from models.rarity_models import Rarity
from models.card_models import Card
from models.pack_models import PackType


NOW = datetime.now(timezone.utc)


async def seed() -> None:
    await init_database()
    async with AsyncSessionLocal() as db:
        # Rarities
        r = await db.execute(select(Rarity).limit(1))
        if r.scalar_one_or_none() is None:
            db.add(Rarity(name="common", description="Common", score_bonus=0, color="#888888", is_active=True))
            await db.flush()
            print("Inserted rarities")

        # Tokens (minimal set)
        r = await db.execute(select(Token).limit(1))
        if r.scalar_one_or_none() is None:
            for sym, name in [("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("AVAX", "Avalanche"), ("SOL", "Solana"), ("LINK", "Chainlink")]:
                db.add(Token(symbol=sym, name=name, weight=10, image_url="https://example.com/1.png", is_active=True))
            await db.flush()
            print("Inserted tokens")

        # Cards: one card per token, rarity_id=1
        r = await db.execute(select(Card).limit(1))
        if r.scalar_one_or_none() is None:
            result = await db.execute(select(Token.id))
            token_ids = [row[0] for row in result.all()]
            rarity_result = await db.execute(select(Rarity.id).limit(1))
            rid = rarity_result.scalar_one()
            for tid in token_ids:
                db.add(Card(token_id=tid, rarity_id=rid, design_type="classic", template_image_url="https://example.com/card.png", is_active=True))
            await db.flush()
            print("Inserted cards")

        # Pack types (id 1 for E2E, id 6 for existing tests)
        r = await db.execute(select(PackType).limit(1))
        if r.scalar_one_or_none() is None:
            result = await db.execute(select(Token.symbol).where(Token.is_active.is_(True)).limit(5))
            symbols = [row[0] for row in result.all()] or ["BTC", "ETH", "AVAX", "SOL", "LINK"]
            slots = {"card_pools": {"common": symbols}, "drop_rules": {"common": len(symbols)}}
            for pid, pname in [(1, "Starter Pack"), (6, "Test Pack")]:
                db.add(PackType(
                    id=pid,
                    name=pname,
                    description="Minimal pack",
                    image_url="https://example.com/pack.png",
                    header_image_url="https://example.com/header.png",
                    cards_per_pack=len(symbols),
                    price=0,
                    currency="USD",
                    is_active=True,
                    guaranteed_slots=slots,
                ))
            await db.execute(text("SELECT setval(pg_get_serial_sequence('pack_types', 'id'), (SELECT MAX(id) FROM pack_types))"))
            await db.flush()
            print("Inserted pack_types 1 and 6")

        await db.commit()
    print("Minimal seed done.")


if __name__ == "__main__":
    asyncio.run(seed())
