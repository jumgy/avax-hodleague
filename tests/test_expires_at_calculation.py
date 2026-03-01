"""
Tests for expires_at calculation for cards from packs.
Checks whether expires_at depends on having a tournament with open registration.
"""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from models.tournament_models import Tournament, TournamentStatus
from models.user_card_models import UserCard


@pytest.mark.asyncio
async def test_expires_at_with_open_tournament(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Case 1: Tournament with open registration (REGISTRATION).
    expires_at must be nearest Friday 17:00 UTC (0-6 days).
    """
    # 1. Create user.
    user = await create_test_user()
    
    # 2. Create tournament in REGISTRATION status.
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(timezone.utc) + timedelta(hours=2),
        end_date=datetime.now(timezone.utc) + timedelta(days=5)
    )
    await db_session.commit()
    
    # 3. Grant pack.
    packs = await grant_pack_to_user(user.id, pack_type_id=6)
    assert len(packs) > 0
    
    # 4. Open pack.
    result = await pack_opening_service.open_pack(
        user_id=user.id,
        pack_type_id=6,
        db=db_session
    )
    await db_session.commit()
    
    # 5. Get cards.
    cards_result = await db_session.execute(
        select(UserCard)
        .where(UserCard.user_id == user.id)
        .order_by(UserCard.id.desc())
    )
    cards = cards_result.scalars().all()
    assert len(cards) > 0
    
    # 6. Check expires_at.
    now = datetime.now(timezone.utc)
    for card in cards:
        assert card.expires_at is not None
        assert card.expires_at > now
        assert card.expires_at.weekday() == 4  # Friday
        assert card.expires_at.hour == 17
        assert card.expires_at.minute == 0
        
        # Nearest Friday = 0-6 days.
        days_until_expire = (card.expires_at - now).days
        assert 0 <= days_until_expire <= 6, \
            f"REGISTRATION tournament -> nearest Friday (0-6 days), got: {days_until_expire}"
    
    print(f"[OK] REGISTRATION tournament: {len(cards)} cards, expires_at = {cards[0].expires_at}")


@pytest.mark.asyncio
async def test_expires_at_without_open_tournament(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Case 2: No tournament with open registration (ONGOING tournament).
    expires_at must be Friday next week (7-13 days).
    """
    user = await create_test_user()
    
    # Tournament already running (ONGOING).
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=4)
    )
    await db_session.commit()
    
    packs = await grant_pack_to_user(user.id, pack_type_id=6)
    result = await pack_opening_service.open_pack(
        user_id=user.id,
        pack_type_id=6,
        db=db_session
    )
    await db_session.commit()
    
    cards_result = await db_session.execute(
        select(UserCard)
        .where(UserCard.user_id == user.id)
        .order_by(UserCard.id.desc())
    )
    cards = cards_result.scalars().all()
    assert len(cards) > 0
    
    now = datetime.now(timezone.utc)
    for card in cards:
        assert card.expires_at is not None
        assert card.expires_at > now
        assert card.expires_at.weekday() == 4  # Friday
        assert card.expires_at.hour == 17
        
        # Next week = 7-13 days.
        days_until_expire = (card.expires_at - now).days
        assert 7 <= days_until_expire <= 13, \
            f"ONGOING tournament -> Friday next week (7-13 days), got: {days_until_expire}"
    
    print(f"[OK] ONGOING tournament: {len(cards)} cards, expires_at = {cards[0].expires_at} (in {days_until_expire} days)")


@pytest.mark.asyncio
async def test_expires_at_with_featured_tournament(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Case 3: Tournament in FEATURED status (scheduled, registration not open).
    expires_at = Friday next week (7-13 days).
    """
    user = await create_test_user()
    
    # FEATURED tournament in a month.
    tournament = await create_test_tournament(
        status=TournamentStatus.FEATURED,
        start_date=datetime.now(timezone.utc) + timedelta(days=30),
        end_date=datetime.now(timezone.utc) + timedelta(days=35)
    )
    await db_session.commit()
    
    packs = await grant_pack_to_user(user.id, pack_type_id=6)
    result = await pack_opening_service.open_pack(
        user_id=user.id,
        pack_type_id=6,
        db=db_session
    )
    await db_session.commit()
    
    cards_result = await db_session.execute(
        select(UserCard)
        .where(UserCard.user_id == user.id)
        .order_by(UserCard.id.desc())
    )
    cards = cards_result.scalars().all()
    assert len(cards) > 0
    
    now = datetime.now(timezone.utc)
    for card in cards:
        assert card.expires_at is not None
        assert card.expires_at.weekday() == 4
        assert card.expires_at.hour == 17
        
        # FEATURED != open registration -> next week.
        days_until_expire = (card.expires_at - now).days
        assert 7 <= days_until_expire <= 13, \
            f"FEATURED tournament -> Friday next week (7-13 days), got: {days_until_expire}"
    
    print(f"[OK] FEATURED tournament: {len(cards)} cards, expires_at = {cards[0].expires_at} (in {days_until_expire} days)")


@pytest.mark.asyncio
async def test_expires_at_consistency(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Case 4: All cards from one pack have the same expires_at.
    """
    user = await create_test_user()
    tournament = await create_test_tournament(status=TournamentStatus.REGISTRATION)
    await db_session.commit()
    
    packs = await grant_pack_to_user(user.id, pack_type_id=6)
    result = await pack_opening_service.open_pack(
        user_id=user.id,
        pack_type_id=6,
        db=db_session
    )
    await db_session.commit()
    
    cards_result = await db_session.execute(
        select(UserCard)
        .where(UserCard.user_id == user.id)
        .order_by(UserCard.id.desc())
    )
    cards = cards_result.scalars().all()
    
    # All cards from one pack must have same expires_at.
    expires_dates = [card.expires_at for card in cards]
    unique_dates = set(expires_dates)
    
    assert len(unique_dates) == 1, \
        f"Cards from one pack have different expires_at: {unique_dates}"
    
    print(f"[OK] All {len(cards)} cards have same expires_at = {expires_dates[0]}")