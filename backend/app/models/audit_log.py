"""Append-only history of all state changes (proposal section 13).

Three properties make this defensible to someone who is not obliged to trust us:

1. `actor_type` — a scheduled job or an AI worker can log honestly instead of
   impersonating a person. Previously `actor_id` was NOT NULL against `users`, so a
   system action had no legal way to be recorded at all.
2. `prev_hash` / `row_hash` — each row hashes its own content plus its predecessor.
   This does not prevent tampering; it makes tampering *detectable*, which is the
   property an auditor actually asks for. Verify with GET /api/v1/audit/verify.
3. `insight_id` — AI-attributed rows join straight to the recommendation that
   produced them, so "what did the system say and what did the human do" is one query.
"""

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ActorType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"        # scheduled workers: SLA ticks, nightly governance
    SYSTEM_AI = "SYSTEM_AI"  # anything whose content came from a model


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('USER','SYSTEM','SYSTEM_AI')", name="ck_audit_actor_type"
        ),
        # A human actor must be identified; system actors legitimately have none.
        CheckConstraint(
            "(actor_type = 'USER' AND actor_id IS NOT NULL) OR actor_type <> 'USER'",
            name="ck_audit_user_has_actor",
        ),
        Index("idx_audit_error", "error_id"),
        Index("idx_audit_created", "created_at"),
    )

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    error_id: Mapped[int | None] = mapped_column(ForeignKey("errors.error_id"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ActorType.USER)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    before_value: Mapped[dict | None] = mapped_column(JSONB)
    after_value: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(String(500))
    request_id: Mapped[str | None] = mapped_column(String(36))
    insight_id: Mapped[int | None] = mapped_column(ForeignKey("ai_insights.insight_id"))

    prev_hash: Mapped[str | None] = mapped_column(String(64))
    row_hash: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    error: Mapped["Error | None"] = relationship(back_populates="audit_logs")

    def compute_hash(self, prev_hash: str | None, created_at: datetime) -> str:
        """SHA-256 over this row's content plus its predecessor's hash.

        `created_at` is passed explicitly because the DB server default is not populated
        on the Python object until after flush; the chain must hash the value that is
        actually stored.
        """
        payload = json.dumps(
            {
                "error_id": self.error_id,
                "actor_id": self.actor_id,
                "actor_type": self.actor_type,
                "action": self.action,
                "before_value": self.before_value,
                "after_value": self.after_value,
                "reason": self.reason,
                "insight_id": self.insight_id,
                "created_at": created_at.isoformat(),
                "prev_hash": prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()
