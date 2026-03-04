# services/user_pack_grant_service.py
import logging
from typing import List
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from models.database import DatabaseSession
from models.pack_models import PackType
from models.user_pack_models import UserPack, PackSource
from models.user_models import User

logger = logging.getLogger(__name__)


class UserPackGrantService:
    """Service for granting all available pack types to a user."""

    STARTER_PACKS_PER_TYPE: int = 3

    def __init__(self):
        self.db_session = None

    async def grant_all_active_packs_to_user(
        self, 
        user_id: int, 
        source: str = PackSource.ADMIN
    ) -> List[UserPack]:
        """Grant user all active pack types from the database.

        Args:
            user_id: User ID.
            source: Pack source (ADMIN, REWARD, PURCHASE).

        Returns:
            List of created UserPack records.
        """
        async with DatabaseSession() as session:
            try:
                # Check user exists
                user_query = select(User).where(User.id == user_id)
                result = await session.execute(user_query)
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.error(f"User with id {user_id} not found")
                    raise ValueError(f"User with id {user_id} not found")
                
                # Get all active pack types
                active_packs_query = select(PackType).where(PackType.is_active == True)
                result = await session.execute(active_packs_query)
                active_pack_types = result.scalars().all()
                
                if not active_pack_types:
                    logger.info("No active pack types found in database")
                    return []
                
                # Create new UserPack records
                new_user_packs = []
                for pack_type in active_pack_types:
                    for _ in range(self.STARTER_PACKS_PER_TYPE):
                        user_pack = UserPack(
                            user_id=user_id,
                            pack_type_id=pack_type.id,
                            obtained_at=datetime.utcnow(),
                            expires_at=None,
                            is_opened=False,
                            source=source
                        )
                        new_user_packs.append(user_pack)
                        session.add(user_pack)
                
                # Flush to get IDs
                await session.flush()
                
                logger.info(
                    f"Successfully granted {len(new_user_packs)} new packs to user {user_id}"
                )
                
                return new_user_packs
                
            except IntegrityError as e:
                logger.error(f"Database integrity error when granting packs to user {user_id}: {e}")
                raise ValueError("Error creating user packs - database integrity error")
            except Exception as e:
                logger.error(f"Error granting packs to user {user_id}: {e}")
                raise


user_pack_grant_service = UserPackGrantService()