"""Widen ux_escalation_once to include escalated_to.

A rule fans out to every user holding target_role (e.g. 6 QA Reviewers), inserting one
Escalation row per recipient -- each is a real, separate email. The constraint was
scoped to (error_id, level, rule_id) only, so the 2nd recipient of any multi-target rule
always collided with the 1st. Reproduced by app/services/escalation_service.py's own
test suite (test_escalation_fires_on_breach) as soon as more than one active user holds
the rule's target_role.

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
"""

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ux_escalation_once", "escalations", type_="unique")
    op.create_unique_constraint(
        "ux_escalation_once", "escalations", ["error_id", "level", "rule_id", "escalated_to"]
    )


def downgrade() -> None:
    op.drop_constraint("ux_escalation_once", "escalations", type_="unique")
    op.create_unique_constraint("ux_escalation_once", "escalations", ["error_id", "level", "rule_id"])
