from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Evidence


class EvidenceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, evidence: Evidence) -> Evidence:
        self.db.add(evidence)
        await self.db.flush()
        return evidence
