"""Audit hash chain (proposal section 13).

The chain's job is not to prevent tampering — it is to make tampering detectable.
These tests assert exactly that property, including the negative case.
"""

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ActorType, AuditLog
from app.repositories.audit_log_repository import AuditLogRepository
from tests.conftest import admin_database_url


async def test_chain_links_each_row_to_its_predecessor(db_session):
    repo = AuditLogRepository(db_session)

    first = await repo.create(action="TEST_ONE", actor_type=ActorType.SYSTEM)
    second = await repo.create(action="TEST_TWO", actor_type=ActorType.SYSTEM)
    third = await repo.create(action="TEST_THREE", actor_type=ActorType.SYSTEM)

    assert second.prev_hash == first.row_hash
    assert third.prev_hash == second.row_hash
    assert len({first.row_hash, second.row_hash, third.row_hash}) == 3


async def test_verify_detects_a_tampered_row():
    """Simulates a direct, out-of-band DB edit -- not a write through the app.

    Since migration d4e5f6a7b8c9, the app's own runtime role has no UPDATE/DELETE grant
    on audit_logs, so this can no longer be exercised through `db_session` (which
    connects as that same role, and which never commits anyway -- an out-of-band editor
    is a different connection entirely, and needs to see a row that's actually
    committed). This runs entirely over the admin connection instead, mirroring
    test_audit_concurrency's pattern of independently-committing sessions, and cleans up
    the rows it commits since the rollback-based `db_session` isolation doesn't apply.
    """
    engine = create_async_engine(admin_database_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids: list[int] = []
    try:
        async with factory() as session:
            repo = AuditLogRepository(session)
            before = await repo.create(action="BEFORE_TAMPER", actor_type=ActorType.SYSTEM)
            victim = await repo.create(
                action="ORIGINAL_ACTION", actor_type=ActorType.SYSTEM, after_value={"status": "Open"}
            )
            after = await repo.create(action="AFTER_TAMPER", actor_type=ActorType.SYSTEM)
            await session.commit()
            ids = [before.audit_id, victim.audit_id, after.audit_id]

            # Simulate someone editing history directly in the database, leaving the
            # hash behind -- exactly what the app itself can no longer do.
            await session.execute(
                text("UPDATE audit_logs SET after_value = :v WHERE audit_id = :i"),
                {"v": '{"status": "Closed"}', "i": victim.audit_id},
            )
            await session.commit()
            session.expire_all()

            # Assert the detection primitive directly rather than asking verify_chain
            # which row it reports first. verify_chain walks from the beginning and
            # stops at the earliest break, so if the table already contains an earlier
            # one — after an authorised bulk change, say — it would report that
            # instead, and this test would fail for a reason that has nothing to do
            # with tamper detection.
            await session.refresh(victim)
            recomputed = victim.compute_hash(victim.prev_hash, victim.created_at)
            assert recomputed != victim.row_hash, "edited content must not still match its stored hash"

            # And the chain as a whole must report itself broken.
            result = await repo.verify_chain()
            assert result["valid"] is False
    finally:
        if ids:
            async with factory() as cleanup:
                await cleanup.execute(delete(AuditLog).where(AuditLog.audit_id.in_(ids)))
                await cleanup.commit()
        await engine.dispose()


async def test_system_actor_may_have_no_user(db_session):
    """A scheduled worker must be able to log without impersonating a person."""
    repo = AuditLogRepository(db_session)
    entry = await repo.create(action="SLA_BREACH", actor_type=ActorType.SYSTEM, actor_id=None)
    assert entry.actor_id is None
    assert entry.actor_type == ActorType.SYSTEM


async def test_user_actor_without_id_is_rejected_by_the_database(db_session):
    """The USER/actor_id invariant is a database constraint, not a code convention."""
    from sqlalchemy.exc import IntegrityError

    repo = AuditLogRepository(db_session)
    with pytest.raises(IntegrityError):
        await repo.create(action="BAD", actor_type=ActorType.USER, actor_id=None)
