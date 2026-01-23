"""
Тест валидации регистрации в турнир.
Проверяет:
- Expired карты (expires_at в прошлом) нельзя использовать при регистрации
- Неактивные карты (is_active=False) нельзя использовать
"""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from models.tournament_models import TournamentStatus
from models.user_card_models import UserCard
from services.tournament_registration_service import TournamentRegistrationService


@pytest.fixture
def registration_service():
    """Возвращает реальный TournamentRegistrationService"""
    return TournamentRegistrationService()


@pytest.mark.asyncio
async def test_cannot_register_with_expired_cards(
    db_session,
    create_test_user,
    create_test_tournament,
    registration_service
):
    """
    Кейс 1: Попытка регистрации с expired картами должна быть отклонена.
    """
    # 1. Создаём пользователя
    user = await create_test_user()
    
    # 2. Создаём expired карты (expires_at в прошлом)
    now = datetime.now(timezone.utc)
    expired_cards = []
    
    for card_id in [2, 5, 6, 7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now - timedelta(days=1),  # ← Истекли вчера
            source='pack_opening',
            is_active=True,
            status='available'
        )
        db_session.add(card)
        expired_cards.append(card)
    
    await db_session.flush()
    expired_card_ids = [c.id for c in expired_cards]
    
    # 3. Создаём турнир
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(timezone.utc) + timedelta(hours=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=7)
    )
    await db_session.commit()
    
    # 4. Пытаемся валидировать дек с expired картами
    with pytest.raises(Exception) as exc_info:
        await registration_service.validate_deck_preview(
            db=db_session,
            tournament_id=tournament.id,
            user_id=user.id,
            deck_composition=expired_card_ids
        )
    
    # 5. Проверяем что ошибка связана с expired картами
    error_message = str(exc_info.value).lower()
    assert 'expire' in error_message or 'invalid' in error_message or 'not found' in error_message, \
        f"Ошибка должна упоминать expired/invalid карты, получено: {exc_info.value}"
    
    print(f"✅ Регистрация с expired картами отклонена: {exc_info.value}")


@pytest.mark.asyncio
async def test_cannot_register_with_inactive_cards(
    db_session,
    create_test_user,
    create_test_tournament,
    registration_service
):
    """
    Кейс 2: Попытка регистрации с неактивными картами (is_active=False) должна быть отклонена.
    """
    # 1. Создаём пользователя
    user = await create_test_user()
    
    # 2. Создаём неактивные карты
    now = datetime.now(timezone.utc)
    inactive_cards = []
    
    for card_id in [2, 5, 6, 7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now + timedelta(days=7),  # Не истекли
            source='pack_opening',
            is_active=False,  # ← Неактивны
            status='expired'
        )
        db_session.add(card)
        inactive_cards.append(card)
    
    await db_session.flush()
    inactive_card_ids = [c.id for c in inactive_cards]
    
    # 3. Создаём турнир
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(timezone.utc) + timedelta(hours=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=7)
    )
    await db_session.commit()
    
    # 4. Пытаемся валидировать дек с неактивными картами
    with pytest.raises(Exception) as exc_info:
        await registration_service.validate_deck_preview(
            db=db_session,
            tournament_id=tournament.id,
            user_id=user.id,
            deck_composition=inactive_card_ids
        )
    
    # 5. Проверяем что ошибка связана с валидностью карт
    error_message = str(exc_info.value).lower()
    assert 'invalid' in error_message or 'not found' in error_message or 'inactive' in error_message or 'not active' in error_message or 'not available' in error_message, \
        f"Ошибка должна упоминать invalid/inactive карты, получено: {exc_info.value}"
    
    print(f"✅ Регистрация с неактивными картами отклонена: {exc_info.value}")


@pytest.mark.asyncio
async def test_can_register_with_valid_cards(
    db_session,
    create_test_user,
    create_test_tournament,
    registration_service
):
    """
    Кейс 3: Валидация с валидными активными картами должна пройти успешно.
    """
    # 1. Создаём пользователя
    user = await create_test_user()
    
    # 2. Создаём валидные активные карты
    now = datetime.now(timezone.utc)
    valid_cards = []
    
    for card_id in [2, 5, 6, 7, 8]:
        card = UserCard(
            user_id=user.id,
            card_id=card_id,
            expires_at=now + timedelta(days=7),  # ← Не истекли
            source='pack_opening',
            is_active=True,  # ← Активны
            status='available'
        )
        db_session.add(card)
        valid_cards.append(card)
    
    await db_session.flush()
    valid_card_ids = [c.id for c in valid_cards]
    
    # 3. Создаём турнир
    tournament = await create_test_tournament(
        status=TournamentStatus.REGISTRATION,
        start_date=datetime.now(timezone.utc) + timedelta(hours=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=7)
    )
    await db_session.commit()
    
    # 4. Валидируем дек с валидными картами
    preview = await registration_service.validate_deck_preview(
        db=db_session,
        tournament_id=tournament.id,
        user_id=user.id,
        deck_composition=valid_card_ids
    )
    
    # 5. Проверяем что валидация прошла успешно
    assert preview is not None, "Preview должен быть возвращён"
    assert preview['valid'] == True, "Дек должен быть валидным"
    assert 'deck_hash' in preview, "Должен быть сгенерирован deck_hash"
    assert preview['deck_hash'].startswith('0x'), "deck_hash должен начинаться с 0x"
    assert len(preview['cards']) == 5, "Должно быть 5 карт"
    assert preview['total_weight'] > 0, "Общий вес должен быть больше 0"
    
    print(f"✅ Валидация с валидными картами прошла успешно (вес: {preview['total_weight']}, hash: {preview['deck_hash'][:10]}...)")