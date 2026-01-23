"""
Тест расчёта expires_at для карт из паков.
Проверяет логику: зависит ли expires_at от наличия турнира с открытой регистрацией.
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
    Кейс 1: Есть турнир с открытой регистрацией (REGISTRATION).
    expires_at должна быть = ближайшая пятница 17:00 UTC (0-6 дней).
    """
    # 1. Создаём пользователя
    user = await create_test_user()
    
    # 2. Создаём турнир в статусе REGISTRATION
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(timezone.utc) + timedelta(hours=2),
        end_date=datetime.now(timezone.utc) + timedelta(days=5)
    )
    await db_session.commit()
    
    # 3. Выдаём пак
    packs = await grant_pack_to_user(user.id, pack_type_id=6)
    assert len(packs) > 0
    
    # 4. Открываем пак
    result = await pack_opening_service.open_pack(
        user_id=user.id,
        pack_type_id=6,
        db=db_session
    )
    await db_session.commit()
    
    # 5. Получаем карты
    cards_result = await db_session.execute(
        select(UserCard)
        .where(UserCard.user_id == user.id)
        .order_by(UserCard.id.desc())
    )
    cards = cards_result.scalars().all()
    assert len(cards) > 0
    
    # 6. Проверяем expires_at
    now = datetime.now(timezone.utc)
    for card in cards:
        assert card.expires_at is not None
        assert card.expires_at > now
        assert card.expires_at.weekday() == 4  # Пятница
        assert card.expires_at.hour == 17
        assert card.expires_at.minute == 0
        
        # Ближайшая пятница = 0-6 дней
        days_until_expire = (card.expires_at - now).days
        assert 0 <= days_until_expire <= 6, \
            f"REGISTRATION турнир → ближайшая пятница (0-6 дней), получено: {days_until_expire}"
    
    print(f"✅ REGISTRATION турнир: {len(cards)} карт, expires_at = {cards[0].expires_at}")


@pytest.mark.asyncio
async def test_expires_at_without_open_tournament(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Кейс 2: НЕТ турнира с открытой регистрацией (турнир ONGOING).
    expires_at должна быть = пятница через неделю (7-13 дней).
    """
    user = await create_test_user()
    
    # Турнир уже идёт (ONGOING)
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
        assert card.expires_at.weekday() == 4  # Пятница
        assert card.expires_at.hour == 17
        
        # Следующая неделя = 7-13 дней
        days_until_expire = (card.expires_at - now).days
        assert 7 <= days_until_expire <= 13, \
            f"ONGOING турнир → пятница через неделю (7-13 дней), получено: {days_until_expire}"
    
    print(f"✅ ONGOING турнир: {len(cards)} карт, expires_at = {cards[0].expires_at} (через {days_until_expire} дней)")


@pytest.mark.asyncio
async def test_expires_at_with_featured_tournament(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Кейс 3: Турнир в статусе FEATURED (запланирован, регистрация НЕ открыта).
    expires_at = пятница через неделю (7-13 дней).
    """
    user = await create_test_user()
    
    # FEATURED турнир через месяц
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
        
        # FEATURED ≠ открытая регистрация → через неделю
        days_until_expire = (card.expires_at - now).days
        assert 7 <= days_until_expire <= 13, \
            f"FEATURED турнир → пятница через неделю (7-13 дней), получено: {days_until_expire}"
    
    print(f"✅ FEATURED турнир: {len(cards)} карт, expires_at = {cards[0].expires_at} (через {days_until_expire} дней)")


@pytest.mark.asyncio
async def test_expires_at_consistency(
    db_session,
    create_test_user,
    create_test_tournament,
    grant_pack_to_user,
    pack_opening_service
):
    """
    Кейс 4: Все карты из одного пака имеют одинаковый expires_at.
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
    
    # Все карты должны иметь одинаковый expires_at
    expires_dates = [card.expires_at for card in cards]
    unique_dates = set(expires_dates)
    
    assert len(unique_dates) == 1, \
        f"Карты из одного пака имеют разные expires_at: {unique_dates}"
    
    print(f"✅ Все {len(cards)} карт имеют одинаковый expires_at = {expires_dates[0]}")