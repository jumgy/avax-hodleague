"""
Tests for tournament registration validation.
- Expired cards (expires_at in the past) cannot be used for registration.
- Inactive cards (is_active=False) cannot be used.
"""

from datetime import UTC, datetime, timedelta

import pytest

from models.tournament_models import TournamentStatus
from models.user_card_models import UserCard
from services.tournament_registration_service import TournamentRegistrationService


@pytest.fixture
def registration_service():
    """Return real TournamentRegistrationService."""
    return TournamentRegistrationService()


@pytest.mark.asyncio
async def test_cannot_register_with_expired_cards(
    db_session, create_test_user, create_test_tournament, registration_service
):
    """
    Case 1: Registration with expired cards must be rejected.
    """
    # 1. Create user.
    user = await create_test_user()

    # 2. Create expired cards (expires_at in the past).
    now = datetime.now(UTC)
    expired_cards = []

    for card_id in [2, 5, 6, 7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now - timedelta(days=1),  # Expired yesterday.
            source="pack_opening",
            is_active=True,
            status="available",
        )
        db_session.add(card)
        expired_cards.append(card)

    await db_session.flush()
    expired_card_ids = [c.id for c in expired_cards]

    # 3. Create tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(UTC) + timedelta(hours=1),
        end_date=datetime.now(UTC) + timedelta(days=7),
    )
    await db_session.commit()

    # 4. Try to validate deck with expired cards.
    with pytest.raises(Exception) as exc_info:
        await registration_service.validate_deck_preview(
            db=db_session, tournament_id=tournament.id, user_id=user.id, deck_composition=expired_card_ids
        )

    # 5. Assert error mentions expired/invalid cards.
    error_message = str(exc_info.value).lower()
    assert (
        "expire" in error_message or "invalid" in error_message or "not found" in error_message
    ), f"Error must mention expired/invalid cards, got: {exc_info.value}"

    print(f"[OK] Registration with expired cards rejected: {exc_info.value}")


@pytest.mark.asyncio
async def test_cannot_register_with_inactive_cards(
    db_session, create_test_user, create_test_tournament, registration_service
):
    """
    Case 2: Registration with inactive cards (is_active=False) must be rejected.
    """
    # 1. Create user.
    user = await create_test_user()

    # 2. Create inactive cards.
    now = datetime.now(UTC)
    inactive_cards = []

    for card_id in [2, 5, 6, 7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now + timedelta(days=7),  # Not expired.
            source="pack_opening",
            is_active=False,  # Inactive.
            status="expired",
        )
        db_session.add(card)
        inactive_cards.append(card)

    await db_session.flush()
    inactive_card_ids = [c.id for c in inactive_cards]

    # 3. Create tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(UTC) + timedelta(hours=1),
        end_date=datetime.now(UTC) + timedelta(days=7),
    )
    await db_session.commit()

    # 4. Try to validate deck with inactive cards.
    with pytest.raises(Exception) as exc_info:
        await registration_service.validate_deck_preview(
            db=db_session, tournament_id=tournament.id, user_id=user.id, deck_composition=inactive_card_ids
        )

    # 5. Assert error mentions invalid/inactive cards.
    error_message = str(exc_info.value).lower()
    assert (
        "invalid" in error_message
        or "not found" in error_message
        or "inactive" in error_message
        or "not active" in error_message
        or "not available" in error_message
    ), f"Error must mention invalid/inactive cards, got: {exc_info.value}"

    print(f"[OK] Registration with inactive cards rejected: {exc_info.value}")


@pytest.mark.asyncio
async def test_can_register_with_valid_cards(
    db_session, create_test_user, create_test_tournament, registration_service
):
    """
    Case 3: Validation with valid active cards must succeed.
    """
    # 1. Create user.
    user = await create_test_user()

    # 2. Create valid active cards.
    now = datetime.now(UTC)
    valid_cards = []

    for card_id in [2, 5, 6, 7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now + timedelta(days=7),  # Not expired.
            source="pack_opening",
            is_active=True,  # Active.
            status="available",
        )
        db_session.add(card)
        valid_cards.append(card)

    await db_session.flush()
    valid_card_ids = [c.id for c in valid_cards]

    # 3. Create tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(UTC) + timedelta(hours=1),
        end_date=datetime.now(UTC) + timedelta(days=7),
    )
    await db_session.commit()

    # 4. Validate deck with valid cards.
    preview = await registration_service.validate_deck_preview(
        db=db_session, tournament_id=tournament.id, user_id=user.id, deck_composition=valid_card_ids
    )

    # 5. Assert validation succeeded.
    assert preview is not None, "Preview must be returned"
    assert preview["valid"] == True, "Deck must be valid"
    assert "deck_hash" in preview, "deck_hash must be generated"
    assert preview["deck_hash"].startswith("0x"), "deck_hash must start with 0x"
    assert len(preview["cards"]) == 5, "Must have 5 cards"
    assert preview["total_weight"] > 0, "Total weight must be greater than 0"

    print(
        f"[OK] Validation with valid cards succeeded (weight: {preview['total_weight']}, hash: {preview['deck_hash'][:10]}...)"
    )
