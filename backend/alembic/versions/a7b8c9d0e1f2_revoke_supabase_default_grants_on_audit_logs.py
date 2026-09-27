"""Close a Supabase-specific hole in the append-only audit chain (finding D-02, part 2).

d4e5f6a7b8c9 revoked UPDATE/DELETE on audit_logs from CURRENT_USER (the app's own
connecting role), on the reasoning that a direct REVOKE is enough regardless of
environment. That held for local Postgres, but not for Supabase: Supabase grants
INSERT/SELECT/UPDATE/DELETE/... on every public table to `anon`, `authenticated`, and
`service_role` by default (so a fresh table works out of the box through its
PostgREST/client-library API), and the project's own connecting role (`postgres`) is a
transitive member of `authenticated`. A role inherits privileges from every role it's a
member of, so revoking the *direct* grant on `postgres` left the *inherited* grant via
`authenticated` completely intact -- confirmed live: `has_table_privilege('postgres',
'audit_logs', 'UPDATE')` still returned true, and an UPDATE from the app's own
connection still succeeded, after d4e5f6a7b8c9 had already run.

This app never uses Supabase's PostgREST/client-library path (it connects directly via
DATABASE_URL and enforces its own RBAC at the application layer -- see backend/README.md
"Database & Storage (Supabase)"), so `anon`/`authenticated`/`service_role` having any
access to audit_logs serves no purpose here except this exact hole. Revoked from all
three, plus PUBLIC as a defensive no-op. Guarded by role existence so this is a no-op on
local Postgres, which has none of these roles.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
"""

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

SUPABASE_DEFAULT_ROLES = ["anon", "authenticated", "service_role"]


def upgrade() -> None:
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")
    for role in SUPABASE_DEFAULT_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'REVOKE UPDATE, DELETE ON audit_logs FROM {role}';
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON audit_logs TO PUBLIC")
    for role in SUPABASE_DEFAULT_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'GRANT UPDATE, DELETE ON audit_logs TO {role}';
                END IF;
            END $$;
            """
        )
