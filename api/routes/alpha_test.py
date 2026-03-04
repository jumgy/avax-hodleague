from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from models.database import get_async_db
from models.alpha_test_models import AlphaTestAccess
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AlphaTestAccessCheck(BaseModel):
    wallet_address: str
    has_access: bool
    added_at: str | None = None


@router.get(
    "/alpha-test/check/{wallet_address}",
    response_model=AlphaTestAccessCheck,
    summary="Check alpha test access",
    description="ALPHA TEST COMPLETED - PUBLIC ACCESS"
)
async def check_alpha_test_access(
    wallet_address: str = Path(..., description="Ethereum wallet address (0x...)")
):
    """All addresses have access (alpha test completed)"""
    wallet_address_normalized = wallet_address.strip().lower()
    
    return AlphaTestAccessCheck(
        wallet_address=wallet_address_normalized,
        has_access=True,
        added_at=datetime.utcnow().isoformat()
    )


@router.get(
    "/alpha-test/stats",
    summary="Get alpha test stats",
    description="Get public statistics about alpha test whitelist"
)
async def get_alpha_test_stats(
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get public alpha test statistics
    
    - Returns total number of whitelisted addresses
    """
    try:
        query = select(AlphaTestAccess)
        result = await db.execute(query)
        addresses = result.scalars().all()
        
        return {
            "total_whitelisted": len(addresses),
            "status": "active"
        }
            
    except Exception as e:
        logger.error(f"Error getting alpha test stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alpha test statistics"
        )