"""Phase 0/2: evidence chain of custody (findings F-03, F-04).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("storage_key", sa.String(300)))
    op.add_column("evidence", sa.Column("sha256", sa.String(64)))
    op.add_column("evidence", sa.Column("evidence_class", sa.String(40)))
    op.add_column("evidence", sa.Column("retention_until", sa.DateTime(timezone=True)))

    # Existing rows stored a full public URL in file_url. Recover the object key from it
    # so historical evidence keeps working through the presigned path.
    op.execute(
        "UPDATE evidence SET storage_key = "
        "COALESCE(NULLIF(substring(file_url from 'evidence/.*'), ''), file_url) "
        "WHERE storage_key IS NULL"
    )

    op.create_table(
        "evidence_access_log",
        sa.Column("access_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("evidence_id", sa.Integer(),
                  sa.ForeignKey("evidence.evidence_id", ondelete="CASCADE"), nullable=False),
        sa.Column("accessed_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_evidence_access", "evidence_access_log", ["evidence_id", "accessed_at"])


def downgrade() -> None:
    op.drop_index("idx_evidence_access", table_name="evidence_access_log")
    op.drop_table("evidence_access_log")
    for col in ("retention_until", "evidence_class", "sha256", "storage_key"):
        op.drop_column("evidence", col)
