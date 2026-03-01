import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from models.database import DatabaseSession 
from models.card_models import Card
from models.user_card_models import UserCard, UserCardSource
from models.user_models import User

logger = logging.getLogger(__name__)

class UserCardGrantService:
    """Service for granting all available cards to a user."""

    def __init__(self):
        self.db_session = None

    async def grant_all_active_cards_to_user(self, user_id: int, source: str = UserCardSource.ADMIN) -> List[UserCard]:
        """Grant user all active cards from the database."""
        async with DatabaseSession() as session:
            try:
                # Check user exists
                user_query = select(User).where(User.id == user_id)
                result = await session.execute(user_query)
                user = result.scalar_one_or_none()

                if not user:
                    logger.error(f"User with id {user_id} not found")
                    raise ValueError(f"User with id {user_id} not found")

                active_cards_query = select(Card).where(Card.is_active == True)
                result = await session.execute(active_cards_query)
                active_cards = result.scalars().all()

                if not active_cards:
                    logger.info("No active cards found in database")
                    return []

                # Get cards user already has
                existing_user_cards_query = select(UserCard.card_id).where(
                    UserCard.user_id == user_id,
                    UserCard.is_active == True
                )
                result = await session.execute(existing_user_cards_query)
                existing_card_ids = {card_id for card_id in result.scalars().all()}

                # Cards the user does not have yet.
                cards_to_grant = [
                    card for card in active_cards 
                    if card.id not in existing_card_ids
                ]

                if not cards_to_grant:
                    logger.info(f"User {user_id} already has all available active cards")
                    return []

                # Create new UserCard records
                new_user_cards = []
                for card in cards_to_grant:
                    user_card = UserCard(
                        user_id=user_id,
                        card_id=card.id,
                        obtained_at=datetime.utcnow(),
                        source=source,
                        status="available"
                    )
                    new_user_cards.append(user_card)
                    session.add(user_card)

                # Flush to get IDs
                await session.flush()
                
                logger.info(f"Successfully granted {len(new_user_cards)} new cards to user {user_id}")
                
                return new_user_cards

            except IntegrityError as e:
                logger.error(f"Database integrity error when granting cards to user {user_id}: {e}")
                raise ValueError("Error creating user cards - possible duplicate")
            except Exception as e:
                logger.error(f"Error granting cards to user {user_id}: {e}")
                raise

    async def get_user_cards_with_details(self, user_id: int) -> List[dict]:
        """Get all user cards with full details.

        Args:
            user_id: User ID.

        Returns:
            List of card dicts with full info.
        """
        async with DatabaseSession() as session:
            try:
                # Use joinedload to fetch related data in one query.
                from sqlalchemy.orm import joinedload
                
                query = select(UserCard).options(
                    joinedload(UserCard.card)
                ).where(
                    UserCard.user_id == user_id,
                    UserCard.is_active == True
                ).join(Card).where(Card.is_active == True)

                result = await session.execute(query)
                user_cards = result.unique().scalars().all()

                # Build detailed card info.
                cards_info = []
                for user_card in user_cards:
                    card_info = {
                        "user_card_id": user_card.id,
                        "card_id": user_card.card_id,
                        "token_id": user_card.card.token_id,
                        "rarity_id": user_card.card.rarity_id,
                        "design_type": user_card.card.design_type,
                        "rendered_image_url": user_card.card.rendered_image_url,
                        "obtained_at": user_card.obtained_at.isoformat(),
                        "source": user_card.source,
                        "status": user_card.status
                    }
                    cards_info.append(card_info)

                logger.info(f"Retrieved {len(cards_info)} cards for user {user_id}")
                return cards_info

            except Exception as e:
                logger.error(f"Error retrieving cards for user {user_id}: {e}")
                raise

    async def get_missing_cards_for_user(self, user_id: int) -> List[Card]:
        """Get active cards the user does not have yet.

        Args:
            user_id: User ID.

        Returns:
            List of Card records the user is missing.
        """
        async with DatabaseSession() as session:
            try:
                all_active_cards_query = select(Card).where(Card.is_active == True)
                result = await session.execute(all_active_cards_query)
                all_active_cards = result.scalars().all()

                user_cards_query = select(UserCard.card_id).where(
                    UserCard.user_id == user_id,
                    UserCard.is_active == True
                )
                result = await session.execute(user_cards_query)
                user_card_ids = {card_id for card_id in result.scalars().all()}

                # Cards user does not have
                missing_cards = [
                    card for card in all_active_cards 
                    if card.id not in user_card_ids
                ]

                return missing_cards

            except Exception as e:
                logger.error(f"Error getting missing cards for user {user_id}: {e}")
                raise

    async def get_active_cards_count(self) -> int:
        """Return count of active cards in the system."""
        async with DatabaseSession() as session:
            try:
                query = select(Card).where(Card.is_active == True)
                result = await session.execute(query)
                active_cards = result.scalars().all()
                return len(active_cards)

            except Exception as e:
                logger.error(f"Error counting active cards: {e}")
                raise

user_card_grant_service = UserCardGrantService()