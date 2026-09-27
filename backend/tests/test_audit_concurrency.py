"""Audit hash chain under concurrent writers.

The chain is only meaningful if writers agree on their predecessor. Two transactions
reading the same tip would fork it, and verification would report a break. The advisory
lock in AuditLogRepository.create is what prevents that — this test exercises it with
genuinely parallel sessions rather than trusting the lock by inspection.

The report flagged this as untested before running more than one API worker.
"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import ActorType, AuditLog
from app.repositories.audit_log_repository import AuditLogRepository
from tests.conftest import admin_database_url

CONCURRENT_WRITERS = 12


@pytest.mark.asyncio
async def test_chain_stays_linear_under_concurrent_writers():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    marker = "CONCURRENCY_PROBE"

    async def writer(n: int) -> int:
        # Each writer gets its own session and commits independently, which is what a
        # second uvicorn worker would do.
        async with factory() as session:
            entry = await AuditLogRepository(session).create(
                action=marker, actor_type=ActorType.SYSTEM, after_value={"writer": n}
            )
            await session.commit()
            return entry.audit_id

    ids: list[int] = []
    try:
        ids = await asyncio.gather(*(writer(i) for i in range(CONCURRENT_WRITERS)))
        assert len(set(ids)) == CONCURRENT_WRITERS, "writers collided on a primary key"

        async with factory() as session:
            rows = (
                await session.execute(
                    select(AuditLog).where(AuditLog.audit_id.in_(ids)).order_by(AuditLog.audit_id)
                )
            ).scalars().all()

            # No two rows may claim the same predecessor — that is what a forked chain
            # looks like, and it is the specific failure the advisory lock prevents.
            prevs = [r.prev_hash for r in rows]
            assert len(prevs) == len(set(prevs)), "two concurrent rows share a prev_hash (forked chain)"

            # Every row's stored hash must still match its own content.
            for r in rows:
                assert r.row_hash == r.compute_hash(r.prev_hash, r.created_at)

            # Scope: this test asks whether concurrent writers fork the chain, not
            # whether the entire historical chain is intact — that is AUD-01's job. A
            # pre-existing break earlier in the table (from an authorised bulk change,
            # say) must not fail a concurrency test, or the two failures become
            # indistinguishable.
            for earlier, later in zip(rows, rows[1:]):
                assert later.prev_hash == earlier.row_hash, (
                    f"chain forked between {earlier.audit_id} and {later.audit_id}"
                )
    finally:
        # Unconditional: a failing run must not leave forked rows behind, or it breaks
        # verify_chain for every later run. Raw SQL because the repository deliberately
        # exposes no delete. Runs over the admin connection (not `factory`, i.e. not the
        # app's own DSN): migration d4e5f6a7b8c9 revoked DELETE on audit_logs from the
        # app's runtime role, so cleanup needs the same elevated path
        # test_audit_chain's tampering test uses.
        if ids:
            from sqlalchemy import delete
            admin_engine = create_async_engine(admin_database_url(), pool_pre_ping=True)
            try:
                admin_factory = async_sessionmaker(admin_engine, expire_on_commit=False)
                async with admin_factory() as cleanup:
                    await cleanup.execute(delete(AuditLog).where(AuditLog.audit_id.in_(ids)))
                    await cleanup.commit()
            finally:
                await admin_engine.dispose()
        await engine.dispose()
