# api/routes/tokens.py
"""Public API: list tokens with current price (no auth required)."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_async_db
from models.token_models import Token, TokenPrice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tokens")

# ==================== Schemas ====================


class TokenCurrentPrice(BaseModel):
    """Latest price snapshot for a token."""

    price: float
    market_cap: Optional[int] = None
    change_24h: Optional[float] = None
    price_timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenScoreFromView(BaseModel):
    """Score from materialized view active_cards_with_score (current tournament)."""

    calculated_score: float
    tournament_change: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class TokenWithPriceResponse(BaseModel):
    """Token with full info and current rate."""

    id: int
    name: str
    symbol: str
    weight: int
    image_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    current_price: Optional[TokenCurrentPrice] = None
    score: Optional[TokenScoreFromView] = None

    model_config = ConfigDict(from_attributes=True)


# ==================== Routes ====================


@router.get(
    "/",
    summary="List tokens with current rate",
    description="Returns all tokens with full info, latest price, and score from materialized view (calculated_score, tournament_change). Supports pagination.",
)
async def list_tokens_with_prices(
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
    is_active: Optional[bool] = Query(
        default=True,
        description="Filter by is_active. Omit or true = active only, false = inactive only.",
    ),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get list of tokens with all information and current rate for each.
    Uses latest record from token_prices per token.
    """
    # Base: all tokens (optional filter by is_active)
    base = select(Token)
    if is_active is not None:
        base = base.where(Token.is_active == is_active)

    # Count total
    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one() or 0

    # Load tokens and join latest TokenPrice (optional: token may have no prices yet)
    tokens_stmt = (
        base.order_by(Token.symbol.asc()).limit(limit).offset(offset)
    )
    tokens_result = await db.execute(tokens_stmt)
    tokens = list(tokens_result.scalars().all())

    if not tokens:
        return {
            "success": True,
            "data": [],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }

    token_ids = [t.id for t in tokens]
    latest_price_subq_filtered = (
        select(
            TokenPrice.token_id,
            func.max(TokenPrice.timestamp).label("max_timestamp"),
        )
        .where(TokenPrice.token_id.in_(token_ids))
        .group_by(TokenPrice.token_id)
        .subquery()
    )

    prices_stmt = (
        select(TokenPrice)
        .join(
            latest_price_subq_filtered,
            and_(
                TokenPrice.token_id == latest_price_subq_filtered.c.token_id,
                TokenPrice.timestamp == latest_price_subq_filtered.c.max_timestamp,
            ),
        )
        .where(TokenPrice.token_id.in_(token_ids))
    )
    prices_result = await db.execute(prices_stmt)
    prices_rows = prices_result.scalars().all()
    price_by_token_id = {p.token_id: p for p in prices_rows}

    # Scores from materialized view active_cards_with_score (one row per token, max score)
    scores_result = await db.execute(
        text("""
            SELECT token_id,
                   MAX(calculated_score) AS calculated_score,
                   MAX(tournament_change) AS tournament_change
            FROM active_cards_with_score
            WHERE token_id = ANY(:token_ids)
            GROUP BY token_id
        """),
        {"token_ids": token_ids},
    )
    scores_rows = scores_result.fetchall()
    score_by_token_id = {
        row.token_id: {
            "calculated_score": float(row.calculated_score) if row.calculated_score is not None else 0.0,
            "tournament_change": float(row.tournament_change) if row.tournament_change is not None else None,
        }
        for row in scores_rows
    }

    data = []
    for t in tokens:
        price = price_by_token_id.get(t.id)
        current = None
        if price is not None:
            current = TokenCurrentPrice(
                price=float(price.price),
                market_cap=int(price.market_cap) if price.market_cap is not None else None,
                change_24h=float(price.change_24h) if price.change_24h is not None else None,
                price_timestamp=price.timestamp,
            )
        score_data = score_by_token_id.get(t.id)
        score = None
        if score_data is not None:
            score = TokenScoreFromView(
                calculated_score=score_data["calculated_score"],
                tournament_change=score_data["tournament_change"],
            )

        data.append(
            {
                "id": t.id,
                "name": t.name,
                "symbol": t.symbol,
                "weight": t.weight,
                "image_url": t.image_url,
                "is_active": t.is_active,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "current_price": current,
                "score": score,
            }
        )

    return {
        "success": True,
        "data": data,
        "pagination": {"limit": limit, "offset": offset, "total": total},
    }
