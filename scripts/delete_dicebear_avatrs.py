import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import AsyncSessionLocal
from models.user_models import User

async def nullify_dicebear_avatars():
    async with AsyncSessionLocal() as session:
        # Find users with DiceBear avatar_url 
        result = await session.execute(
            select(User).where(User.avatar_url.contains("api.dicebear.com"))
        )
        users = result.scalars().all()
        print(f"Found {len(users)} users to update.")

        # Clear avatar_url (no extra updates needed)
        for user in users:
            user.avatar_url = None
        await session.commit()
        print(f"Updated {len(users)} users.")

if __name__ == "__main__":
    asyncio.run(nullify_dicebear_avatars())