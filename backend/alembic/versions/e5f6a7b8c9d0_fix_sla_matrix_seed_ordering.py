"""Fix SLA matrix seed depending on sla_policies, which isn't populated yet at migrate time.

Migration b2c3d4e5f6a7 seeds `sla_matrix` via `INSERT ... SELECT ... FROM sla_policies`,
but `sla_policies` is only ever populated by `app.tasks.seed`, which the project's own
documented setup order (README: "alembic upgrade head" then "python -m app.tasks.seed")
runs *after* migrations. On any environment that follows that order from a clean
database, `sla_policies` is empty when b2c3d4e5f6a7 runs, so its cross join produces
zero sla_matrix rows -- confirmed by a full local re-seed, which left every governance
test (test_sla_engine.py, test_sla_worker.py) failing with "No SLA policy exists...".

The long-lived dev database this was authored against never hit this, because
`app.tasks.seed` had already been run against it earlier in its history before
b2c3d4e5f6a7 was written and applied -- an ordering that happened to work by accident of
that one database's history, not something the documented setup order (or a fresh
install, or CI) actually guarantees.

Fix: insert the same 16 rows (4 severities x 4 stages) using the literal severity/hours
figures migration b2c3d4e5f6a7's comment already names (matching app.tasks.seed's
DEFAULT_SLA_POLICIES), rather than reading them from a table that may not exist yet.
Guarded so it's a no-op if sla_matrix already has rows (e.g. re-running against a
database where b2c3d4e5f6a7's original cross join did work).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

# (severity, budget_hours) -- matches app.tasks.seed.DEFAULT_SLA_POLICIES
SEVERITY_HOURS = [("Critical", 4), ("High", 24), ("Medium", 72), ("Low", 168)]
# (stage, share) -- matches migration b2c3d4e5f6a7's original cross join
STAGE_SHARES = [("RESPOND", 0.3), ("REBUT", 0.3), ("DECIDE", 0.3), ("CLOSE", 0.1)]


def upgrade() -> None:
    already_seeded = op.get_bind().execute(
        __import__("sqlalchemy").text("SELECT count(*) FROM sla_matrix")
    ).scalar_one()
    if already_seeded:
        return

    values = ", ".join(
        f"('{severity}', '{stage}', {round(hours * share, 2)}, true, "
        "(SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), "
        "TIMESTAMPTZ '2000-01-01 00:00:00+00')"
        for severity, hours in SEVERITY_HOURS
        for stage, share in STAGE_SHARES
    )
    op.execute(
        "INSERT INTO sla_matrix (severity, stage, budget_hours, business_hours_only, "
        f"calendar_id, effective_from) VALUES {values}"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM sla_matrix WHERE effective_from = TIMESTAMPTZ '2000-01-01 00:00:00+00'"
    )
