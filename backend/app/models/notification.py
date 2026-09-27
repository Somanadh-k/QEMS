from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class NotificationEvent(StrEnum):
    ERROR_CREATED = "ERROR_CREATED"
    ERROR_ASSIGNED = "ERROR_ASSIGNED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    REBUTTAL_SUBMITTED = "REBUTTAL_SUBMITTED"
    EVIDENCE_REQUESTED = "EVIDENCE_REQUESTED"
    DECISION_UPDATED = "DECISION_UPDATED"
    DEADLINE_APPROACHING = "DEADLINE_APPROACHING"
    ERROR_OVERDUE = "ERROR_OVERDUE"
    ERROR_RESOLVED = "ERROR_RESOLVED"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    READ = "READ"


class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int | None] = mapped_column(ForeignKey("errors.error_id"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=NotificationStatus.PENDING)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    error: Mapped["Error | None"] = relationship(back_populates="notifications")
    logs: Mapped[list["NotificationLog"]] = relationship(back_populates="notification", cascade="all, delete-orphan")


class NotificationTemplate(Base):
    """Configurable per-event Gmail (and future channel) template.

    `{{var}}` placeholders are substituted by app.services.notification_templates.render.
    Disabling a template does not disable the event -- the dispatcher falls back to a
    minimal deterministic subject/body so delivery never silently stops.
    """

    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    subject_template: Mapped[str] = mapped_column(String(300), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class NotificationLog(Base):
    """One row per delivery *attempt* -- a notification retried 3 times has 3 log rows.

    This is what makes "never silently swallow email failures" auditable: the
    Notification row shows only the latest state, this table shows the whole history.
    """

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.notification_id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    notification: Mapped["Notification"] = relationship(back_populates="logs")
