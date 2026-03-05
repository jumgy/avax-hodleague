# api/routes/packs.py

from fastapi import APIRouter, HTTPException, Request, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from models.database import get_async_db
from models.pack_models import PackType
import secrets

from services.pack_opening_service import pack_opening_service
from services.pack_mint_service import get_on_chain_pack_balance
from services.blockchain_event_listener import confirm_pack_opening_by_tx_hash
from api.routes.auth import verify_jwt_dependency
from config import Config
from utils.rate_limit import limiter
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ==================== Pydantic Schemas ====================

class PackTypeDetail(BaseModel):
    pack_type_id: int
    name: str
    description: str
    image_url: str
    header_image_url: str
    cards_per_pack: int
    price: float
    currency: str
    supply: Optional[int]
    available_from: Optional[str]
    available_until: Optional[str]
    is_active: bool
    count: int  # Count owned by user

class AvailablePacksResponse(BaseModel):
    available_packs: int
    pack_types: List[PackTypeDetail]

class PrepareOpenRequest(BaseModel):
    user_pack_id: int
    client_seed: str  # hex-encoded 32 bytes


class PrepareOpenResponse(BaseModel):
    pack_opening_id: int
    user_pack_id: int
    card_ids: List[int]
    server_seed: str
    server_seed_hash: str
    client_seed: str
    combined_hash: str
    signature: str


class PackOpeningStatusResponse(BaseModel):
    pack_opening_id: int
    status: str  # pending_mint | completed | failed
    card_ids: Optional[List[int]] = None
    nft_token_ids: Optional[List[int]] = None


class ConfirmOpenRequest(BaseModel):
    tx_hash: str  # 0x-prefixed or raw hex


class CardReceived(BaseModel):
    user_card_id: int
    card_id: int
    token_symbol: str
    token_name: str
    token_image_url: str
    rarity_name: str
    rarity_color: str
    design_type: str
    rendered_image_url: str

class OpenPackResponse(BaseModel):
    pack_opening_id: int
    pack_type_name: str
    opened_at: str
    cards_received: List[CardReceived]


class ConfirmOpenResponse(BaseModel):
    """On success, returns full opening so the client does not need a separate GET."""
    status: str  # "completed"
    pack_opening_id: int
    pack_type_name: str
    opened_at: str
    cards_received: List[CardReceived]
    nft_token_ids: Optional[List[int]] = None


class PackHistoryItem(BaseModel):
    pack_opening_id: int
    pack_type_name: str
    opened_at: str
    cards_count: int
    cards_received: List[CardReceived]

class PackHistoryResponse(BaseModel):
    total: int
    openings: List[PackHistoryItem]

# ==================== Routes ====================

@router.get(
    "/packs/available",
    response_model=AvailablePacksResponse,
    summary="Get available packs",
    description="Get number of unopened packs for authenticated user with full pack details"
)
async def get_available_packs(
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get available packs for current user with full pack type information
    Requires JWT authentication
    """
    try:
        user_id = current_user["user_id"]
        wallet_address = current_user.get("wallet_address", "")

        # Get off-chain pack counts (UserPack, unopened)
        availability = await pack_opening_service.check_pack_availability(
            user_id=user_id,
            pack_type_id=None,
            db=db
        )

        # Fetch all active pack types
        result = await db.execute(
            select(PackType).where(PackType.is_active == True)
        )
        pack_types = result.scalars().all()

        # Merge off-chain counts with on-chain balanceOf for each pack type
        pack_details = []
        total_available = 0
        for pack_type in pack_types:
            off_chain_count = availability["by_type"].get(pack_type.id, 0)
            on_chain_count = 0
            if Config.PACKS_CONTRACT_ADDRESS and wallet_address:
                balance = await get_on_chain_pack_balance(wallet_address, pack_type.id)
                on_chain_count = balance or 0
            count = off_chain_count + on_chain_count
            if count <= 0:
                continue
            total_available += count
            
            pack_details.append(PackTypeDetail(
                pack_type_id=pack_type.id,
                name=pack_type.name,
                description=pack_type.description,
                image_url=pack_type.image_url,
                header_image_url=pack_type.header_image_url,
                cards_per_pack=pack_type.cards_per_pack,
                price=float(pack_type.price),
                currency=pack_type.currency,
                supply=pack_type.supply,
                available_from=pack_type.available_from.isoformat() if pack_type.available_from else None,
                available_until=pack_type.available_until.isoformat() if pack_type.available_until else None,
                is_active=pack_type.is_active,
                count=count
            ))

        # Sort by pack_type_id
        pack_details.sort(key=lambda x: x.pack_type_id)

        return AvailablePacksResponse(
            available_packs=total_available,
            pack_types=pack_details
        )
        
    except Exception as e:
        logger.error(f"Error getting available packs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available packs"
        )


@router.post(
    "/packs/prepare-open",
    response_model=PrepareOpenResponse,
    summary="Prepare off-chain pack opening (single on-chain mintWithSignature)",
    description="Prepare opening of an off-chain pack: generate server_seed and card_ids, sign payload for HodleagueCards.mintWithSignature.",
)
@limiter.limit("30/minute")
async def prepare_open_pack(
    request: Request,
    body: PrepareOpenRequest,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Off-chain packs flow:
      - Verifies that the given UserPack belongs to the user and is not opened.
      - If PackOpening already exists for this pack, returns the same data (no reroll).
      - Otherwise generates server_seed, derives card_ids deterministically using client_seed,
        signs payload for HodleagueCards.mintWithSignature and persists PackOpening with status=prepared.
    """
    try:
        user_id = current_user["user_id"]
        wallet_address = current_user.get("wallet_address", "")
        if not wallet_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wallet address not in session",
            )
        # client_seed expected as hex string (64 chars, 32 bytes).
        client_seed_hex = body.client_seed.strip().lower()
        if client_seed_hex.startswith("0x"):
            client_seed_hex = client_seed_hex[2:]
        try:
            client_seed = bytes.fromhex(client_seed_hex)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="client_seed must be a 32-byte hex string",
            )

        result = await pack_opening_service.prepare_open_offchain(
            user_id=user_id,
            wallet_address=wallet_address,
            user_pack_id=body.user_pack_id,
            client_seed=client_seed,
            db=db,
        )
        await db.commit()
        return PrepareOpenResponse(**result)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error("Prepare-open failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare pack open",
        )


