# api/routes/cards.py

from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
from models.database import get_async_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ==================== Pydantic Schemas ====================

class CardBase(BaseModel):
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    token_weight: int
    rarity_name: str
    rarity_color: str
    rarity_score_bonus: int
    design_type: str
    background_image_url: str
    current_price: Optional[float]
    market_cap: Optional[int]
    change_24h: Optional[float]
    calculated_score: float

class CardCatalogResponse(BaseModel):
    total: int
    cards: List[CardBase]

class CardStats(BaseModel):
    total_owned: int
    unique_owners: int

class CardDetailResponse(CardBase):
    stats: CardStats

# ==================== Routes ====================

@router.get(
    "/cards",
    response_model=CardCatalogResponse,
    summary="Get all available cards",
    description="Get catalog of all active cards with optional filters by rarity and token"
)
async def get_cards_catalog(
    rarity: Optional[str] = Query(None, description="Filter by rarity (common, rare, epic, legendary)"),
    token_symbol: Optional[str] = Query(None, description="Filter by token symbol (BTC, ETH, etc.)"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all available cards in the game
    
    - **rarity**: Optional filter by rarity name
    - **token_symbol**: Optional filter by token symbol
    """
    try:
        # Build query with optional filters
        query = """
            SELECT DISTINCT ON (card_id)
                card_id,
                token_symbol,
                token_name,
                token_image_url,
                token_weight,
                rarity_name,
                rarity_color,
                rarity_score_bonus,
                design_type,
                background_image_url,
                current_price,
                market_cap,
                change_24h,
                calculated_score
            FROM active_cards_with_score
            WHERE is_active = true
        """
        
        params = {}
        
        if rarity:
            query += " AND LOWER(rarity_name) = LOWER(:rarity)"
            params["rarity"] = rarity
        
        if token_symbol:
            query += " AND LOWER(token_symbol) = LOWER(:token_symbol)"
            params["token_symbol"] = token_symbol
        
        query += " ORDER BY card_id, rarity_name DESC, token_symbol ASC"
        
        result = await db.execute(text(query), params)
        rows = result.fetchall()
        
        cards = []
        for row in rows:
            card_data = {
                "card_id": row.card_id,
                "token_symbol": row.token_symbol,
                "token_name": row.token_name,
                "token_image_url": row.token_image_url,
                "token_weight": row.token_weight,
                "rarity_name": row.rarity_name,
                "rarity_color": row.rarity_color,
                "rarity_score_bonus": row.rarity_score_bonus,
                "design_type": row.design_type,
                "background_image_url": row.background_image_url,
                "current_price": float(row.current_price) if row.current_price else None,
                "market_cap": int(row.market_cap) if row.market_cap else None,
                "change_24h": float(row.change_24h) if row.change_24h else None,
                "calculated_score": float(row.calculated_score) if row.calculated_score else 0.0
            }
            cards.append(card_data)
        
        return CardCatalogResponse(
            total=len(cards),
            cards=cards
        )
        
    except Exception as e:
        logger.error(f"Error fetching cards catalog: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cards catalog"
        )


@router.get(
    "/cards/{card_id}",
    response_model=CardDetailResponse,
    summary="Get card details",
    description="Get detailed information about a specific card including ownership statistics"
)
async def get_card_details(
    card_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed card information by ID
    
    - **card_id**: Card ID from the database
    """
    try:
        # Get card details from materialized view
        card_query = text("""
            SELECT 
                card_id,
                token_symbol,
                token_name,
                token_image_url,
                token_weight,
                rarity_name,
                rarity_color,
                rarity_score_bonus,
                design_type,
                background_image_url,
                current_price,
                market_cap,
                change_24h,
                calculated_score
            FROM active_cards_with_score
            WHERE card_id = :card_id
              AND is_active = true
            LIMIT 1
        """)
        
        card_result = await db.execute(card_query, {"card_id": card_id})
        card_row = card_result.fetchone()
        
        if not card_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Card with ID {card_id} not found"
            )
        
        # Get ownership statistics
        stats_query = text("""
            SELECT 
                COUNT(id) as total_owned,
                COUNT(DISTINCT user_id) as unique_owners
            FROM user_cards
            WHERE card_id = :card_id
              AND is_active = true
        """)
        
        stats_result = await db.execute(stats_query, {"card_id": card_id})
        stats_row = stats_result.fetchone()
        
        # Build response
        card_data = {
            "card_id": card_row.card_id,
            "token_symbol": card_row.token_symbol,
            "token_name": card_row.token_name,
            "token_image_url": card_row.token_image_url,
            "token_weight": card_row.token_weight,
            "rarity_name": card_row.rarity_name,
            "rarity_color": card_row.rarity_color,
            "rarity_score_bonus": card_row.rarity_score_bonus,
            "design_type": card_row.design_type,
            "background_image_url": card_row.background_image_url,
            "current_price": float(card_row.current_price) if card_row.current_price else None,
            "market_cap": int(card_row.market_cap) if card_row.market_cap else None,
            "change_24h": float(card_row.change_24h) if card_row.change_24h else None,
            "calculated_score": float(card_row.calculated_score) if card_row.calculated_score else 0.0,
            "stats": {
                "total_owned": stats_row.total_owned if stats_row else 0,
                "unique_owners": stats_row.unique_owners if stats_row else 0
            }
        }
        
        return CardDetailResponse(**card_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching card details for card_id {card_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve card details"
        )