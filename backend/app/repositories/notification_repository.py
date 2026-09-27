from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationLog, NotificationTemplate


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, notification: Notification) -> Notification:
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def add_log(self, log: NotificationLog) -> NotificationLog:
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_by_id(self, notification_id: int) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(Notification.notification_id == notification_id)
        )
        return result.scalar_one_or_none()

    async def list_by_error(self, error_id: int) -> list[Notification]:
        result = await self.db.execute(
            select(Notification).where(Notification.error_id == error_id).order_by(Notification.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_unread_for_recipient(self, recipient_id: int) -> int:
        result = await self.db.execute(
            select(Notification).where(
                Notification.recipient_id == recipient_id, Notification.read_at.is_(None)
            )
        )
        return len(result.scalars().all())

    async def list_retryable(self, now: datetime, max_retries: int) -> list[Notification]:
        """Failed notifications still within the retry budget and past their backoff."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.status == "FAILED",
                Notification.retry_count < max_retries,
                (Notification.next_retry_at.is_(None)) | (Notification.next_retry_at <= now),
            )
        )
        return list(result.scalars().all())

    async def exists_for_event(self, error_id: int, event_type: str) -> bool:
        """Used to de-duplicate DEADLINE_APPROACHING/ERROR_OVERDUE -- these fire once per
        error, not once per scheduler tick."""
        result = await self.db.execute(
            select(Notification.notification_id).where(
                Notification.error_id == error_id, Notification.event_type == event_type
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None


class NotificationTemplateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_event(self, event_type: str) -> NotificationTemplate | None:
        result = await self.db.execute(
            select(NotificationTemplate).where(NotificationTemplate.event_type == event_type)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, template_id: int) -> NotificationTemplate | None:
        result = await self.db.execute(
            select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[NotificationTemplate]:
        result = await self.db.execute(select(NotificationTemplate).order_by(NotificationTemplate.event_type))
        return list(result.scalars().all())
