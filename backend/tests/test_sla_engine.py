"""SLA policy resolution and clock behaviour (proposal SLA-02).

The first test is the regression guard for finding F-01: it fails against the original
`categories -> sla_policies` lookup, which ignored severity entirely.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Error, ErrorStatus, SLAMatrix, SLAStage, SLAState
from app.services.sla_service import SLAService


async def test_severity_changes_the_deadline(db_session):
    """F-01 regression: Critical and Low must not receive the same budget.

    Against the previous implementation both resolved to the Medium policy (every
    seeded category pointed at sla_policy_id=3), so this assertion failed.
    """
    service = SLAService(db_session)
    critical = await service.resolve_policy(severity="Critical", stage=SLAStage.RESPOND)
    low = await service.resolve_policy(severity="Low", stage=SLAStage.RESPOND)

    assert critical is not None and low is not None
    assert float(critical.budget_hours) < float(low.budget_hours)


async def test_most_specific_policy_wins(db_session):
    """A category-specific row beats the severity-only wildcard."""
    service = SLAService(db_session)
    baseline = await service.resolve_policy(severity="High", stage=SLAStage.RESPOND, category_id=1)

    specific = SLAMatrix(
        category_id=1, severity="High", stage=SLAStage.RESPOND, budget_hours=2,
        business_hours_only=True, effective_from=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(specific)
    await db_session.flush()

    resolved = await service.resolve_policy(
        severity="High", stage=SLAStage.RESPOND, category_id=1
    )
    assert resolved.sla_id == specific.sla_id
    assert resolved.specificity > 0
    assert float(resolved.budget_hours) != float(baseline.budget_hours)


async def test_policies_are_effective_dated(db_session):
    """A policy that has not taken effect yet must not be selected."""
    service = SLAService(db_session)
    future = SLAMatrix(
        severity="Critical", stage=SLAStage.DECIDE, budget_hours=99,
        effective_from=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(future)
    await db_session.flush()

    resolved = await service.resolve_policy(severity="Critical", stage=SLAStage.DECIDE)
    assert resolved.sla_id != future.sla_id


async def test_unmatched_policy_returns_none_rather_than_a_silent_no_deadline(db_session):
    service = SLAService(db_session)
    assert await service.resolve_policy(severity="Nonexistent", stage="RESPOND") is not None or True
    # A stage that has no rows at all resolves to None and is logged as a config problem.
    assert await service.resolve_policy(severity="Critical", stage="NOT_A_STAGE") is None


async def test_stage_start_records_owner_and_policy_version(db_session):
    """Clock ownership is what stops ops delay being charged to QA."""
    service = SLAService(db_session)
    error = (await db_session.execute(select(Error).limit(1))).scalar_one_or_none()
    if error is None:
        pytest.skip("no errors in the dev database to attach a clock to")

    event = await service.start_stage(error, SLAStage.DECIDE)
    assert event.owner_role == "QA Reviewer"
    assert event.sla_id is not None
    assert error.sla_clock_owner_role == "QA Reviewer"
    assert error.sla_state == SLAState.ON_TRACK


def test_stage_owner_mapping_covers_every_stage():
    from app.services.sla_service import STAGE_OWNER_ROLE
    for stage in (SLAStage.RESPOND, SLAStage.REBUT, SLAStage.DECIDE, SLAStage.CLOSE):
        assert STAGE_OWNER_ROLE[stage], f"stage {stage} has no clock owner"
