from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditLog(Base):
    """Append-only history of all state changes (Section 8.3/14.4). Never updated or deleted."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_error", "error_id"),)

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    error_id: Mapped[int | None] = mapped_column(ForeignKey("errors.error_id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    before_value: Mapped[dict | None] = mapped_column(JSONB)
    after_value: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    error: Mapped["Error | None"] = relationship(back_populates="audit_logs")
