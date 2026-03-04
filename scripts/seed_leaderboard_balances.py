"""
Seed user balances for leaderboard testing.

Writes claimed user_rewards so they appear in user_balances_view (available_balance).
Use GET /api/users/leaderboard?sort_by=balance to verify sorting.
"""
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal
from models.user_models import User
from models.reward_models import RewardType, UserReward, ClaimStatus


async def seed_leaderboard_balances(
    max_users: int = 50,
    amount_min: float = 100.0,
    amount_max: float = 100_000.0,
    reward_type_id: Optional[int] = None,
) -> None:
    """Grant claimed rewards to active users with varying amounts.

    Args:
        max_users: Maximum number of users to process (default 50).
        amount_min: Minimum amount per user.
        amount_max: Maximum amount per user.
        reward_type_id: If set, use only this reward type; otherwise use first active.
    """
    async with AsyncSessionLocal() as session:
        # Reward type
        if reward_type_id is not None:
            rt_result = await session.execute(
                select(RewardType).where(
                    RewardType.id == reward_type_id,
                    RewardType.is_active == True,
                )
            )
            rt = rt_result.scalar_one_or_none()
        else:
            rt_result = await session.execute(
                select(RewardType).where(RewardType.is_active == True).order_by(RewardType.id).limit(1)
            )
            rt = rt_result.scalar_one_or_none()

        if not rt:
            print("No active reward types found. Create at least one.")
            return

        # Active users
        users_result = await session.execute(
            select(User).where(User.is_active == True).order_by(User.id).limit(max_users)
        )
        users = users_result.scalars().all()
        if not users:
            print("No active users found.")
            return

        now = datetime.now(timezone.utc)
        created = 0
        for i, user in enumerate(users):
            amount = round(random.uniform(amount_min, amount_max), 8)
            reward = UserReward(
                user_id=user.id,
                reward_type_id=rt.id,
                amount=amount,
                tournament_result_id=None,
                earned_at=now,
                claimed_at=now,
                claim_status=ClaimStatus.CLAIMED,
            )
            session.add(reward)
            created += 1

        await session.commit()
        print(f"Granted {created} rewards (reward_type_id={rt.id}, {rt.name}). Verify: GET /api/users/leaderboard?sort_by=balance")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed balances for leaderboard testing")
    parser.add_argument("--max-users", type=int, default=50, help="Max users (default: 50)")
    parser.add_argument("--min", type=float, default=100.0, help="Min amount per user")
    parser.add_argument("--max", type=float, default=100_000.0, help="Max amount per user")
    parser.add_argument("--reward-type-id", type=int, default=None, help="Reward type ID (default: first active)")
    args = parser.parse_args()
    asyncio.run(seed_leaderboard_balances(
        max_users=args.max_users,
        amount_min=args.min,
        amount_max=args.max,
        reward_type_id=args.reward_type_id,
    ))
