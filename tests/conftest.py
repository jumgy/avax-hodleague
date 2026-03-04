"""
Pytest fixtures for integration testing.
Uses real DB and cleans data after tests.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from models.database import AsyncSessionLocal
from models.tournament_models import Tournament, TournamentStatus
from models.user_models import User
from models.user_pack_models import PackSource, UserPack

# Real services for tests.
from services.pack_opening_service import PackOpeningService
from services.user_pack_grant_service import user_pack_grant_service

# ============================================================================
# EVENT LOOP FIXTURE
# ============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the whole test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
async def db_session():
    """Create real DB session for the test."""
    async with AsyncSessionLocal() as session:
        yield session


# ============================================================================
# CLEANUP FIXTURE
# ============================================================================


@pytest.fixture(scope="function", autouse=True)
async def auto_cleanup():
    """Clean test data BEFORE the test via raw SQL."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        try:
            # 1. Remove test users and their data.
            result = await session.execute(text("SELECT id FROM users WHERE wallet_address LIKE '0xTest%'"))
            test_user_ids = [row[0] for row in result.fetchall()]

            if test_user_ids:
                ids_str = ",".join(map(str, test_user_ids))

                # Delete in correct order (FK constraints).
                await session.execute(text(f"DELETE FROM user_rewards WHERE user_id IN ({ids_str})"))
                await session.execute(text(f"DELETE FROM user_cards WHERE user_id IN ({ids_str})"))
                await session.execute(text(f"DELETE FROM pack_openings WHERE user_id IN ({ids_str})"))
                await session.execute(text(f"DELETE FROM user_packs WHERE user_id IN ({ids_str})"))
                await session.execute(text(f"DELETE FROM tournament_decks WHERE user_id IN ({ids_str})"))
                await session.execute(text(f"DELETE FROM users WHERE id IN ({ids_str})"))

            # 2. Remove test tournaments (tournament_number >= 9000).
            result = await session.execute(text("SELECT id FROM tournaments WHERE tournament_number >= 9000"))
            test_tournament_ids = [row[0] for row in result.fetchall()]

            if test_tournament_ids:
                t_ids_str = ",".join(map(str, test_tournament_ids))

                # Delete tournament_prize_config first (FK constraint).
                try:
                    await session.execute(
                        text(f"DELETE FROM tournament_prize_config WHERE tournament_id IN ({t_ids_str})")
                    )
                except Exception as e:
                    print(f"[WARNING] tournament_prize_config cleanup: {e}")

                # Find tournament_results.
                result = await session.execute(
                    text(f"SELECT id FROM tournament_results WHERE tournament_id IN ({t_ids_str})")
                )
                test_tr_ids = [row[0] for row in result.fetchall()]

                # Delete user_rewards linked to tournament_results.
                if test_tr_ids:
                    tr_ids_str = ",".join(map(str, test_tr_ids))
                    await session.execute(
                        text(f"DELETE FROM user_rewards WHERE tournament_result_id IN ({tr_ids_str})")
                    )

                # Delete tournament-related data.
                await session.execute(text(f"DELETE FROM token_scores WHERE tournament_id IN ({t_ids_str})"))
                await session.execute(text(f"DELETE FROM tournament_results WHERE tournament_id IN ({t_ids_str})"))
                await session.execute(
                    text(f"DELETE FROM tournament_token_snapshots WHERE tournament_id IN ({t_ids_str})")
                )
                await session.execute(text(f"DELETE FROM tournament_decks WHERE tournament_id IN ({t_ids_str})"))

                # Delete tournaments themselves.
                await session.execute(text(f"DELETE FROM tournaments WHERE id IN ({t_ids_str})"))

            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"[WARNING] Cleanup warning: {e}")

    yield


# ============================================================================
# SERVICE FIXTURES
# ============================================================================


@pytest.fixture
def pack_opening_service():
    """Return real PackOpeningService."""
    return PackOpeningService()


# ============================================================================
# FACTORY FIXTURES
# ============================================================================


@pytest.fixture
async def create_test_user(db_session):
    """Create a test user."""

    async def _create_user(wallet_address: str = None, nickname: str = None, is_active: bool = True):
        timestamp = int(time.time() * 1000000)

        user = User(
            wallet_address=wallet_address or f"0xTest{timestamp}",
            nickname=nickname or f"test_{timestamp}",
            referral_route=f"T{timestamp}",
            avatar_url="https://example.com/avatar.png",
            is_active=is_active,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture
async def create_test_tournament(db_session):
    """Create a test tournament."""

    async def _create_tournament(
        status: str = TournamentStatus.REGISTRATION,
        start_date: datetime = None,
        end_date: datetime = None,
        weight_limit: int = 30,
    ):
        timestamp = int(time.time() * 1000000)
        tournament_number = 900000 + (timestamp % 100000)

        now = datetime.now(UTC)
        tournament = Tournament(
            tournament_number=tournament_number,
            status=status,
            start_date=start_date or (now + timedelta(hours=1)),
            end_date=end_date or (now + timedelta(days=5)),
            weight_limit=weight_limit,
            is_active=True,
        )
        db_session.add(tournament)
        await db_session.commit()
        await db_session.refresh(tournament)
        return tournament

    return _create_tournament


@pytest.fixture
async def grant_pack_to_user(db_session):
    """Grant a pack to a user."""

    async def _grant_pack(user_id: int, source: str = PackSource.ADMIN, pack_type_id: int = None):
        if pack_type_id:
            # Grant specific pack type.
            user_pack = UserPack(user_id=user_id, pack_type_id=pack_type_id, source=source, is_opened=False)
            db_session.add(user_pack)
            await db_session.commit()
            await db_session.refresh(user_pack)
            return [user_pack]
        else:
            # Grant all active packs via service.
            await user_pack_grant_service.grant_all_active_packs_to_user(user_id=user_id, source=source)

            async with AsyncSessionLocal() as fresh_session:
                result = await fresh_session.execute(
                    select(UserPack)
                    .where(UserPack.user_id == user_id, UserPack.is_opened == False)
                    .order_by(UserPack.id.desc())
                )
                packs = result.scalars().all()
                for pack in packs:
                    fresh_session.expunge(pack)
                return packs

    return _grant_pack
