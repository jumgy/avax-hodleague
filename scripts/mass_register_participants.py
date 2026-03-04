"""
Mass registration of fake participants for tournament testing
"""
import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import random
import logging

from models.database import AsyncSessionLocal
from models.tournament_models import Tournament
from models.tournament_deck_models import TournamentDeck
from models.user_models import User
from models.card_models import Card
from models.user_card_models import UserCard
from models.token_models import Token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_or_create_fake_user(db: AsyncSession, index: int) -> User:
    """Create or retrieve a fake user for testing."""
    nickname = f"fakeuser{index}"
    
    result = await db.execute(
        select(User).where(User.nickname == nickname)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            wallet_address=f"0x{index:040d}",  # 0x + 40 hex digits = 42 chars
            nickname=nickname,
            referral_route=f"fake{index}",
            avatar_url=f"https://i.pravatar.cc/150?u=fake{index}",
            is_active=True
        )
        db.add(user)
        await db.flush()
    
    return user


from sqlalchemy.orm import selectinload

async def get_random_cards(db: AsyncSession, count: int = 5) -> list:
    """Get random active cards."""
    result = await db.execute(
        select(Card)
        .join(Token)
        .options(selectinload(Card.token))
        .where(Token.is_active == True)
        .order_by(Card.id)
    )
    all_cards = result.scalars().all()
    
    if len(all_cards) < count:
        raise ValueError(f"Not enough active cards in DB (need {count}, found {len(all_cards)})")
    
    return random.sample(all_cards, count)


async def create_user_cards_for_user(db: AsyncSession, user: User, cards: list) -> list:
    """Create user_cards for the given user."""
    user_card_ids = []
    
    for card in cards:
        # Check if user already has this card
        existing = await db.execute(
            select(UserCard).where(
                UserCard.user_id == user.id,
                UserCard.card_id == card.id
            )
        )
        user_card = existing.scalar_one_or_none()
        
        if not user_card:
            user_card = UserCard(
                user_id=user.id,
                card_id=card.id,
                obtained_at=datetime.now(timezone.utc),
                source="admin",
                status="available"
            )
            db.add(user_card)
            await db.flush()
        
        user_card_ids.append(user_card.id)
    
    return user_card_ids


async def register_participant(db: AsyncSession, tournament_id: int, user_index: int) -> bool:
    """Register a single participant."""
    try:
        # Create or get user
        user = await get_or_create_fake_user(db, user_index)
        
        # Check if already registered
        existing_deck = await db.execute(
            select(TournamentDeck).where(
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.user_id == user.id,
                TournamentDeck.is_active == True
            )
        )
        if existing_deck.scalar_one_or_none():
            logger.info(f"  User {user_index} already registered, skipping")
            return False
        
        # Get random cards
        cards = await get_random_cards(db, count=5)
        
        # Create user_cards
        user_card_ids = await create_user_cards_for_user(db, user, cards)
        
        # Sum total weight from tokens
        total_weight = sum(card.token.weight for card in cards)

        # Create deck
        deck = TournamentDeck(
            tournament_id=tournament_id,
            user_id=user.id,
            deck_composition=user_card_ids,
            deck_hash=f"hash_{user_index}_{tournament_id}",
            total_weight=total_weight,
            is_valid=True,
            is_active=True
        )
        db.add(deck)
        
        return True
        
    except Exception as e:
        logger.error(f"Error registering user {user_index}: {e}")
        raise


async def mass_register(tournament_id: int, participants_count: int = 350):
    """Mass-register participants for a tournament."""
    async with AsyncSessionLocal() as db:
        try:
            # Check tournament
            result = await db.execute(
                select(Tournament).where(Tournament.id == tournament_id)
            )
            tournament = result.scalar_one_or_none()
            
            if not tournament:
                raise ValueError(f"Tournament {tournament_id} not found")
            
            logger.info(f"Tournament #{tournament.tournament_number} found")
            logger.info(f"Starting mass registration for {participants_count} participants...")
            
            registered = 0
            batch_size = 50  # Commit every 50 participants
            
            for i in range(1, participants_count + 1):
                success = await register_participant(db, tournament_id, i)
                
                if success:
                    registered += 1
                
                # Commit in batches
                if i % batch_size == 0:
                    await db.commit()
                    logger.info(f"Registered {registered}/{i} participants (committed)")

            await db.commit()
            logger.info(f"Total registered: {registered} participants")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Mass registration failed: {e}")
            raise


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mass_register_participants.py <tournament_id> [participants_count]")
        print("Example: python mass_register_participants.py 5 350")
        sys.exit(1)
    
    tournament_id = int(sys.argv[1])
    participants_count = int(sys.argv[2]) if len(sys.argv) > 2 else 350
    
    asyncio.run(mass_register(tournament_id, participants_count))