# api/routes/tokens.py
from fastapi import APIRouter, HTTPException, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging

from services.coinmarketcap_service import CoinMarketCapService
from data.game_tokens import get_token_weight, validate_deck_weight, get_weight_distribution

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Initialize services
cmc_service = CoinMarketCapService()

# Pydantic models
class TokenResponse(BaseModel):
    """Token data model for API responses"""
    id: str
    name: str
    symbol: str
    price: float
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    percent_change_1h: Optional[float] = None
    percent_change_24h: Optional[float] = None
    percent_change_7d: Optional[float] = None
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    cmc_rank: Optional[int] = None
    last_updated: Optional[str] = None
    is_game_token: Optional[bool] = None
    weight: Optional[float] = None

class TokenListResponse(BaseModel):
    """Response model for token list endpoints"""
    success: bool
    data: Dict[str, Any]
    message: Optional[str] = None

class TokenDetailResponse(BaseModel):
    """Response model for single token details"""
    success: bool
    data: TokenResponse
    message: Optional[str] = None

class TokenStatsResponse(BaseModel):
    """Response model for token statistics"""
    success: bool
    data: Dict[str, Any]
    message: Optional[str] = None


@router.get("/tokens", 
           response_model=TokenListResponse,
           summary="Get game tokens",
           description="Get all available game tokens")
async def get_tokens():
    """Get all available game tokens"""
    try:
        # Get game tokens that are available in current top-100
        available_tokens = cmc_service.get_available_game_tokens()
        
        if not available_tokens:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No tokens available - Could not fetch token data from CoinMarketCap"
            )

        return TokenListResponse(
            success=True,
            data={
                "tokens": available_tokens,
                "total_count": len(available_tokens),
                "last_updated": datetime.utcnow().isoformat()
            },
            message=f"Successfully retrieved {len(available_tokens)} available tokens"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/tokens/{symbol}",
           response_model=TokenDetailResponse,
           summary="Get token details", 
           description="Get detailed information about a specific token")
async def get_token_details(symbol: str):
    """Get detailed information about a specific token"""
    try:
        symbol = symbol.upper()
        
        # Get all available tokens and find the requested one
        available_tokens = cmc_service.get_available_game_tokens()
        token = next((t for t in available_tokens if t['symbol'] == symbol), None)
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Token {symbol} not found in available game tokens"
            )

        return TokenDetailResponse(
            success=True,
            data=token,
            message=f"Successfully retrieved details for {symbol}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_token_details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/simulation-tokens",
           response_model=TokenListResponse,
           summary="Get simulation tokens",
           description="Get all 100 tokens used for simulation calculations")
async def get_simulation_tokens():
    """Get all 100 tokens used for simulation calculations"""
    try:
        # Get simulation tokens (100 total, includes 30 game tokens + 70 others)
        simulation_tokens = cmc_service.get_simulation_tokens()
        
        if not simulation_tokens:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No simulation tokens available - Could not fetch simulation token data from CoinMarketCap"
            )

        # Separate stats
        game_tokens_count = len([t for t in simulation_tokens if t['is_game_token']])
        other_tokens_count = len(simulation_tokens) - game_tokens_count

        return TokenListResponse(
            success=True,
            data={
                "tokens": simulation_tokens,
                "total_count": len(simulation_tokens),
                "game_tokens_count": game_tokens_count,
                "other_tokens_count": other_tokens_count,
                "last_updated": datetime.utcnow().isoformat()
            },
            message=f"Successfully retrieved {len(simulation_tokens)} simulation tokens ({game_tokens_count} game + {other_tokens_count} others)"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_simulation_tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/tokens-stats",
           response_model=TokenStatsResponse,
           summary="Get tokens statistics",
           description="Get statistics about available tokens")
async def get_tokens_stats():
    """Get statistics about available tokens"""
    try:
        game_tokens, simulation_tokens = cmc_service.get_all_tokens_data()
        
        stats = {
            "game_tokens": {
                "count": len(game_tokens),
                "target": 30
            },
            "simulation_tokens": {
                "count": len(simulation_tokens),
                "target": 100,
                "game_tokens_included": len([t for t in simulation_tokens if t['is_game_token']]),
                "other_tokens_included": len([t for t in simulation_tokens if not t['is_game_token']])
            },
            "last_updated": datetime.utcnow().isoformat()
        }

        return TokenStatsResponse(
            success=True,
            data=stats,
            message="Successfully retrieved token statistics"
        )

    except Exception as e:
        logger.error(f"Error in get_tokens_stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )