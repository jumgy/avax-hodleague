"""
Seed pack_types table from a JSON file exported from production or edited manually.

Usage (inside Docker or venv):

    python -m scripts.seed_pack_types_from_json path/to/pack_types.json

Expected JSON structure:

{
  "items": [
    {
      "id": 1,
      "name": "Starter Pack",
      "description": "Starter pack with 5 cards",
      "image_url": "https://.../pack.png",
      "header_image_url": "https://.../header.png",
      "cards_per_pack": 5,
      "price": 0.0,
      "currency": "USD",
      "is_active": true,
      "guaranteed_slots": {
        "card_pools": {
          "common": ["BTC", "ETH", "AVAX", "SOL", "LINK"]
        },
        "drop_rules": {
          "common": 5
        }
      }
    }
  ]
}

The guaranteed_slots JSON is used by PackOpeningService and must contain:
  - "card_pools": mapping from category name to list of token symbols
  - "drop_rules": mapping from category name to integer count per pack
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_database
from models.pack_models import PackType


NOW = datetime.now(timezone.utc)


async def _upsert_pack_types_from_items(
    items: List[Dict[str, Any]],
    db: AsyncSession,
) -> None:
    """Insert or update pack types from a list of JSON dicts.

    Args:
        items: List of pack type objects from JSON ("items" array).
        db: Async SQLAlchemy session.
    """
    created = 0
    updated = 0

    for raw in items:
        try:
            pack_type_id = int(raw["id"])
            name = str(raw["name"])
            description = str(raw["description"])
            image_url = str(raw["image_url"])
            header_image_url = str(raw["header_image_url"])
            cards_per_pack = int(raw.get("cards_per_pack", 5))
            price_raw = raw.get("price", 0)
            currency = str(raw.get("currency", "USD"))
            is_active = bool(raw.get("is_active", True))
            guaranteed_slots = raw.get("guaranteed_slots")  # can be None
        except KeyError as exc:
            print(f"Skipping entry without required field {exc}: {raw}")
            continue

        # Normalize price to Decimal to match Numeric column.
        try:
            price = Decimal(str(price_raw))
        except Exception:
            raise ValueError(f"Invalid price value for pack type {name}: {price_raw!r}")

        result = await db.execute(select(PackType).where(PackType.id == pack_type_id))
        pack_type: PackType | None = result.scalar_one_or_none()

        if pack_type is None:
            # Ensure we do not accidentally violate unique(name) with a different id.
            existing_by_name = await db.execute(
                select(PackType).where(PackType.name == name)
            )
            by_name = existing_by_name.scalar_one_or_none()
            if by_name is not None and by_name.id != pack_type_id:
                raise ValueError(
                    f"PackType name conflict for {name}: "
                    f"JSON id={pack_type_id}, DB id={by_name.id}"
                )

            pack_type = PackType(
                id=pack_type_id,
                name=name,
                description=description,
                image_url=image_url,
                header_image_url=header_image_url,
                cards_per_pack=cards_per_pack,
                price=price,
                currency=currency,
                guaranteed_slots=guaranteed_slots,
                is_active=is_active,
                available_from=None,
                available_until=None,
                supply=None,
            )
            db.add(pack_type)
            created += 1
        else:
            pack_type.name = name
            pack_type.description = description
            pack_type.image_url = image_url
            pack_type.header_image_url = header_image_url
            pack_type.cards_per_pack = cards_per_pack
            pack_type.price = price
            pack_type.currency = currency
            pack_type.guaranteed_slots = guaranteed_slots
            pack_type.is_active = is_active
            updated += 1

    # Align PostgreSQL sequence with the highest id we just wrote.
    await db.execute(
        text(
            "SELECT setval("
            "  pg_get_serial_sequence('pack_types', 'id'),"
            "  COALESCE((SELECT MAX(id) FROM pack_types), 1)"
            ")"
        )
    )

    await db.flush()
    print(f"Pack types upserted. Created: {created}, Updated: {updated}")


async def seed_from_file(path: str) -> None:
    """Seed pack_types table from a JSON file.

    Args:
        path: Path to JSON file with structure {\"items\": [...] }.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items") or []
    if not isinstance(items, list):
        raise ValueError("JSON must contain 'items' array")

    print(f"[seed_pack_types_from_json] Loaded {len(items)} pack type entries from {path}")

    await init_database()
    async with AsyncSessionLocal() as db:
        await _upsert_pack_types_from_items(items, db)
        await db.commit()

    print("[seed_pack_types_from_json] Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.seed_pack_types_from_json path/to/pack_types.json")
        sys.exit(1)

    json_path = sys.argv[1]
    asyncio.run(seed_from_file(json_path))

