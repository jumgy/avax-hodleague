"""
Seed cards table from JSON exports (cards + template listing).

Usage (inside Docker or venv, from project root):

    python -m scripts.seed_cards_from_json data/cards.json data/card_templates.json

Expected JSON formats:

cards.json:
{
  "items": [
    {
      "id": 1,
      "token_id": 1,
      "rarity_id": 3,
      "design_type": "classic",
      "template_image_url": "https://old-cdn.example.com/...",
      "rendered_image_url": "...",
      "is_active": true,
      "token_symbol": "BTC",
      "rarity_name": "common",
      "rarity_color": "#6B7280"
      ...
    },
    ...
  ]
}

card_templates.json:
{
  "success": true,
  "total": 36,
  "templates": [
    {
      "filename": "btc_classic_common_20260304_....png",
      "url": "https://cdn-avax.hodleague.com/card_templates/btc_classic_common_20260304_....png",
      "token_symbol": "BTC",
      "design_type": "classic",
      "rarity": "common"
    },
    ...
  ]
}

The script:
- Preserves card ids, token_id and rarity_id from cards.json.
- Sets template_image_url to the new R2 URL from card_templates.json when a match
  is found by (token_symbol, design_type, rarity); otherwise keeps the original
  template_image_url from cards.json.
- Sets rendered_image_url and last_rendered_at to NULL so that the render job
  can regenerate images for the new environment.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_database
from models.card_models import Card
from models.rarity_models import Rarity


def _parse_iso(dt_str: str | None) -> datetime | None:
    """Parse ISO datetime string with Z suffix into aware UTC datetime."""
    if not dt_str:
        return None
    try:
        # Normalize trailing Z to +00:00
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _build_template_index(templates: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], str]:
    """Build index (token_symbol, design_type, rarity) -> template URL."""
    index: Dict[Tuple[str, str, str], str] = {}
    for t in templates:
        symbol = str(t.get("token_symbol", "")).upper()
        design = str(t.get("design_type", "")).lower()
        rarity = str(t.get("rarity", "")).lower()
        url = t.get("url")
        if not symbol or not design or not rarity or not url:
            continue
        key = (symbol, design, rarity)
        index[key] = str(url)
    return index


async def _ensure_rarities_from_cards(
    cards: List[Dict[str, Any]], db: AsyncSession
) -> None:
    """Ensure rarities referenced in cards exist in DB with the same ids.

    For each unique (rarity_id, rarity_name, rarity_color) in JSON:
    - If a rarity with that id exists, it is left as-is.
    - If not, a new Rarity is created with that explicit id.
    """
    seen: Dict[int, Tuple[str, str]] = {}
    for c in cards:
        try:
            rid = int(c["rarity_id"])
        except KeyError:
            continue
        name = str(c.get("rarity_name") or "").strip()
        color = str(c.get("rarity_color") or "#000000").strip() or "#000000"
        if rid not in seen:
            seen[rid] = (name, color)

    if not seen:
        return

    # Load existing rarities
    result = await db.execute(select(Rarity.id))
    existing_ids = {row[0] for row in result.fetchall()}

    created = 0
    for rid, (name, color) in sorted(seen.items(), key=lambda x: x[0]):
        if rid in existing_ids:
            continue
        if not name:
            name = f"rarity_{rid}"
        desc = f"{name.capitalize()} rarity imported from JSON"
        rarity = Rarity(
            id=rid,
            name=name,
            description=desc,
            score_bonus=1,
            color=color,
            is_active=True,
        )
        db.add(rarity)
        created += 1

    if created:
        await db.flush()
        # Align sequence
        await db.execute(
            text(
                "SELECT setval("
                "  pg_get_serial_sequence('rarities', 'id'),"
                "  COALESCE((SELECT MAX(id) FROM rarities), 1)"
                ")"
            )
        )
        print(f"[seed_cards_from_json] Created {created} missing rarities.")


async def _upsert_cards_from_items(
    items: List[Dict[str, Any]],
    template_index: Dict[Tuple[str, str, str], str],
    db: AsyncSession,
) -> None:
    """Insert or update cards from JSON."""
    created = 0
    updated = 0

    # Optionally clear existing cards before import (fresh environment).
    await db.execute(text("DELETE FROM cards"))

    for raw in items:
        try:
            card_id = int(raw["id"])
            token_id = int(raw["token_id"])
            rarity_id = int(raw["rarity_id"])
            design_type = str(raw.get("design_type") or "classic")
            original_template_url = str(raw.get("template_image_url") or "")
            is_active = bool(raw.get("is_active", True))

            token_symbol = str(raw.get("token_symbol", "")).upper()
            rarity_name = str(raw.get("rarity_name", "")).lower() or "common"
        except KeyError as exc:
            print(f"[seed_cards_from_json] Skipping card without required field {exc}: {raw}")
            continue

        # Choose template URL: prefer new R2 URL if we have a match.
        key = (token_symbol, design_type.lower(), rarity_name)
        template_url = template_index.get(key, original_template_url)
        if not template_url:
            # As a last resort, fall back to placeholder-like URL from JSON or skip.
            print(
                f"[seed_cards_from_json] No template URL for card id={card_id}, "
                f"token_symbol={token_symbol}, rarity={rarity_name}; keeping empty."
            )

        # We ignore rendered_image_url from JSON so that render job can regenerate.
        created_at = _parse_iso(raw.get("created_at")) or datetime.now(timezone.utc)
        updated_at = _parse_iso(raw.get("updated_at")) or created_at

        result = await db.execute(select(Card).where(Card.id == card_id))
        card: Card | None = result.scalar_one_or_none()

        if card is None:
            card = Card(
                id=card_id,
                token_id=token_id,
                rarity_id=rarity_id,
                design_type=design_type,
                template_image_url=template_url,
                rendered_image_url=None,
                last_rendered_at=None,
                is_active=is_active,
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(card)
            created += 1
        else:
            card.token_id = token_id
            card.rarity_id = rarity_id
            card.design_type = design_type
            card.template_image_url = template_url
            card.rendered_image_url = None
            card.last_rendered_at = None
            card.is_active = is_active
            card.created_at = created_at
            card.updated_at = updated_at
            updated += 1

    # Align sequence for cards.id
    await db.execute(
        text(
            "SELECT setval("
            "  pg_get_serial_sequence('cards', 'id'),"
            "  COALESCE((SELECT MAX(id) FROM cards), 1)"
            ")"
        )
    )
    await db.flush()
    print(f"[seed_cards_from_json] Cards upserted. Created: {created}, Updated: {updated}")


async def seed_from_files(cards_path: str, templates_path: str) -> None:
    """Seed cards table from cards and template JSON files."""
    if not os.path.exists(cards_path):
        raise FileNotFoundError(f"cards JSON file not found: {cards_path}")
    if not os.path.exists(templates_path):
        raise FileNotFoundError(f"templates JSON file not found: {templates_path}")

    with open(cards_path, "r", encoding="utf-8") as f:
        cards_data = json.load(f)
    with open(templates_path, "r", encoding="utf-8") as f:
        templates_data = json.load(f)

    items = cards_data.get("items") or []
    if not isinstance(items, list):
        raise ValueError("cards JSON must contain 'items' array")

    templates = templates_data.get("templates") or []
    if not isinstance(templates, list):
        raise ValueError("templates JSON must contain 'templates' array")

    print(f"[seed_cards_from_json] Loaded {len(items)} cards and {len(templates)} templates.")

    template_index = _build_template_index(templates)
    print(f"[seed_cards_from_json] Built template index with {len(template_index)} keys.")

    await init_database()
    async with AsyncSessionLocal() as db:
        # Ensure rarities exist with correct ids.
        await _ensure_rarities_from_cards(items, db)
        # Upsert cards.
        await _upsert_cards_from_items(items, template_index, db)
        await db.commit()

    print("[seed_cards_from_json] Done.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.seed_cards_from_json data/cards.json data/card_templates.json")
        sys.exit(1)

    cards_json_path = sys.argv[1]
    templates_json_path = sys.argv[2]
    asyncio.run(seed_from_files(cards_json_path, templates_json_path))

