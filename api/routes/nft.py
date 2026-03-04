"""
ERC-721 metadata endpoint for HodleagueCards tokenURI.
Contract base URL: https://api.hodleague.com/nft/cards/
"""

import logging

from fastapi import APIRouter, HTTPException, status, Depends

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from models.database import get_async_db
from models.user_card_models import UserCard
from models.card_models import Card
from models.token_models import Token
from models.rarity_models import Rarity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nft", tags=["NFT Metadata"])


class NFTAttribute(BaseModel):
    trait_type: str
    value: str


class ERC721MetadataResponse(BaseModel):
    """ERC-721 metadata standard for tokenURI."""

    name: str
    description: str
    image: str
    attributes: list[NFTAttribute]


@router.get(
    "/cards/{token_id}",
    response_model=ERC721MetadataResponse,
    summary="ERC-721 card metadata",
    description="Returns JSON metadata for HodleagueCards tokenURI (marketplaces, wallets).",
)
async def get_card_metadata(
    token_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Lookup UserCard by nft_token_id (on-chain token ID), join Card, Token, Rarity.
    Returns standard ERC-721 metadata: name, description, image, attributes.
    """
    result = await db.execute(
        select(UserCard, Card, Token, Rarity)
        .join(Card, UserCard.card_id == Card.id)
        .join(Token, Card.token_id == Token.id)
        .join(Rarity, Card.rarity_id == Rarity.id)
        .where(UserCard.nft_token_id == token_id)
        .limit(1)
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    user_card, card, token, rarity = row
    image_url = card.rendered_image_url or token.image_url or ""

    return ERC721MetadataResponse(
        name=f"{token.symbol} #{token_id}",
        description=f"Hodleague fantasy card: {token.name} ({token.symbol}), {rarity.name} rarity.",
        image=image_url,
        attributes=[
            NFTAttribute(trait_type="Token", value=token.symbol),
            NFTAttribute(trait_type="Rarity", value=rarity.name),
            NFTAttribute(trait_type="Design", value=card.design_type),
        ],
    )
