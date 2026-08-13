from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


class AuditLogRepository:
    """Append-only: no update/delete methods exist on this repository by design (Section 14.4)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        actor_id: int,
        action: str,
        error_id: int | None = None,
        before_value: dict | None = None,
        after_value: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            error_id=error_id,
            actor_id=actor_id,
            action=action,
            before_value=before_value,
            after_value=after_value,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
