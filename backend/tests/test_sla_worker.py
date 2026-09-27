"""SLA worker behaviour: breach detection, escalation, and idempotency.

The idempotency test is the important one. A worker that was down for six hours must be
able to catch up without re-firing every escalation it already sent — otherwise recovery
means four hundred emails at 09:00 and a feature everyone turns off.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.api.v1.routers.governance import AckRequest, acknowledge_escalation
from app.core.exceptions import PermissionDeniedError
from app.models import (
    Error,
    ErrorStatus,
    Escalation,
    SLAEvent,
    SLAEventType,
    SLAStage,
    SLAState,
    User,
)
from app.services.escalation_service import EscalationService
from app.services.sla_service import SLAService
from tests.test_error_lifecycle import _make_user


async def _breached_error(db):
    """An error whose RESPOND clock started long enough ago to be well past budget.

    Unique qa_error_code per call (not a hardcoded literal): acknowledge_escalation is a
    router function that commits internally, and calling it directly with db_session (as
    the ack-authorization tests below do) persists its transaction for real instead of
    rolling back at teardown -- the same reason test_error_lifecycle.py and
    test_error_authorization.py generate unique identifiers instead of hardcoding them.
    """
    qa = (await db.execute(select(User).limit(1))).scalar_one()
    error = Error(
        qa_error_code=f"TEST-BREACH-{uuid.uuid4().hex[:8]}", title="Identity check skipped",
        description="Test fixture", category_id=1, severity="Critical",
        status=ErrorStatus.OPEN, department_id=1, raised_by=qa.user_id,
        date_discovered=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc) - timedelta(days=20),
    )
    db.add(error)
    await db.flush()

    sla = SLAService(db)
    await sla.start_stage(error, SLAStage.RESPOND)
    # Backdate the START event so the clock has genuinely run out.
    await db.execute(
        SLAEvent.__table__.update()
        .where(SLAEvent.error_id == error.error_id)
        .values(occurred_at=datetime.now(timezone.utc) - timedelta(days=20))
    )
    return error


async def test_a_stale_clock_is_reported_as_breached(db_session):
    error = await _breached_error(db_session)
    state, ratio = await SLAService(db_session).evaluate(error)
    assert state == SLAState.BREACHED
    assert ratio >= 1.0


async def test_escalation_fires_on_breach(db_session):
    error = await _breached_error(db_session)
    created = await EscalationService(db_session).fire(error, "BREACH")
    assert created, "a breach with an active BREACH rule must produce an escalation"
    assert error.escalation_level >= 1


async def test_escalation_is_idempotent_across_repeated_runs(db_session):
    """Replaying the same window must not produce a second escalation."""
    error = await _breached_error(db_session)
    service = EscalationService(db_session)

    first = await service.fire(error, "BREACH")
    second = await service.fire(error, "BREACH")
    third = await service.fire(error, "BREACH")

    assert len(first) >= 1
    assert second == [] and third == []

    total = (
        await db_session.execute(
            select(func.count()).select_from(Escalation).where(Escalation.error_id == error.error_id)
        )
    ).scalar_one()
    assert total == len(first), "repeated ticks must not accumulate escalation rows"


async def test_acknowledging_requires_and_records_a_commitment(db_session):
    error = await _breached_error(db_session)
    service = EscalationService(db_session)
    escalation = (await service.fire(error, "BREACH"))[0]
    user = (await db_session.execute(select(User).limit(1))).scalar_one()

    await service.acknowledge(escalation, user, "Reassigning to the process owner today", None)
    assert escalation.acknowledged_at is not None
    assert escalation.acknowledged_by == user.user_id
    assert escalation.next_action


async def test_ack_endpoint_rejects_a_user_the_escalation_was_not_routed_to(db_session):
    """list_escalations already scopes reads to "escalated to you, or Admin sees all" --
    the POST .../ack endpoint had no equivalent check, so any authenticated user could
    acknowledge (and thereby silence) an alert routed to someone else. Found live while
    testing the Escalation Inbox: a Department Owner successfully acknowledged an
    escalation that was routed to a QA Reviewer."""
    error = await _breached_error(db_session)
    escalation = (await EscalationService(db_session).fire(error, "BREACH"))[0]
    tag = uuid.uuid4().hex[:8]
    bystander = await _make_user(db_session, "Department Owner", 1, f"bystander_ack_{tag}@qemscorp.dev")

    assert escalation.escalated_to != bystander.user_id
    with pytest.raises(PermissionDeniedError):
        await acknowledge_escalation(
            escalation.escalation_id,
            AckRequest(next_action="should be rejected"),
            db=db_session,
            user=bystander,
        )


async def test_ack_endpoint_allows_the_actual_target(db_session):
    error = await _breached_error(db_session)
    escalation = (await EscalationService(db_session).fire(error, "BREACH"))[0]
    target = await db_session.get(User, escalation.escalated_to)

    result = await acknowledge_escalation(
        escalation.escalation_id,
        AckRequest(next_action="Reassigning to the process owner today"),
        db=db_session,
        user=target,
    )
    assert result.acknowledged_at is not None


async def test_ack_endpoint_allows_admin_override(db_session):
    error = await _breached_error(db_session)
    escalation = (await EscalationService(db_session).fire(error, "BREACH"))[0]
    tag = uuid.uuid4().hex[:8]
    admin = await _make_user(db_session, "Admin", 1, f"admin_ack_{tag}@qemscorp.dev")

    assert escalation.escalated_to != admin.user_id
    result = await acknowledge_escalation(
        escalation.escalation_id,
        AckRequest(next_action="Admin override test"),
        db=db_session,
        user=admin,
    )
    assert result.acknowledged_at is not None


async def test_a_met_clock_does_not_escalate(db_session):
    """A fresh clock must be ON_TRACK — the worker must not fire on healthy work."""
    qa = (await db_session.execute(select(User).limit(1))).scalar_one()
    error = Error(
        qa_error_code="TEST-FRESH", title="Fresh finding", description="Test fixture",
        category_id=1, severity="Low", status=ErrorStatus.OPEN, department_id=1,
        raised_by=qa.user_id, date_discovered=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(error)
    await db_session.flush()
    await SLAService(db_session).start_stage(error, SLAStage.RESPOND)

    state, ratio = await SLAService(db_session).evaluate(error)
    assert state == SLAState.ON_TRACK
    assert ratio < 0.8
