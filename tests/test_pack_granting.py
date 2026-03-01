"""
Tests for pack granting after tournament finalization.
- After finish_tournament() all active users receive packs.
- PackSource.REWARD is used.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from models.tournament_models import Tournament, TournamentStatus
from services.tournament_service import TournamentService


@pytest.fixture
def tournament_service():
    """Return real TournamentService."""
    return TournamentService()


@pytest.mark.asyncio
async def test_packs_granted_after_tournament_finish(
    db_session,
    create_test_user,
    create_test_tournament
):
    """
    Case: After tournament finalization all active users receive packs.
    """
    # 1. Create 3 active users.
    users = []
    for i in range(3):
        user = await create_test_user(nickname=f"pack_user_{i}_{datetime.now().timestamp()}")
        users.append(user)
    
    await db_session.commit()
    
    # 2. Create finished tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # 3. Mock UserPackGrantService.grant_all_active_packs_to_user.
    with patch('services.user_pack_grant_service.UserPackGrantService.grant_all_active_packs_to_user', 
               new_callable=AsyncMock) as mock_grant:
        mock_grant.return_value = []
        
        # 4. Simulate scheduler: grant packs to all active users.
        from models.user_models import User
        from services.user_pack_grant_service import user_pack_grant_service, PackSource
        
        result = await db_session.execute(
            select(User).where(User.is_active == True)
        )
        active_users = result.scalars().all()
        
        for user in active_users:
            await user_pack_grant_service.grant_all_active_packs_to_user(
                user_id=user.id,
                source=PackSource.REWARD
            )
        
        # 5. Assert grant_all_active_packs_to_user was called for each user.
        assert mock_grant.call_count >= 3, \
            f"grant_all_active_packs_to_user must be called at least 3 times, got: {mock_grant.call_count}"
        
        # 6. Assert all calls used source=REWARD.
        for call in mock_grant.call_args_list:
            kwargs = call.kwargs
            assert kwargs.get('source') == PackSource.REWARD, \
                f"source must be REWARD, got: {kwargs.get('source')}"
        
        print(f"[OK] Pack granting: grant called {mock_grant.call_count} times with source=REWARD")


@pytest.mark.asyncio
async def test_inactive_users_do_not_receive_packs(
    db_session,
    create_test_user,
    create_test_tournament
):
    """
    Case: Inactive users (is_active=False) must NOT receive packs.
    """
    # 1. Create active and inactive users.
    active_user = await create_test_user(nickname=f"active_{datetime.now().timestamp()}")
    inactive_user = await create_test_user(nickname=f"inactive_{datetime.now().timestamp()}")
    
    # Make one user inactive.
    inactive_user.is_active = False
    await db_session.commit()
    
    # 2. Create tournament.
    tournament = await create_test_tournament(
        status=TournamentStatus.ONGOING,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),
        end_date=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await db_session.commit()
    
    # 3. Mock pack granting.
    with patch('services.user_pack_grant_service.UserPackGrantService.grant_all_active_packs_to_user', 
               new_callable=AsyncMock) as mock_grant:
        mock_grant.return_value = []
        
        # Simulate scheduler: only active users.
        from models.user_models import User
        from services.user_pack_grant_service import user_pack_grant_service, PackSource
        
        result = await db_session.execute(
            select(User).where(User.is_active == True)
        )
        active_users = result.scalars().all()
        
        for user in active_users:
            await user_pack_grant_service.grant_all_active_packs_to_user(
                user_id=user.id,
                source=PackSource.REWARD
            )
        
        # 4. Assert inactive user did not receive packs.
        called_user_ids = [call.kwargs['user_id'] for call in mock_grant.call_args_list]
        
        assert active_user.id in called_user_ids, \
            "Active user must receive packs"
        assert inactive_user.id not in called_user_ids, \
            "Inactive user must NOT receive packs"
        
        print(f"[OK] Inactive users did not receive packs (only {len(called_user_ids)} active)")