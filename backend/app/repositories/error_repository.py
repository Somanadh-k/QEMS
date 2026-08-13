from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Error


class ErrorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _detail_query(self):
        return select(Error).options(
            selectinload(Error.evidence),
            selectinload(Error.rebuttals),
            selectinload(Error.decisions),
            selectinload(Error.category),
            selectinload(Error.department),
        )

    async def get_by_id(self, error_id: int) -> Error | None:
        result = await self.db.execute(self._detail_query().where(Error.error_id == error_id))
        return result.scalar_one_or_none()

    async def list(
        self,
        status: str | None = None,
        department_id: int | None = None,
        severity: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Error], int]:
        query = select(Error)
        count_query = select(func.count()).select_from(Error)
        if status:
            query = query.where(Error.status == status)
            count_query = count_query.where(Error.status == status)
        if department_id:
            query = query.where(Error.department_id == department_id)
            count_query = count_query.where(Error.department_id == department_id)
        if severity:
            query = query.where(Error.severity == severity)
            count_query = count_query.where(Error.severity == severity)

        query = query.order_by(Error.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

        total = (await self.db.execute(count_query)).scalar_one()
        rows = (await self.db.execute(query)).scalars().all()
        return list(rows), total

    async def add(self, error: Error) -> Error:
        self.db.add(error)
        await self.db.flush()
        return error

    async def find_similar_closed(
        self, embedding: list[float], exclude_error_id: int, limit: int = 5
    ) -> list[Error]:
        """Top-N historically similar *closed* errors via pgvector cosine distance (Section 13.2)."""
        distance = Error.description_embedding.cosine_distance(embedding)
        result = await self.db.execute(
            select(Error)
            .where(
                Error.status == "Closed",
                Error.description_embedding.isnot(None),
                Error.error_id != exclude_error_id,
            )
            .order_by(distance)
            .limit(limit)
        )
        return list(result.scalars().all())
