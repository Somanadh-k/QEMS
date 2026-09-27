from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("idx_evidence_error", "error_id"),)

    evidence_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int] = mapped_column(ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Opaque object key, never derived from the client-supplied filename.
    storage_key: Mapped[str | None] = mapped_column(String(300))
    # Content hash captured at upload, so a swapped file is provable rather than deniable.
    sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_class: Mapped[str | None] = mapped_column(String(40))
    retention_until: Mapped[datetime | None]

    error: Mapped["Error"] = relationship(back_populates="evidence")


class EvidenceAccessLog(Base):
    """Every read of an evidence file. Access that is possible but unrecorded is not
    controlled access — this is what makes the chain of custody real."""

    __tablename__ = "evidence_access_log"
    __table_args__ = (Index("idx_evidence_access", "evidence_id", "accessed_at"),)

    access_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence.evidence_id", ondelete="CASCADE"), nullable=False
    )
    accessed_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    accessed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
