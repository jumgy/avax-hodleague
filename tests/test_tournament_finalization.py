"""
Tests for tournament finalization.
- Status change ONGOING to FINISHED via finish_tournament().
- Result calculation via calculate_results().
- Soft delete of expired cards (is_active=False).
"""
import pytest
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from models.tournament_models import Tournament, TournamentStatus
from models.user_card_models import UserCard
from models.tournament_deck_models import TournamentDeck, TournamentResult
from services import tournament_registration_service
from services.tournament_service import TournamentService
from services.tournament_registration_service import TournamentRegistrationService

@pytest.fixture
def tournament_service():
    """Return real TournamentService."""
    return TournamentService()


@pytest.mark.asyncio
async def test_expired_cards_soft_delete(db_session, create_test_user):
    """
    Case 1: Soft delete of expired cards (is_active=False, status=expired).
    Simulate scheduler job.
    """
    # 1. Create user.
    user = await create_test_user()
    
    # 2. Create cards: 3 valid + 2 expired.
    now = datetime.now(timezone.utc)
    
    # Valid cards (expires_at in the future).
    valid_cards = []
    for card_id in [2, 5, 6]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now + timedelta(days=7),
            source='pack_opening',
            is_active=True,
            status='available'
        )
        db_session.add(card)
        valid_cards.append(card)
    
    # Expired cards (expires_at in the past).
    expired_cards = []
    for card_id in [7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now - timedelta(days=1),
            source='pack_opening',
            is_active=True,
            status='available'
        )
        db_session.add(card)
        expired_cards.append(card)
    
    await db_session.commit()
    
    # Refresh IDs after commit.
    for card in valid_cards + expired_cards:
        await db_session.refresh(card)
    
    valid_card_ids = [c.id for c in valid_cards]
    expired_card_ids = [c.id for c in expired_cards]
    
    print(f"[OK] Created cards: {len(valid_cards)} valid, {len(expired_cards)} expired")
    
    # 3. Simulate scheduler: soft delete expired cards.
    result = await db_session.execute(
        update(UserCard)
        .where(UserCard.expires_at <= now)
        .values(is_active=False, status="expired")
    )
    await db_session.commit()
    
    marked_count = result.rowcount
    print(f"[OK] Marked as expired: {marked_count} cards")
    
    # 4. Assert expired cards are is_active=False.
    result = await db_session.execute(
        select(UserCard).where(UserCard.id.in_(expired_card_ids))
    )
    expired_cards_updated = result.scalars().all()
    
    assert len(expired_cards_updated) == 2, "Expired cards must remain in DB"
    for card in expired_cards_updated:
        assert card.is_active == False, f"Card {card.id} must be is_active=False"
        assert card.status == "expired", f"Card {card.id} must have status=expired"
    
    # 5. Assert valid cards stayed active.
    result = await db_session.execute(
        select(UserCard).where(UserCard.id.in_(valid_card_ids))
    )
    valid_cards_check = result.scalars().all()
    
    assert len(valid_cards_check) == 3
    for card in valid_cards_check:
        assert card.is_active == True, f"Valid card {card.id} must be active"
        assert card.status == "available", f"Valid card {card.id} must be available"
    
    print(f"[OK] Soft delete: {len(expired_cards_updated)} expired, {len(valid_cards_check)} active")


