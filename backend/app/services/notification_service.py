"""Centralised, event-driven notification dispatch (Feature 2).

    QEMS event -> dispatch_event() -> template/AI render -> provider.send() -> recipient

Nothing else in the codebase talks to smtplib or the Gmail API directly -- error_service.py,
message_service.py and workers/scheduler.py only ever call `dispatch_event` with one of
`NotificationEvent`'s members. That is what keeps Gmail calls out of business logic and
makes adding a channel (WhatsApp/Teams/Slack/SMS) a new `NotificationProvider`, not a
grep-and-edit across the app.

Failure handling: a send failure never raises out of `dispatch_event` -- the calling
transaction (e.g. ErrorService.create_error) must succeed regardless of whether Gmail is
reachable. The notification row is left FAILED with a `next_retry_at`, and
workers/scheduler.py:run_notification_retry_tick retries it later with exponential
backoff, up to `settings.notification_max_retries` attempts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Notification, NotificationLog, NotificationStatus
from app.repositories.notification_repository import NotificationRepository, NotificationTemplateRepository
from app.repositories.user_repository import UserRepository
from app.services.ai_notification_service import narrate
from app.services.notification_providers import GmailProvider, NotificationSendError, SmtpProvider
from app.services.notification_templates import render

if TYPE_CHECKING:
    from app.models import Error

logger = logging.getLogger("qems.notification")
settings = get_settings()


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)
        self.templates = NotificationTemplateRepository(db)
        self.users = UserRepository(db)

    async def dispatch_event(
        self,
        event: str,
        *,
        recipient_id: int,
        error: "Error | None" = None,
        context: dict | None = None,
    ) -> Notification:
        ctx = dict(context or {})
        if error is not None:
            ctx.setdefault("error_id", error.qa_error_code)
            ctx.setdefault("qems_url", f"{settings.app_base_url.rstrip('/')}/errors/{error.error_id}")

        subject, body = await self._render(event, ctx)

        notification = Notification(
            error_id=error.error_id if error is not None else None,
            recipient_id=recipient_id,
            event_type=event,
            channel="email",
            subject=subject,
            content=body,
            status=NotificationStatus.PENDING,
        )
        await self.repo.add(notification)
        await self._attempt_send(notification)
        return notification

    async def _render(self, event: str, context: dict) -> tuple[str, str]:
        try:
            ai_result = await narrate(event, context)
        except Exception:  # noqa: BLE001 -- AI copy is best-effort, never blocks delivery
            logger.exception("AI notification narration raised unexpectedly")
            ai_result = None
        if ai_result:
            return ai_result

        template = await self.templates.get_by_event(event)
        if template is not None and template.enabled:
            return render(template.subject_template, context), render(template.body_template, context)

        # Deterministic last resort if the template was disabled or somehow missing --
        # delivery must never depend on the templates table having the "right" row.
        error_id = context.get("error_id", "")
        return f"QEMS notification: {event} {error_id}".strip(), (
            context.get("message") or f"Event {event} occurred on {error_id}."
        )

    async def _attempt_send(self, notification: Notification) -> None:
        recipient = await self.users.get_by_id(notification.recipient_id)
        if recipient is None:
            logger.warning("Notification recipient user_id=%s not found; skipping send", notification.recipient_id)
            notification.status = NotificationStatus.FAILED
            await self.repo.add_log(
                NotificationLog(
                    notification_id=notification.notification_id,
                    provider="none",
                    status=NotificationStatus.FAILED,
                    error_message="recipient not found",
                )
            )
            return

        provider = GmailProvider() if GmailProvider.is_configured() else SmtpProvider()
        try:
            provider_message_id = await provider.send(
                recipient.email, notification.subject, notification.content or notification.subject
            )
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.now(timezone.utc)
            await self.repo.add_log(
                NotificationLog(
                    notification_id=notification.notification_id,
                    provider=provider.name,
                    provider_message_id=provider_message_id,
                    status=NotificationStatus.SENT,
                )
            )
        except NotificationSendError as exc:
            logger.warning("Notification %s send failed via %s: %s", notification.notification_id, provider.name, exc)
            notification.status = NotificationStatus.FAILED
            notification.next_retry_at = self._next_retry_at(notification.retry_count)
            await self.repo.add_log(
                NotificationLog(
                    notification_id=notification.notification_id,
                    provider=provider.name,
                    status=NotificationStatus.FAILED,
                    error_message=str(exc)[:2000],
                )
            )

    @staticmethod
    def _next_retry_at(retry_count: int) -> datetime:
        # ponytail: fixed exponential backoff (2^n minutes), capped implicitly by
        # settings.notification_max_retries -- a jittered/configurable schedule would be
        # overkill for this volume of traffic.
        backoff_minutes = 2 ** max(retry_count, 1)
        return datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)

    async def retry(self, notification: Notification) -> None:
        notification.retry_count += 1
        await self._attempt_send(notification)
