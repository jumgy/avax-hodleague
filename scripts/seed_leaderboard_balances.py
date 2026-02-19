"""
Скрипт для начисления балансов пользователям в тестовой БД.
Нужен для проверки лидерборда GET /api/users/leaderboard?sort_by=balance.

Записывает в user_rewards записи со статусом claimed, чтобы они попали
в user_balances_view (available_balance). Суммы различаются, чтобы тестировать сортировку.
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
    """
    Начислить claimed-награды активным пользователям с разными суммами.

    :param max_users: максимум пользователей (по умолчанию 50)
    :param amount_min: минимальная сумма на пользователя
    :param amount_max: максимальная сумма на пользователя
    :param reward_type_id: если задан — использовать только этот тип награды, иначе первый активный
    """
    async with AsyncSessionLocal() as session:
        # Тип награды
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
            print("Нет активных типов наград (reward_types). Создайте хотя бы один.")
            return

        # Активные пользователи
        users_result = await session.execute(
            select(User).where(User.is_active == True).order_by(User.id).limit(max_users)
        )
        users = users_result.scalars().all()
        if not users:
            print("Нет активных пользователей.")
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
        print(f"Начислено {created} записей (reward_type_id={rt.id}, {rt.name}) пользователям. Проверьте: GET /api/users/leaderboard?sort_by=balance")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Начислить балансы для теста лидерборда")
    parser.add_argument("--max-users", type=int, default=50, help="Макс. пользователей (default: 50)")
    parser.add_argument("--min", type=float, default=100.0, help="Мин. сумма на пользователя")
    parser.add_argument("--max", type=float, default=100_000.0, help="Макс. сумма на пользователя")
    parser.add_argument("--reward-type-id", type=int, default=None, help="ID типа награды (default: первый активный)")
    args = parser.parse_args()
    asyncio.run(seed_leaderboard_balances(
        max_users=args.max_users,
        amount_min=args.min,
        amount_max=args.max,
        reward_type_id=args.reward_type_id,
    ))