@pytest.mark.asyncio
async def test_calculate_results_with_participants(
    db_session,
    create_test_user,
    create_test_tournament,
    tournament_service
):
    """
    Case 2: calculate_results() creates tournament_results for participants.
    """
    import uuid
    
    # 1. Create 3 participants with cards (unique nicknames).
    users = []
    user_decks_data = []
    unique_suffix = str(uuid.uuid4())[:8]
    
    for i in range(3):
        user = await create_test_user(nickname=f"player_{i}_{unique_suffix}")
        users.append(user)
        
        # Create 5 cards per user.
        user_cards = []
        for card_id in [2, 5, 6, 7, 8]:
            card = UserCard(
                user_id=user.id,
                card_id=card_id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                source='pack_opening',
                is_active=True,
                status='available'
            )
            db_session.add(card)
            user_cards.append(card)
        
        await db_session.flush()
        user_card_ids = [c.id for c in user_cards]
        user_decks_data.append((user, user_card_ids))
    
    # 2. Create ONGOING tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=3),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # 3. Register participants with deck_hash.
    for user, user_card_ids in user_decks_data:
        deck_hash = TournamentRegistrationService.generate_deck_hash(
            tournament_id=tournament.id,
            user_id=user.id,
            deck_composition=user_card_ids
        )
        
        deck = TournamentDeck(
            user_id=user.id,
            tournament_id=tournament.id,
            deck_composition=user_card_ids,
            deck_hash=deck_hash,
            total_weight=25.0,
            is_valid=True,
            is_active=True
        )
        db_session.add(deck)
    
    await db_session.commit()
    
    # 4. Run result calculation.
    results_count = await tournament_service.calculate_results(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    assert results_count == 3, f"Must create 3 results, got: {results_count}"
    
    # 5. Assert tournament_results were created.
    result = await db_session.execute(
        select(TournamentResult)
        .where(TournamentResult.tournament_id == tournament.id)
        .order_by(TournamentResult.final_position.asc())
    )
    results = result.scalars().all()
    assert len(results) == 3, "Must have 3 results in DB"


@pytest.mark.asyncio
async def test_finish_tournament_already_finished(
    db_session,
    create_test_tournament,
    tournament_service
):
    """
    Case 3: Re-finalizing an already FINISHED tournament must raise an error.
    """
    tournament = await create_test_tournament(
        status=TournamentStatus.FINISHED,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),
        end_date=datetime.now(timezone.utc) - timedelta(days=2)
    )
    await db_session.commit()
    
    # Run finalization (must raise ValueError).
    with pytest.raises(ValueError, match="Cannot finish.*expected 'ongoing'"):
        await tournament_service.finish_tournament(
            tournament_id=tournament.id,
            db=db_session
        )
    
    print("[OK] Re-finalizing FINISHED tournament correctly raised error")


@pytest.mark.asyncio
async def test_finish_tournament_without_participants(
    db_session,
    create_test_tournament,
    tournament_service
):
    """
    Case 4: Finalizing tournament WITHOUT participants: only status change.
    """
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=2),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # Finalize tournament without participants.
    finished = await tournament_service.finish_tournament(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    # Assert status.
    assert finished.status == TournamentStatus.FINISHED
    
    # Assert no results were created.
    results_count = await tournament_service.calculate_results(
        tournament_id=tournament.id,
        db=db_session
    )
    
    assert results_count == 0, f"No results expected for tournament without participants, got: {results_count}"
    
    print("[OK] Finalization without participants: status change only")


@pytest.mark.asyncio
async def test_full_finalization_flow(
    db_session,
    create_test_user,
    create_test_tournament,
    tournament_service
):
    """
    Case 5: Full finalization flow: finish_tournament then calculate_results.
    """
    # Create participant with cards.
    user = await create_test_user()
    
    user_cards = []
    for card_id in [2, 5, 6]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            source='pack_opening',
            is_active=True,
            status='available'
        )
        db_session.add(card)
        user_cards.append(card)
    
    await db_session.flush()
    user_card_ids = [c.id for c in user_cards]
    
    # Create tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=4),
        end_date=datetime.now(timezone.utc) - timedelta(hours=2)
    )
    await db_session.commit()
    
    # Generate deck_hash.
    deck_hash = TournamentRegistrationService.generate_deck_hash(
        tournament_id=tournament.id,
        user_id=user.id,
        deck_composition=user_card_ids
    )
    
    # Add deck.
    deck = TournamentDeck(
        user_id=user.id,
        tournament_id=tournament.id,
        deck_composition=user_card_ids,
        deck_hash=deck_hash,
        total_weight=20.0,
        is_valid=True,
        is_active=True
    )
    db_session.add(deck)
    await db_session.commit()
    await db_session.refresh(deck)
    
    # 1. Finalize tournament.
    finished = await tournament_service.finish_tournament(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    assert finished.status == TournamentStatus.FINISHED
    
    # 2. Calculate results.
    results_count = await tournament_service.calculate_results(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    assert results_count == 1
    
    # 3. Assert result was created via tournament_deck_id.
    result = await db_session.execute(
        select(TournamentResult).where(
            TournamentResult.tournament_id == tournament.id,
            TournamentResult.tournament_deck_id == deck.id
        )
    )
    tournament_result = result.scalar_one()
    
    assert tournament_result.final_position == 1
    
    print(f"[OK] Full flow: finish_tournament + calculate_results succeeded (position: {tournament_result.final_position})")