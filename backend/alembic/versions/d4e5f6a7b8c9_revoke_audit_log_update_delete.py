"""Actually enforce the append-only audit chain (finding D-02).

audit_log_repository.py has claimed since Phase 0 that the chain is protected by "a
revoked grant... see migration a1b2c3d4e5f6 notes" -- that migration never actually
contained a REVOKE statement, so the application's own DB role has held full UPDATE and
DELETE on audit_logs the entire time. A QA audit of the running system found the chain
already broken (`GET /audit/verify` -> valid:false) and confirmed via
`has_table_privilege` that the grant the code describes does not exist. This migration
is the actual control the comment always claimed to have.

REVOKE on a table's owner still takes effect for ordinary DML (UPDATE/DELETE are
ACL-governed privileges, unlike the DDL rights ownership grants implicitly), so this
does not require a separate, non-owning application role to be effective -- it simply
stops the connected role from ever issuing UPDATE/DELETE against this one table again.
INSERT is untouched: AuditLogRepository.create() only ever inserts.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CURRENT_USER rather than a hard-coded role name: this must bind to whichever role
    # the application actually connects as, in any environment, not just local dev's
    # "qems".
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM CURRENT_USER")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON audit_logs TO CURRENT_USER")
