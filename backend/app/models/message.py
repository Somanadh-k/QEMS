from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MessageType(StrEnum):
    TEXT = "TEXT"
    EVIDENCE_REQUEST = "EVIDENCE_REQUEST"
    EVIDENCE_UPLOAD = "EVIDENCE_UPLOAD"
    STATUS_NOTE = "STATUS_NOTE"


class Message(Base):
    """A single entry in a QA Error's conversation thread (Feature 1).

    Scoped permanently to one error (error_id, CASCADE) -- there is no endpoint that lets
    a message exist outside that context, by design (spec: "do not allow users to
    communicate outside the context of a QEMS error").
    """

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('TEXT','EVIDENCE_REQUEST','EVIDENCE_UPLOAD','STATUS_NOTE')",
            name="ck_messages_type",
        ),
        Index("idx_messages_error", "error_id", "created_at"),
        Index("idx_messages_parent", "parent_message_id"),
    )

    message_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int] = mapped_column(ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    parent_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.message_id", ondelete="SET NULL"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Drives the derived communication status (message_service.compute_communication_status)
    # without a second, unrelated workflow/state-machine on top of the error's own.
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, default=MessageType.TEXT)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    error: Mapped["Error"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship()
    attachments: Mapped[list["MessageAttachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    __table_args__ = (Index("idx_message_attachments_message", "message_id"),)

    attachment_id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.message_id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    # Opaque storage key (never the client filename), same convention as Evidence.storage_key.
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    message: Mapped["Message"] = relationship(back_populates="attachments")
