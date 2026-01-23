"""
Тест финализации турнира.
Проверяет:
- Смену статуса ONGOING → FINISHED через finish_tournament()
- Подсчёт результатов через calculate_results()
- Мягкое удаление expired карт (is_active=False)
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
    """Возвращает реальный TournamentService"""
    return TournamentService()


@pytest.mark.asyncio
async def test_expired_cards_soft_delete(db_session, create_test_user):
    """
    Кейс 1: Мягкое удаление expired карт (is_active=False, status=expired).
    Имитируем работу шедулера.
    """
    # 1. Создаём пользователя
    user = await create_test_user()
    
    # 2. Создаём карты: 3 валидные + 2 expired
    now = datetime.now(timezone.utc)
    
    # Валидные карты (expires_at в будущем)
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
    
    # Expired карты (expires_at в прошлом)
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
    
    # Обновляем ID после commit
    for card in valid_cards + expired_cards:
        await db_session.refresh(card)
    
    valid_card_ids = [c.id for c in valid_cards]
    expired_card_ids = [c.id for c in expired_cards]
    
    print(f"📋 Созданы карты: {len(valid_cards)} валидных, {len(expired_cards)} expired")
    
    # 3. Имитируем работу шедулера - мягкое удаление expired карт
    result = await db_session.execute(
        update(UserCard)
        .where(UserCard.expires_at <= now)
        .values(is_active=False, status="expired")
    )
    await db_session.commit()
    
    marked_count = result.rowcount
    print(f"🗑️  Помечено как expired: {marked_count} карт")
    
    # 4. Проверяем что expired карты помечены как is_active=False
    result = await db_session.execute(
        select(UserCard).where(UserCard.id.in_(expired_card_ids))
    )
    expired_cards_updated = result.scalars().all()
    
    assert len(expired_cards_updated) == 2, "Expired карты должны остаться в БД"
    for card in expired_cards_updated:
        assert card.is_active == False, f"Карта {card.id} должна быть is_active=False"
        assert card.status == "expired", f"Карта {card.id} должна иметь status=expired"
    
    # 5. Проверяем что валидные карты остались активными
    result = await db_session.execute(
        select(UserCard).where(UserCard.id.in_(valid_card_ids))
    )
    valid_cards_check = result.scalars().all()
    
    assert len(valid_cards_check) == 3
    for card in valid_cards_check:
        assert card.is_active == True, f"Валидная карта {card.id} должна быть активной"
        assert card.status == "available", f"Валидная карта {card.id} должна быть available"
    
    print(f"✅ Мягкое удаление: {len(expired_cards_updated)} expired, {len(valid_cards_check)} активных")


@pytest.mark.asyncio
async def test_calculate_results_with_participants(
    db_session,
    create_test_user,
    create_test_tournament,
    tournament_service
):
    """
    Кейс 2: calculate_results() создаёт tournament_results для участников.
    """
    import uuid
    
    # 1. Создаём 3 участников с картами (уникальные никнеймы)
    users = []
    user_decks_data = []
    unique_suffix = str(uuid.uuid4())[:8]  # Уникальный суффикс
    
    for i in range(3):
        user = await create_test_user(nickname=f"player_{i}_{unique_suffix}")
        users.append(user)
        
        # Создаём 5 карт для каждого пользователя
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
    
    # 2. Создаём турнир ONGOING
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=3),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # 3. Регистрируем участников с deck_hash
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
    
    # 4. Запускаем подсчёт результатов
    results_count = await tournament_service.calculate_results(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    assert results_count == 3, f"Должно быть создано 3 результата, получено: {results_count}"
    
    # 5. Проверяем что созданы tournament_results
    result = await db_session.execute(
        select(TournamentResult)
        .where(TournamentResult.tournament_id == tournament.id)
        .order_by(TournamentResult.final_position.asc())
    )
    results = result.scalars().all()
    assert len(results) == 3, f"Должно быть 3 результата в БД"


@pytest.mark.asyncio
async def test_finish_tournament_already_finished(
    db_session,
    create_test_tournament,
    tournament_service
):
    """
    Кейс 3: Повторная финализация уже FINISHED турнира должна вызвать ошибку.
    """
    tournament = await create_test_tournament(
        status=TournamentStatus.FINISHED,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),
        end_date=datetime.now(timezone.utc) - timedelta(days=2)
    )
    await db_session.commit()
    
    # Запускаем финализацию (должна вызвать ValueError)
    with pytest.raises(ValueError, match="Cannot finish.*expected 'ongoing'"):
        await tournament_service.finish_tournament(
            tournament_id=tournament.id,
            db=db_session
        )
    
    print(f"✅ Повторная финализация FINISHED турнира правильно вызвала ошибку")


@pytest.mark.asyncio
async def test_finish_tournament_without_participants(
    db_session,
    create_test_tournament,
    tournament_service
):
    """
    Кейс 4: Финализация турнира БЕЗ участников → только смена статуса.
    """
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=2),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # Финализируем турнир без участников
    finished = await tournament_service.finish_tournament(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    # Проверяем статус
    assert finished.status == TournamentStatus.FINISHED
    
    # Проверяем что results НЕ создались
    results_count = await tournament_service.calculate_results(
        tournament_id=tournament.id,
        db=db_session
    )
    
    assert results_count == 0, f"Не должно быть результатов для турнира без участников, получено: {results_count}"
    
    print(f"✅ Финализация без участников: только смена статуса")


@pytest.mark.asyncio
async def test_full_finalization_flow(
    db_session,
    create_test_user,
    create_test_tournament,
    tournament_service
):
    """
    Кейс 5: Полный флоу финализации: finish_tournament → calculate_results.
    """
    # Создаём участника с картами
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
    
    # Создаём турнир
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=4),
        end_date=datetime.now(timezone.utc) - timedelta(hours=2)
    )
    await db_session.commit()
    
    # Генерируем deck_hash
    deck_hash = TournamentRegistrationService.generate_deck_hash(
        tournament_id=tournament.id,
        user_id=user.id,
        deck_composition=user_card_ids
    )
    
    # Добавляем deck
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
    await db_session.refresh(deck)  # Получаем ID
    
    # 1. Финализируем турнир
    finished = await tournament_service.finish_tournament(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    assert finished.status == TournamentStatus.FINISHED
    
    # 2. Подсчитываем результаты
    results_count = await tournament_service.calculate_results(
        tournament_id=tournament.id,
        db=db_session
    )
    await db_session.commit()
    
    assert results_count == 1
    
    # 3. Проверяем что результат создан через tournament_deck_id
    result = await db_session.execute(
        select(TournamentResult).where(
            TournamentResult.tournament_id == tournament.id,
            TournamentResult.tournament_deck_id == deck.id
        )
    )
    tournament_result = result.scalar_one()
    
    assert tournament_result.final_position == 1
    
    print(f"✅ Полный флоу: finish_tournament + calculate_results успешно (позиция: {tournament_result.final_position})")