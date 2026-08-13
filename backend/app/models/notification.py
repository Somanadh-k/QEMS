from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int | None] = mapped_column(ForeignKey("errors.error_id"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    sent_at: Mapped[datetime | None]

    error: Mapped["Error | None"] = relationship(back_populates="notifications")
