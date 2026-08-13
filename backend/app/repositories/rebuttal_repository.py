from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Rebuttal


class RebuttalRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, rebuttal: Rebuttal) -> Rebuttal:
        self.db.add(rebuttal)
        await self.db.flush()
        return rebuttal
