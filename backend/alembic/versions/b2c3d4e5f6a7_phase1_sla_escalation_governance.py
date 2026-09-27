"""Phase 1: SLA matrix, escalation engine, transition ledger, risk score.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6

Fixes finding F-01. Every seeded category pointed at sla_policy_id=3 (Medium/72h), and
the lookup joined categories->sla_policies without filtering on severity, so a Critical
error and a Low error both received 72 hours. The severity-keyed budgets in the old
table were never read. This migration carries those budgets into a real matrix and makes
severity the primary lookup dimension.

Backfill policy: existing errors keep their current due_at and are seeded ON_TRACK. A
migration that retro-breaches historical work opens day one with a wall of red rows and
destroys trust in the number permanently.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- process dimension ---------------------------------------------------
    op.create_table(
        "processes",
        sa.Column("process_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.department_id")),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # --- business calendars --------------------------------------------------
    op.create_table(
        "business_calendars",
        sa.Column("calendar_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("timezone", sa.String(60), nullable=False, server_default="UTC"),
        sa.Column("workday_start", sa.Time(), nullable=False),
        sa.Column("workday_end", sa.Time(), nullable=False),
        sa.Column("workdays", postgresql.ARRAY(sa.Integer()), nullable=False),
    )
    op.create_table(
        "calendar_holidays",
        sa.Column("calendar_id", sa.Integer(),
                  sa.ForeignKey("business_calendars.calendar_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("holiday_date", sa.Date(), primary_key=True),
        sa.Column("name", sa.String(120)),
    )

    # --- SLA matrix ----------------------------------------------------------
    op.create_table(
        "sla_matrix",
        sa.Column("sla_id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.category_id")),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.department_id")),
        sa.Column("severity", sa.String(20)),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("budget_hours", sa.Numeric(6, 2), nullable=False),
        sa.Column("business_hours_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("calendar_id", sa.Integer(), sa.ForeignKey("business_calendars.calendar_id")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.CheckConstraint("budget_hours > 0", name="ck_sla_matrix_budget_positive"),
        sa.CheckConstraint("stage IN ('RESPOND','REBUT','DECIDE','CLOSE')", name="ck_sla_matrix_stage"),
    )
    op.create_index("idx_sla_matrix_lookup", "sla_matrix", ["severity", "stage", "effective_from"])

    op.create_table(
        "sla_events",
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column("error_id", sa.Integer(), sa.ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner_role", sa.String(50)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("sla_id", sa.Integer(), sa.ForeignKey("sla_matrix.sla_id")),
    )
    op.create_index("idx_sla_events_error", "sla_events", ["error_id", "occurred_at"])

    # --- escalation ----------------------------------------------------------
    op.create_table(
        "escalation_rules",
        sa.Column("rule_id", sa.Integer(), primary_key=True),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("severity_min", sa.String(20)),
        sa.Column("target_role", sa.String(50)),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="720"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("trigger IN ('AT_RISK','BREACH','LEVEL_TIMEOUT')", name="ck_escalation_trigger"),
    )
    op.create_table(
        "escalations",
        sa.Column("escalation_id", sa.Integer(), primary_key=True),
        sa.Column("error_id", sa.Integer(), sa.ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("escalation_rules.rule_id"), nullable=False),
        sa.Column("escalated_to", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("next_action", sa.Text()),
        sa.Column("eta", sa.DateTime(timezone=True)),
        # Idempotency: a worker replaying a missed window cannot re-fire the same escalation.
        sa.UniqueConstraint("error_id", "level", "rule_id", name="ux_escalation_once"),
    )
    op.create_index("idx_escalation_open", "escalations", ["acknowledged_at"])

    # --- transition ledger ---------------------------------------------------
    op.create_table(
        "error_transitions",
        sa.Column("transition_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("error_id", sa.Integer(), sa.ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="USER"),
        sa.Column("reason", sa.Text()),
        sa.Column("rule_applied", sa.String(60)),
        sa.Column("round_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_transition_error", "error_transitions", ["error_id", "occurred_at"])

    # --- errors: governance columns -----------------------------------------
    op.add_column("errors", sa.Column("embedding_model", sa.String(60)))
    op.add_column("errors", sa.Column("embedded_at", sa.DateTime(timezone=True)))
    op.add_column("errors", sa.Column("embedding_source_hash", sa.String(64)))
    op.add_column("errors", sa.Column("process_id", sa.Integer(), sa.ForeignKey("processes.process_id")))
    op.add_column("errors", sa.Column("sla_state", sa.String(20), nullable=False, server_default="ON_TRACK"))
    op.add_column("errors", sa.Column("sla_stage", sa.String(20)))
    op.add_column("errors", sa.Column("sla_due_at", sa.DateTime(timezone=True)))
    op.add_column("errors", sa.Column("sla_clock_owner_role", sa.String(50)))
    op.add_column("errors", sa.Column("sla_paused_ms", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("errors", sa.Column("escalation_level", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("errors", sa.Column("risk_score", sa.Numeric(5, 2)))
    op.add_column("errors", sa.Column("risk_score_breakdown", postgresql.JSONB()))
    op.add_column("errors", sa.Column("risk_computed_at", sa.DateTime(timezone=True)))
    op.add_column("errors", sa.Column("round_no", sa.SmallInteger(), nullable=False, server_default="1"))
    op.create_index("idx_errors_governance", "errors", ["sla_state", "risk_score"])
    op.create_index("idx_errors_recurrence", "errors", ["category_id", "process_id", "created_at"])

    # --- seed: calendar, matrix carried over from sla_policies, escalation rules ---
    op.execute(
        "INSERT INTO business_calendars (name, timezone, workday_start, workday_end, workdays) "
        "VALUES ('Default 9-5 Mon-Fri', 'UTC', '09:00', '17:00', '{1,2,3,4,5}')"
    )
    # Carry the severity budgets that the old table held but never applied. RESPOND and
    # DECIDE split the original single budget; REBUT gets the same window as RESPOND.
    op.execute(
        """
        INSERT INTO sla_matrix (severity, stage, budget_hours, business_hours_only,
                                calendar_id, effective_from)
        SELECT p.severity, s.stage,
               ROUND(p.sla_hours * s.share, 2), true,
               (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'),
               -- Backdated deliberately. These budgets were already in force via
               -- sla_policies; stamping them as effective from the migration date would
               -- leave every pre-existing error with no governing policy, which the
               -- evaluator would then read as permanently ON_TRACK.
               TIMESTAMPTZ '2000-01-01 00:00:00+00'
        FROM sla_policies p
        CROSS JOIN (VALUES ('RESPOND', 0.3), ('REBUT', 0.3), ('DECIDE', 0.3), ('CLOSE', 0.1))
                   AS s(stage, share)
        """
    )
    op.execute(
        """
        INSERT INTO escalation_rules (trigger, level, severity_min, target_role, channel, cooldown_minutes)
        VALUES ('BREACH', 1, NULL, 'QA Reviewer', 'email', 720),
               ('LEVEL_TIMEOUT', 2, 'High', 'Admin', 'email', 1440)
        """
    )
    # Backfill: preserve existing deadlines, never retro-breach.
    op.execute("UPDATE errors SET sla_due_at = due_at, sla_stage = 'RESPOND', sla_state = 'ON_TRACK'")


def downgrade() -> None:
    op.drop_index("idx_errors_recurrence", table_name="errors")
    op.drop_index("idx_errors_governance", table_name="errors")
    for col in ("round_no", "risk_computed_at", "risk_score_breakdown", "risk_score",
                "escalation_level", "sla_paused_ms", "sla_clock_owner_role", "sla_due_at",
                "sla_stage", "sla_state", "process_id", "embedding_source_hash",
                "embedded_at", "embedding_model"):
        op.drop_column("errors", col)
    op.drop_index("idx_transition_error", table_name="error_transitions")
    op.drop_table("error_transitions")
    op.drop_index("idx_escalation_open", table_name="escalations")
    op.drop_table("escalations")
    op.drop_table("escalation_rules")
    op.drop_index("idx_sla_events_error", table_name="sla_events")
    op.drop_table("sla_events")
    op.drop_index("idx_sla_matrix_lookup", table_name="sla_matrix")
    op.drop_table("sla_matrix")
    op.drop_table("calendar_holidays")
    op.drop_table("business_calendars")
    op.drop_table("processes")
