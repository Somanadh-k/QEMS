"""Phase 0 substrate: AI provenance ledger, audit hash chain, HNSW index.

Revision ID: a1b2c3d4e5f6
Revises: d650696750e8
Create Date: 2026-09-05

Nothing user-visible ships here. This is the substrate every later phase writes to:
without an insights table AI output cannot be traceable, and without actor_type a
scheduled worker cannot write an audit row at all.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "d650696750e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- AI provenance -------------------------------------------------------
    op.create_table(
        "ai_prompt_versions",
        sa.Column("version", sa.String(60), primary_key=True),
        sa.Column("insight_type", sa.String(30), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "ai_insights",
        sa.Column("insight_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("error_id", sa.Integer(), sa.ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=True),
        sa.Column("insight_type", sa.String(30), nullable=False),
        sa.Column("model_name", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(60), sa.ForeignKey("ai_prompt_versions.version"), nullable=True),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("retrieved_error_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("risk_band", sa.String(10), nullable=True),
        sa.Column("ai_output", postgresql.JSONB(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 5), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="FRESH"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_action", sa.String(30), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.CheckConstraint("risk_band IS NULL OR risk_band IN ('LOW','MEDIUM','HIGH')", name="ck_insight_risk_band"),
        sa.CheckConstraint(
            "reviewer_action IS NULL OR reviewer_action IN "
            "('ACCEPTED','PARTIALLY_ACCEPTED','REJECTED','NO_ACTION')",
            name="ck_insight_reviewer_action",
        ),
    )
    op.create_index("idx_insight_error_type", "ai_insights", ["error_id", "insight_type"])
    op.create_index("idx_insight_fingerprint", "ai_insights", ["input_fingerprint"])
    # One live insight per (error, type). Recompute supersedes; it never overwrites.
    op.create_index(
        "ux_insight_fresh", "ai_insights", ["error_id", "insight_type"],
        unique=True, postgresql_where=sa.text("status = 'FRESH'"),
    )

    op.create_table(
        "ai_cost_ledger",
        sa.Column("ledger_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("model_name", sa.String(80), nullable=False),
        sa.Column("call_type", sa.String(20), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 5), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurred_on", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_cost_day_feature", "ai_cost_ledger", ["occurred_on", "feature"])

    # --- Audit trail hardening ----------------------------------------------
    op.add_column("audit_logs", sa.Column("actor_type", sa.String(20), nullable=False, server_default="USER"))
    op.add_column("audit_logs", sa.Column("reason", sa.String(500), nullable=True))
    op.add_column("audit_logs", sa.Column("request_id", sa.String(36), nullable=True))
    op.add_column("audit_logs", sa.Column("insight_id", sa.BigInteger(), nullable=True))
    op.add_column("audit_logs", sa.Column("prev_hash", sa.String(64), nullable=True))
    op.add_column("audit_logs", sa.Column("row_hash", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_audit_insight", "audit_logs", "ai_insights", ["insight_id"], ["insight_id"]
    )
    # A system actor has no user row to point at.
    op.alter_column("audit_logs", "actor_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_audit_actor_type", "audit_logs", "actor_type IN ('USER','SYSTEM','SYSTEM_AI')"
    )
    op.create_check_constraint(
        "ck_audit_user_has_actor",
        "audit_logs",
        "(actor_type = 'USER' AND actor_id IS NOT NULL) OR actor_type <> 'USER'",
    )
    op.create_index("idx_audit_created", "audit_logs", ["created_at"])

    # --- Vector index (finding F-05) ----------------------------------------
    # Without this every similarity query sequentially scans every embedding.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_errors_embedding ON errors "
        "USING hnsw (description_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_errors_embedding")
    op.drop_index("idx_audit_created", table_name="audit_logs")
    op.drop_constraint("ck_audit_user_has_actor", "audit_logs", type_="check")
    op.drop_constraint("ck_audit_actor_type", "audit_logs", type_="check")
    op.alter_column("audit_logs", "actor_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_audit_insight", "audit_logs", type_="foreignkey")
    for col in ("row_hash", "prev_hash", "insight_id", "request_id", "reason", "actor_type"):
        op.drop_column("audit_logs", col)
    op.drop_index("idx_cost_day_feature", table_name="ai_cost_ledger")
    op.drop_table("ai_cost_ledger")
    for ix in ("ux_insight_fresh", "idx_insight_fingerprint", "idx_insight_error_type"):
        op.drop_index(ix, table_name="ai_insights")
    op.drop_table("ai_insights")
    op.drop_table("ai_prompt_versions")