@router.get(
    "/packs/openings/{pack_opening_id}/status",
    response_model=PackOpeningStatusResponse,
    summary="Get pack opening status",
    description="Poll until event listener marks on-chain opening as completed",
)
async def get_pack_opening_status(
    pack_opening_id: int,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db),
):
    """Return status of a pack opening (pending_mint / completed / failed)."""
    try:
        user_id = current_user["user_id"]
        result = await pack_opening_service.get_pack_opening_status(
            pack_opening_id=pack_opening_id,
            user_id=user_id,
            db=db,
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pack opening not found or access denied",
            )
        return PackOpeningStatusResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get opening status failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get status",
        )


@router.post(
    "/packs/openings/{pack_opening_id}/confirm",
    response_model=ConfirmOpenResponse,
    summary="Confirm card mint by tx hash",
    description="After submitting mintWithSignature tx, send tx_hash. On success returns full opening with cards (no extra GET needed).",
)
@limiter.limit("30/minute")
async def confirm_pack_open(
    request: Request,
    pack_opening_id: int,
    body: ConfirmOpenRequest,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db),
):
    """Confirm on-chain mintWithSignature by transaction hash; creates UserCards. Returns full opening with cards_received."""
    try:
        user_id = current_user["user_id"]
        ownership = await pack_opening_service.get_pack_opening_status(
            pack_opening_id=pack_opening_id,
            user_id=user_id,
            db=db,
        )
        if not ownership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pack opening not found or access denied",
            )
        outcome = await confirm_pack_opening_by_tx_hash(
            tx_hash=body.tx_hash.strip(),
            pack_opening_id=pack_opening_id,
            db=db,
        )
        if outcome == "not_found":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction not found or no PackOpened event in receipt",
            )
        if outcome == "mismatch":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction does not match this pack opening (user or opening_id)",
            )
        await db.commit()
        full = await pack_opening_service.get_pack_opening_by_id(
            pack_opening_id=pack_opening_id,
            user_id=user_id,
            db=db,
        )
        if not full:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Opening confirmed but failed to load result",
            )
        status_result = await pack_opening_service.get_pack_opening_status(
            pack_opening_id=pack_opening_id,
            user_id=user_id,
            db=db,
        )
        return ConfirmOpenResponse(
            status="completed",
            pack_opening_id=full["pack_opening_id"],
            pack_type_name=full["pack_type_name"],
            opened_at=full["opened_at"],
            cards_received=full["cards_received"],
            nft_token_ids=status_result.get("nft_token_ids"),
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Confirm pack open failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm pack open",
        )


@router.get(
    "/packs/openings/{pack_opening_id}",
    response_model=OpenPackResponse,
    summary="Get specific pack opening",
    description="Get details of a specific pack opening by ID"
)
async def get_pack_opening(
    pack_opening_id: int,
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get specific pack opening details with cards received
    Requires JWT authentication
    - **pack_opening_id**: ID of the pack opening to retrieve
    """
    try:
        user_id = current_user["user_id"]
        
        result = await pack_opening_service.get_pack_opening_by_id(
            pack_opening_id=pack_opening_id,
            user_id=user_id,
            db=db
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pack opening not found or access denied"
            )
        
        return OpenPackResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pack opening {pack_opening_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pack opening"
        )


@router.get(
    "/packs/history",
    response_model=PackHistoryResponse,
    summary="Get pack opening history",
    description="Get history of all opened packs for authenticated user with cards received"
)
async def get_pack_history(
    limit: int = Query(20, ge=1, le=100, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: dict = Depends(verify_jwt_dependency),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get pack opening history
    Requires JWT authentication
    
    - **limit**: Number of records (1-100)
    - **offset**: Pagination offset
    """
    try:
        user_id = current_user["user_id"]
        
        history = await pack_opening_service.get_pack_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            db=db
        )
        
        return PackHistoryResponse(**history)
        
    except Exception as e:
        logger.error(f"Error getting pack history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pack history"
        )