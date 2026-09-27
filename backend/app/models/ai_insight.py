"""AI provenance ledger (proposal PRV-03).

Every inference the system performs writes a row here before its output is shown to
anyone. This is what makes the design principle "every AI recommendation must be
traceable" enforceable rather than aspirational: the model, the prompt version, the
exact inputs, the exact historical errors retrieved, the cost, and the reviewer's
eventual disposition are all recoverable months later.

Rows are never updated in place. A recompute writes a new row and marks the old one
SUPERSEDED, so the record of what was actually shown at decision time survives.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class InsightType(StrEnum):
    RECURRENCE = "RECURRENCE"
    REBUTTAL = "REBUTTAL"
    CONSISTENCY = "CONSISTENCY"
    ROOT_CAUSE = "ROOT_CAUSE"
    SEVERITY = "SEVERITY"
    REPORT_SUMMARY = "REPORT_SUMMARY"


class InsightStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"           # source text changed after the insight was produced
    SUPERSEDED = "SUPERSEDED"  # a newer insight of the same type replaced it
    DEGRADED = "DEGRADED"      # deterministic metrics valid, model output unavailable
    FAILED = "FAILED"


class ReviewerAction(StrEnum):
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"
    NO_ACTION = "NO_ACTION"


class RiskBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AIPromptVersion(Base):
    """Immutable prompt text, referenced by every insight it produced.

    Editing a prompt creates a new version; it never mutates an existing one. Without
    this, a prompt change silently rewrites the meaning of every historical insight.
    """

    __tablename__ = "ai_prompt_versions"

    version: Mapped[str] = mapped_column(String(60), primary_key=True)
    insight_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    retired_at: Mapped[datetime | None]


class AIInsight(Base):
    __tablename__ = "ai_insights"
    __table_args__ = (
        CheckConstraint(
            "risk_band IS NULL OR risk_band IN ('LOW','MEDIUM','HIGH')",
            name="ck_insight_risk_band",
        ),
        CheckConstraint(
            "reviewer_action IS NULL OR reviewer_action IN "
            "('ACCEPTED','PARTIALLY_ACCEPTED','REJECTED','NO_ACTION')",
            name="ck_insight_reviewer_action",
        ),
        Index("idx_insight_error_type", "error_id", "insight_type"),
        Index("idx_insight_fingerprint", "input_fingerprint"),
        # At most one live insight of each type per error. A recompute supersedes the
        # previous row rather than overwriting it.
        Index(
            "ux_insight_fresh",
            "error_id",
            "insight_type",
            unique=True,
            postgresql_where=text("status = 'FRESH'"),
        ),
    )

    insight_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    error_id: Mapped[int | None] = mapped_column(
        ForeignKey("errors.error_id", ondelete="CASCADE")
    )
    insight_type: Mapped[str] = mapped_column(String(30), nullable=False)

    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(
        ForeignKey("ai_prompt_versions.version")
    )
    # sha256 of the exact inputs: doubles as the cache key and as reproducibility proof.
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Exactly which historical errors the model was shown — not "similar ones", these ones.
    retrieved_error_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))

    # Facts computed in SQL. The model never produces these.
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    risk_band: Mapped[str | None] = mapped_column(String(10))

    # Narrative only. NULL when the model was unavailable — metrics above stay valid.
    ai_output: Mapped[dict | None] = mapped_column(JSONB)

    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 5))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=InsightStatus.FRESH)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Human disposition. A rejection with a reason is the most valuable row in this table.
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    reviewed_at: Mapped[datetime | None]
    reviewer_action: Mapped[str | None] = mapped_column(String(30))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)

    error: Mapped["Error | None"] = relationship(back_populates="insights")


class AICostLedger(Base):
    """Per-call spend, so the AI budget is observable and cappable per feature."""

    __tablename__ = "ai_cost_ledger"
    __table_args__ = (Index("idx_cost_day_feature", "occurred_on", "feature"),)

    ledger_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    call_type: Mapped[str] = mapped_column(String(20), nullable=False)  # embedding | chat
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 5), nullable=False, default=0)
    cache_hit: Mapped[bool] = mapped_column(nullable=False, default=False)
    occurred_on: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
