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

        # Governance queue ordering: highest risk first, newest as the tie-break. QA
        # capacity should go to the highest-risk work by default rather than by accident.
        query = (
            query.order_by(Error.risk_score.desc().nullslast(), Error.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

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
        """Top-N historically similar *closed* errors (kept for the existing /ai routes)."""
        neighbours = await self.find_neighbours(
            embedding, exclude_error_id=exclude_error_id, limit=limit, closed_only=True
        )
        return [n[0] for n in neighbours]

    async def find_neighbours(
        self,
        embedding: list[float],
        *,
        exclude_error_id: int | None = None,
        limit: int = 20,
        max_distance: float | None = None,
        department_ids: list[int] | None = None,
        embedding_model: str | None = None,
        closed_only: bool = False,
    ) -> list[tuple[Error, float]]:
        """Nearest neighbours with their cosine distance.

        Three things the previous implementation could not do, each of which finding F-05
        identified as blocking recurrence detection:

        * **Returns the distance.** Without it the caller cannot tell a genuine match
          from the nearest of five unrelated rows, and every threshold is guesswork.
        * **Applies a distance ceiling.** The old query always returned five rows even
          when nothing was similar.
        * **Includes open errors.** A defect recurring *right now* is exactly what makes
          it recurring; restricting to Closed hid the live pattern.

        `department_ids` scopes retrieval to what the caller may see. Nearest-neighbour
        search ignores authorisation boundaries by default, so without this a reviewer in
        one department would read another department's finding titles.
        """
        distance = Error.description_embedding.cosine_distance(embedding).label("distance")
        query = select(Error, distance).where(Error.description_embedding.isnot(None))

        if exclude_error_id is not None:
            query = query.where(Error.error_id != exclude_error_id)
        if closed_only:
            query = query.where(Error.status == "Closed")
        if department_ids is not None:
            query = query.where(Error.department_id.in_(department_ids))
        if embedding_model is not None:
            # Never compare vectors produced by different models: the distances are not
            # on the same scale and the comparison is meaningless rather than merely noisy.
            query = query.where(Error.embedding_model == embedding_model)
        if max_distance is not None:
            query = query.where(distance <= max_distance)

        rows = (await self.db.execute(query.order_by(distance).limit(limit))).all()
        return [(row[0], float(row[1])) for row in rows]
