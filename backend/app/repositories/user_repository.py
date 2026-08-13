from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User, UserRole


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _base_query(self):
        return select(User).options(selectinload(User.user_roles).selectinload(UserRole.role))

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(self._base_query().where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(self._base_query().where(User.email == email))
        return result.scalar_one_or_none()
