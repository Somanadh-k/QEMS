from datetime import date, datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

EMBEDDING_DIM = 1536  # text-embedding-3-small


class Severity(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ErrorStatus(StrEnum):
    OPEN = "Open"
    IN_REVIEW = "In Review"
    REBUTTAL_RAISED = "Rebuttal Raised"
    QA_DECISION_PENDING = "QA Decision Pending"
    RESOLVED = "Resolved"
    REJECTED = "Rejected"
    CLOSED = "Closed"


class Error(Base):
    """Core QA error record — the central entity (Section 8.3/8.4)."""

    __tablename__ = "errors"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('Low','Medium','High','Critical')", name="ck_errors_severity"
        ),
        Index("idx_errors_status", "status"),
        Index("idx_errors_department", "department_id"),
        Index("idx_errors_due_at", "due_at"),
    )

    error_id: Mapped[int] = mapped_column(primary_key=True)
    qa_error_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.category_id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=ErrorStatus.OPEN)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id"), nullable=False)
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    date_discovered: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[datetime | None]

    # Not in the original report's DDL — added so AI similarity search (Section 13.2) has
    # somewhere to persist the OpenAI embedding computed at creation time.
    description_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    category: Mapped["Category"] = relationship()
    department: Mapped["Department"] = relationship()
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="error", cascade="all, delete-orphan")
    rebuttals: Mapped[list["Rebuttal"]] = relationship(back_populates="error", cascade="all, delete-orphan")
    decisions: Mapped[list["QADecision"]] = relationship(back_populates="error", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="error")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="error")
