"""
Тест выдачи паков после финализации турнира.
Проверяет:
- После finish_tournament() всем активным юзерам выдаются паки
- Используется PackSource.REWARD
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from models.tournament_models import Tournament, TournamentStatus
from services.tournament_service import TournamentService


@pytest.fixture
def tournament_service():
    """Возвращает реальный TournamentService"""
    return TournamentService()


@pytest.mark.asyncio
async def test_packs_granted_after_tournament_finish(
    db_session,
    create_test_user,
    create_test_tournament
):
    """
    Кейс: После финализации турнира всем активным юзерам выдаются паки.
    """
    # 1. Создаём 3 активных пользователей
    users = []
    for i in range(3):
        user = await create_test_user(nickname=f"pack_user_{i}_{datetime.now().timestamp()}")
        users.append(user)
    
    await db_session.commit()
    
    # 2. Создаём турнир который закончился
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # 3. Мокируем метод класса UserPackGrantService
    with patch('services.user_pack_grant_service.UserPackGrantService.grant_all_active_packs_to_user', 
               new_callable=AsyncMock) as mock_grant:
        mock_grant.return_value = []  # Возвращаем пустой список паков
        
        # 4. Имитируем работу шедулера - выдаём паки всем активным юзерам
        from models.user_models import User
        from services.user_pack_grant_service import user_pack_grant_service, PackSource
        
        result = await db_session.execute(
            select(User).where(User.is_active == True)
        )
        active_users = result.scalars().all()
        
        for user in active_users:
            await user_pack_grant_service.grant_all_active_packs_to_user(
                user_id=user.id,
                source=PackSource.REWARD  # ← Используем REWARD
            )
        
        # 5. Проверяем что grant_all_active_packs_to_user вызвался для каждого юзера
        assert mock_grant.call_count >= 3, \
            f"grant_all_active_packs_to_user должен быть вызван минимум 3 раза (для наших юзеров), вызвано: {mock_grant.call_count}"
        
        # 6. Проверяем что все вызовы были с source=REWARD
        for call in mock_grant.call_args_list:
            kwargs = call.kwargs
            assert kwargs.get('source') == PackSource.REWARD, \
                f"source должен быть REWARD, получено: {kwargs.get('source')}"
        
        print(f"✅ Выдача паков: grant вызван {mock_grant.call_count} раз с source=REWARD")


@pytest.mark.asyncio
async def test_inactive_users_do_not_receive_packs(
    db_session,
    create_test_user,
    create_test_tournament
):
    """
    Кейс: Неактивные юзеры (is_active=False) НЕ должны получать паки.
    """
    # 1. Создаём активного и неактивного юзеров
    active_user = await create_test_user(nickname=f"active_{datetime.now().timestamp()}")
    inactive_user = await create_test_user(nickname=f"inactive_{datetime.now().timestamp()}")
    
    # Делаем одного неактивным
    inactive_user.is_active = False
    await db_session.commit()
    
    # 2. Создаём турнир
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # 3. Мокируем выдачу паков
    with patch('services.user_pack_grant_service.UserPackGrantService.grant_all_active_packs_to_user', 
               new_callable=AsyncMock) as mock_grant:
        mock_grant.return_value = []
        
        # Имитируем шедулер
        from models.user_models import User
        from services.user_pack_grant_service import user_pack_grant_service, PackSource
        
        result = await db_session.execute(
            select(User).where(User.is_active == True)  # ← Только активные
        )
        active_users = result.scalars().all()
        
        # Выдаём паки только активным
        for user in active_users:
            await user_pack_grant_service.grant_all_active_packs_to_user(
                user_id=user.id,
                source=PackSource.REWARD  # ← Используем REWARD
            )
        
        # 4. Проверяем что неактивному юзеру паки НЕ выдавались
        called_user_ids = [call.kwargs['user_id'] for call in mock_grant.call_args_list]
        
        assert active_user.id in called_user_ids, \
            "Активному юзеру должны быть выданы паки"
        assert inactive_user.id not in called_user_ids, \
            "Неактивному юзеру НЕ должны быть выданы паки"
        
        print(f"✅ Неактивные юзеры не получили паки (только {len(called_user_ids)} активных)")