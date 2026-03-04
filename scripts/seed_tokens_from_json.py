"""
Seed tokens table from a JSON file exported from production.

Usage (inside Docker or venv):

    python -m scripts.seed_tokens_from_json path/to/tokens.json

The JSON format must match:

{
  "items": [
    {
      "id": 3,
      "name": "Bitcoin",
      "symbol": "BTC",
      "weight": 6,
      "image_url": "https://...",
      "is_active": true,
      ...
    },
    ...
  ]
}

All other fields in the JSON are ignored. Primary keys (id) are preserved and
the PostgreSQL sequence is advanced to MAX(id).
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List

from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_database
from models.token_models import Token


NOW = datetime.now(timezone.utc)


async def _upsert_tokens_from_items(items: List[Dict[str, Any]], db: AsyncSession) -> None:
    """Insert or update tokens from a list of JSON dicts.

    Args:
        items: List of token objects from JSON ("items" array).
        db: Async SQLAlchemy session.
    """
    created = 0
    updated = 0

    for raw in items:
        try:
            token_id = int(raw["id"])
            name = str(raw["name"])
            symbol = str(raw["symbol"])
            weight = int(raw["weight"])
            image_url = str(raw["image_url"])
            is_active = bool(raw.get("is_active", True))
        except KeyError as exc:
            print(f"Skipping entry without required field {exc}: {raw}")
            continue

        # Prefer matching by id to preserve primary keys exactly.
        result = await db.execute(select(Token).where(Token.id == token_id))
        token: Token | None = result.scalar_one_or_none()

        if token is None:
            # Ensure we do not accidentally violate unique(symbol) with a different id.
            existing_by_symbol = await db.execute(
                select(Token).where(Token.symbol == symbol)
            )
            by_symbol = existing_by_symbol.scalar_one_or_none()
            if by_symbol is not None and by_symbol.id != token_id:
                raise ValueError(
                    f"Token symbol conflict for {symbol}: "
                    f"JSON id={token_id}, DB id={by_symbol.id}"
                )

            token = Token(
                id=token_id,
                name=name,
                symbol=symbol,
                weight=weight,
                image_url=image_url,
                is_active=is_active,
            )
            db.add(token)
            created += 1
        else:
            token.name = name
            token.symbol = symbol
            token.weight = weight
            token.image_url = image_url
            token.is_active = is_active
            updated += 1

    # Align PostgreSQL sequence with the highest id we just wrote.
    await db.execute(
        text(
            "SELECT setval("
            "  pg_get_serial_sequence('tokens', 'id'),"
            "  COALESCE((SELECT MAX(id) FROM tokens), 1)"
            ")"
        )
    )

    await db.flush()
    print(f"Tokens upserted. Created: {created}, Updated: {updated}")


async def seed_from_file(path: str) -> None:
    """Seed tokens table from a JSON file.

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

    print(f"[seed_tokens_from_json] Loaded {len(items)} token entries from {path}")

    await init_database()
    async with AsyncSessionLocal() as db:
        await _upsert_tokens_from_items(items, db)
        await db.commit()

    print("[seed_tokens_from_json] Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.seed_tokens_from_json path/to/tokens.json")
        sys.exit(1)

    json_path = sys.argv[1]
    asyncio.run(seed_from_file(json_path))

