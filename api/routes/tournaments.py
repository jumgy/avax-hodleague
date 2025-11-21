# api/routes/tournaments.py
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List
from pydantic import BaseModel
import logging

from data.game_tokens import get_weight_distribution

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Pydantic models
class TournamentRules(BaseModel):
    deck_size: int
    weight_limit: int
    duration_days: int

class WeightTiers(BaseModel):
    giants_80_100: Dict[str, Any]
    major_60_79: Dict[str, Any]
    mid_40_59: Dict[str, Any]
    emerging_25_39: Dict[str, Any]
    speculative_15_24: Dict[str, Any]

class TournamentInfo(BaseModel):
    tournament_id: str
    name: str
    status: str
    rules: TournamentRules
    weight_tiers: WeightTiers
    example_strategies: List[str]

class TournamentResponse(BaseModel):
    success: bool
    data: TournamentInfo
    message: str


@router.get("/tournament",
           response_model=TournamentResponse,
           summary="Get tournament info",
           description="Get current tournament information")
async def get_tournament_info():
    """Get current tournament information"""
    try:
        weight_stats = get_weight_distribution()

        tournament_info = TournamentInfo(
            tournament_id="simulation_001",
            name="Crypto Fantasy Tournament",
            status="active",
            rules=TournamentRules(
                deck_size=5,
                weight_limit=28,
                duration_days=7
            ),
            weight_tiers=WeightTiers(
                giants_80_100=weight_stats['tier_1'],
                major_60_79=weight_stats['tier_2'], 
                mid_40_59=weight_stats['tier_3'],
                emerging_25_39=weight_stats['tier_4'],
                speculative_15_24=weight_stats['tier_5']
            ),
            example_strategies=[
                "Conservative: 1 Giant + 4 Mid/Small = BTC(100) + 4x(37avg)",
                "Balanced: 2 Major + 3 Small = SOL(75) + DOGE(70) + 3x(35avg)", 
                "Risky: 5 Speculative = 5x(50avg)"
            ]
        )

        return TournamentResponse(
            success=True,
            data=tournament_info,
            message="Tournament info retrieved"
        )

    except Exception as e:
        logger.error(f"Error in get_tournament_info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )