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
    description="Check if a wallet address has access to alpha test"
)
async def check_alpha_test_access(
    wallet_address: str = Path(..., description="Ethereum wallet address (0x...)"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Check if wallet address is whitelisted for alpha test
    
    - **wallet_address**: Ethereum wallet address (0x...)
    - Returns has_access flag and added_at date if whitelisted
    """
    try:
        # Normalize wallet address
        wallet_address_normalized = wallet_address.strip().lower()
        
        # Check if address exists in whitelist
        query = select(AlphaTestAccess).where(
            AlphaTestAccess.wallet_address == wallet_address_normalized
        )
        result = await db.execute(query)
        access = result.scalar_one_or_none()
        
        if access:
            return AlphaTestAccessCheck(
                wallet_address=access.wallet_address,
                has_access=True,
                added_at=access.created_at.isoformat()
            )
        else:
            return AlphaTestAccessCheck(
                wallet_address=wallet_address_normalized,
                has_access=False,
                added_at=None
            )
            
    except Exception as e:
        logger.error(f"Error checking alpha test access for {wallet_address}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check alpha test access"
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