import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Notification
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger("qems.notification")
settings = get_settings()


def _send_smtp_sync(to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


class NotificationService:
    """Dispatches stakeholder notifications (Section 4.7).

    Sends real SMTP email via a local Mailpit instance in dev (view at
    http://localhost:8025) — swap SMTP_HOST/PORT/credentials in .env for a real
    transactional email provider (SendGrid/Resend/etc.) in production; no code change needed.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)
        self.users = UserRepository(db)

    async def notify(
        self, recipient_id: int, subject: str, error_id: int | None = None, body: str | None = None
    ) -> Notification:
        notification = Notification(
            error_id=error_id,
            recipient_id=recipient_id,
            channel="email",
            subject=subject,
            status="Pending",
        )
        await self.repo.add(notification)
        try:
            await self._send_email(recipient_id, subject, body or subject)
            notification.status = "Sent"
            notification.sent_at = datetime.now(timezone.utc)
        except OSError:
            logger.exception("Failed to send notification email to user_id=%s", recipient_id)
            notification.status = "Failed"
        return notification

    async def _send_email(self, recipient_id: int, subject: str, body: str) -> None:
        recipient = await self.users.get_by_id(recipient_id)
        if recipient is None:
            logger.warning("Notification recipient user_id=%s not found; skipping send", recipient_id)
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_smtp_sync, recipient.email, subject, body)
        logger.info("Sent email to %s subject=%r", recipient.email, subject)
