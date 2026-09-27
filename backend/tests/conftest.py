import getpass
import os
import re

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings

# Finding D-02's fix (migration d4e5f6a7b8c9) revokes UPDATE/DELETE on audit_logs from
# the app's own runtime role, so it can no longer tamper with or bulk-delete its own
# audit trail. Two tests legitimately need to act *outside* that boundary: simulating a
# direct out-of-band edit (test_audit_chain.test_verify_detects_a_tampered_row) and
# cleaning up rows written by independently-committing sessions
# (test_audit_concurrency). Both now do so over this separate, more-privileged
# connection rather than the app's own DSN -- exactly the "distinct, gated credential"
# a real incident-response/admin path would use. Overridable via env for CI; defaults to
# the local OS user, which is the Postgres superuser on a typical local dev install.
def admin_database_url() -> str:
    override = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if override:
        return override
    base = get_settings().database_url
    # Swap only the credentials (user[:pass]@), keep host/port/db from the app's own URL.
    return re.sub(r"://[^@]+@", f"://{getpass.getuser()}@", base)


@pytest_asyncio.fixture
async def db_session():
    """A DB session whose transaction is always rolled back — no test data persists.

    Runs against the real dev Postgres (needed for the pgvector column type), not sqlite.
    Uses its own engine (rather than the app's module-level singleton) and disposes it at
    teardown, since pytest-asyncio gives each test function a fresh event loop and asyncpg
    connections can't be reused across event loops.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
