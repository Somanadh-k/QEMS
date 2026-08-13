from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QADecision


class DecisionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, decision: QADecision) -> QADecision:
        self.db.add(decision)
        await self.db.flush()
        return decision
