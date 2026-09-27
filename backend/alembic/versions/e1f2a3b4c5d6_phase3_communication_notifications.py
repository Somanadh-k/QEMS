"""Phase 3: two-way communication threads + event-driven notification system.

Adds `messages` / `message_attachments` (Feature 1 -- a permanent conversation thread
per QA Error, never freestanding), and `notification_templates` / `notification_logs`
plus new columns on the existing `notifications` table (Feature 2 -- centralised,
event-driven notification dispatch; see app/services/notification_service.py). No
existing table is dropped or renamed and no existing row is touched beyond the
`created_at` backfill below, so this is safe to run against a populated database.

Revision ID: e1f2a3b4c5d6
Revises: a7b8c9d0e1f2
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

# Keep in sync with app.models.notification.NotificationEvent. Seeded once so the
# system has usable copy from the first request; editable afterwards via
# GET/PATCH /notification-templates without another migration.
DEFAULT_TEMPLATES = [
    (
        "ERROR_CREATED",
        "New QA Error Logged: {{error_id}}",
        "A new QA error has been logged.\n\n"
        "Error ID: {{error_id}}\nSeverity: {{severity}}\nCategory: {{category}}\n\n"
        "View it here: {{qems_url}}",
    ),
    (
        "ERROR_ASSIGNED",
        "Action Required: {{error_id}}",
        "A new QA error has been assigned to you.\n\n"
        "Error ID: {{error_id}}\nSeverity: {{severity}}\nCategory: {{category}}\n"
        "Assigned By: {{sender}}\nDue Date: {{due_date}}\n\n"
        "Please review the error and submit your response.\n{{qems_url}}",
    ),
    (
        "MESSAGE_RECEIVED",
        "New message on {{error_id}}",
        "{{sender}} sent a new message on {{error_id}}:\n\n\"{{message}}\"\n\n"
        "Reply here: {{qems_url}}",
    ),
    (
        "REBUTTAL_SUBMITTED",
        "Response Received: Rebuttal on {{error_id}}",
        "A stakeholder has submitted a rebuttal for {{error_id}}. Please review the "
        "response and supporting evidence.\n\n{{message}}\n\n{{qems_url}}",
    ),
    (
        "EVIDENCE_REQUESTED",
        "Evidence Required: {{error_id}}",
        "Additional evidence has been requested for {{error_id}}.\n\n"
        "Request: {{message}}\n\nPlease upload supporting evidence: {{qems_url}}",
    ),
    (
        "DECISION_UPDATED",
        "QA decision recorded: {{error_id}}",
        "A QA decision has been recorded on {{error_id}}.\n\n"
        "Decision: {{decision}}\nNotes: {{message}}\n\n{{qems_url}}",
    ),
    (
        "DEADLINE_APPROACHING",
        "Reminder: {{error_id}} is due soon",
        "{{error_id}} is due {{due_date}} and is still awaiting a response. "
        "Please act before the deadline.\n\n{{qems_url}}",
    ),
    (
        "ERROR_OVERDUE",
        "Overdue: {{error_id}}",
        "{{error_id}} has exceeded its response deadline ({{due_date}}). "
        "Immediate attention is required.\n\n{{qems_url}}",
    ),
    (
        "ERROR_RESOLVED",
        "Resolved: {{error_id}}",
        "{{error_id}} ({{category}}) has been marked Resolved.\n\n"
        "Decision: {{decision}}\n\n{{qems_url}}",
    ),
]


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("message_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("error_id", sa.Integer(), sa.ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column(
            "parent_message_id",
            sa.Integer(),
            sa.ForeignKey("messages.message_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False, server_default="TEXT"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "message_type IN ('TEXT','EVIDENCE_REQUEST','EVIDENCE_UPLOAD','STATUS_NOTE')",
            name="ck_messages_type",
        ),
    )
    op.create_index("idx_messages_error", "messages", ["error_id", "created_at"])
    op.create_index("idx_messages_parent", "messages", ["parent_message_id"])

    op.create_table(
        "message_attachments",
        sa.Column("attachment_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "message_id", sa.Integer(), sa.ForeignKey("messages.message_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size_kb", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_message_attachments_message", "message_attachments", ["message_id"])

    # --- notifications: extend in place, no data loss ---
    op.add_column("notifications", sa.Column("event_type", sa.String(40)))
    op.add_column("notifications", sa.Column("content", sa.Text()))
    op.add_column("notifications", sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("notifications", sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("created_at", sa.DateTime(timezone=True)))
    # Existing rows have no created_at; best available approximation is sent_at, else now().
    op.execute("UPDATE notifications SET created_at = COALESCE(sent_at, now()) WHERE created_at IS NULL")
    op.alter_column("notifications", "created_at", nullable=False, server_default=sa.func.now())

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(40), nullable=False, unique=True),
        sa.Column("subject_template", sa.String(300), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )

    templates_table = sa.table(
        "notification_templates",
        sa.column("event_type", sa.String),
        sa.column("subject_template", sa.String),
        sa.column("body_template", sa.Text),
    )
    op.bulk_insert(
        templates_table,
        [
            {"event_type": event, "subject_template": subject, "body_template": body}
            for event, subject, body in DEFAULT_TEMPLATES
        ],
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notification_id", sa.Integer(),
            sa.ForeignKey("notifications.notification_id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_notification_logs_notification", "notification_logs", ["notification_id"])


def downgrade() -> None:
    op.drop_index("idx_notification_logs_notification", table_name="notification_logs")
    op.drop_table("notification_logs")
    op.drop_table("notification_templates")

    for col in ("created_at", "read_at", "next_retry_at", "retry_count", "content", "event_type"):
        op.drop_column("notifications", col)

    op.drop_index("idx_message_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")

    op.drop_index("idx_messages_parent", table_name="messages")
    op.drop_index("idx_messages_error", table_name="messages")
    op.drop_table("messages")
