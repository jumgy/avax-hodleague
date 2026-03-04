"""
Server seed and commitment for pack opening commit-reveal.
Deterministic card selection from pack type drop table using server_seed as RNG seed.
"""

import logging
import os
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from models.card_models import Card
from models.pack_models import PackType
from models.token_models import Token

logger = logging.getLogger(__name__)


def generate_server_seed() -> bytes:
    """
    Generate a cryptographically random 32-byte server seed.
    Used for commit-reveal; same seed + same pack_type yields same card_ids.
    """
    return os.urandom(32)


def commitment_from_seed(server_seed: bytes) -> bytes:
    """
    Compute commitment = keccak256(server_seed).
    Store commitment before revealing server_seed so opening can be verified.
    """
    if len(server_seed) != 32:
        raise ValueError("server_seed must be 32 bytes")
    return Web3.keccak(server_seed)


async def get_deterministic_card_ids(
    pack_type: PackType,
    server_seed: bytes,
    db: AsyncSession,
) -> List[int]:
    """
    Deterministic card selection from pack_type.guaranteed_slots using server_seed as RNG seed.
    Same server_seed + same pack_type always produces the same card_ids (for verification).

    Args:
        pack_type: PackType with guaranteed_slots (card_pools, drop_rules).
        server_seed: 32-byte seed.
        db: Database session for symbol -> card_id lookup.

    Returns:
        List of card_ids in the same order as drop rules.
    """
    if len(server_seed) != 32:
        raise ValueError("server_seed must be 32 bytes")

    guaranteed_slots = pack_type.guaranteed_slots
    if not guaranteed_slots or not isinstance(guaranteed_slots, dict):
        raise ValueError(f"Pack type '{pack_type.name}' has no valid guaranteed_slots")
    if "card_pools" not in guaranteed_slots or "drop_rules" not in guaranteed_slots:
        raise ValueError(f"Pack type '{pack_type.name}' missing card_pools or drop_rules")

    card_pools = guaranteed_slots["card_pools"]
    drop_rules = guaranteed_slots["drop_rules"]
    rng = __rng_from_seed(server_seed)

    selected_card_ids: List[int] = []
    for category, count in drop_rules.items():
        if category not in card_pools:
            logger.warning("Category '%s' in drop_rules but not in card_pools, skipping", category)
            continue
        token_symbols = list(card_pools[category])
        if not token_symbols:
            logger.warning("Category '%s' has empty token list, skipping", category)
            continue
        if len(token_symbols) < count:
            selected_symbols = token_symbols
        else:
            selected_symbols = __sample_without_replacement(rng, token_symbols, count)
        for symbol in selected_symbols:
            card_id = await __get_card_id_by_symbol(symbol, db)
            if card_id is not None:
                selected_card_ids.append(card_id)
            else:
                logger.warning("Symbol %s not found for card_id, skipping", symbol)

    if not selected_card_ids:
        raise ValueError(
            f"Deterministic drop produced no cards for pack '{pack_type.name}'. Check token symbols."
        )
    if len(selected_card_ids) != pack_type.cards_per_pack:
        logger.warning(
            "Deterministic drop: %d cards, expected %d for pack type %s",
            len(selected_card_ids),
            pack_type.cards_per_pack,
            pack_type.name,
        )
    return selected_card_ids


def __rng_from_seed(server_seed: bytes):
    """Return a random.Random instance seeded with server_seed (32 bytes -> int)."""
    import random
    seed_int = int.from_bytes(server_seed, "big")
    return random.Random(seed_int)


def __sample_without_replacement(rng, population: list, k: int) -> list:
    """Sample k items without replacement using the given RNG (reproducible)."""
    return rng.sample(population, k)


async def __get_card_id_by_symbol(token_symbol: str, db: AsyncSession) -> int | None:
    """Resolve token symbol to active card id (one card per token)."""
    result = await db.execute(
        select(Card.id)
        .join(Token, Card.token_id == Token.id)
        .where(
            Token.symbol == token_symbol,
            Token.is_active.is_(True),
            Card.is_active.is_(True),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()
