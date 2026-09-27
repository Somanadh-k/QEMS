"""Quality Signal Engine endpoints (proposal QS-01).

Read-only from the client's perspective. There is deliberately no route by which an AI
output can write to a workflow field — see tests/test_ai_write_isolation.py, which
enumerates every route and asserts exactly that.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role, visible_departments
from app.core.db import get_db
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models import (
    ActorType,
    AIInsight,
    Error,
    InsightStatus,
    ReviewerAction,
    User,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.error_repository import ErrorRepository
from app.schemas.signal import InsightAckRequest, InsightResponse, SignalResponse
from app.services.signal_service import SignalService

router = APIRouter(tags=["signal"])


@router.get("/errors/{error_id}/signal", response_model=SignalResponse)
async def get_signal(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    signal = await SignalService(db).compute(
        error, visible_department_ids=visible_departments(user)
    )
    await db.commit()
    return SignalResponse(**signal)


@router.post("/errors/{error_id}/signal/recompute", response_model=SignalResponse)
async def recompute_signal(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    # Supersede the live insight so compute() produces a fresh one rather than serving
    # the fingerprint cache.
    await db.execute(
        AIInsight.__table__.update()
        .where(AIInsight.error_id == error_id, AIInsight.status == InsightStatus.FRESH)
        .values(status=InsightStatus.SUPERSEDED)
    )
    signal = await SignalService(db).compute(
        error, visible_department_ids=visible_departments(user)
    )
    await db.commit()
    return SignalResponse(**signal)


@router.get("/errors/{error_id}/insights", response_model=list[InsightResponse])
async def list_insights(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Full history including STALE and SUPERSEDED rows.

    What was shown at decision time matters more than what the current model says, so
    superseded insights are listed rather than hidden.
    """
    rows = (
        await db.execute(
            select(AIInsight)
            .where(AIInsight.error_id == error_id)
            .order_by(AIInsight.created_at.desc())
        )
    ).scalars().all()
    return [
        InsightResponse(
            insight_id=r.insight_id, insight_type=r.insight_type, risk_band=r.risk_band,
            risk_score=float(r.risk_score) if r.risk_score is not None else None,
            status=r.status, model_name=r.model_name, created_at=r.created_at,
            reviewer_action=r.reviewer_action, reviewer_notes=r.reviewer_notes,
        )
        for r in rows
    ]


@router.post("/insights/{insight_id}/ack", response_model=InsightResponse)
async def acknowledge_insight(
    insight_id: int,
    payload: InsightAckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Record what the reviewer did with a recommendation.

    Acknowledge, not agree: REJECTED with a reason is a first-class outcome and is the
    most valuable row in the table — it is the only evidence that the human in the loop
    is actually exercising judgement rather than clicking through.
    """
    insight = (
        await db.execute(select(AIInsight).where(AIInsight.insight_id == insight_id))
    ).scalar_one_or_none()
    if insight is None:
        raise NotFoundError(f"Insight {insight_id} not found")

    if payload.action not in set(ReviewerAction):
        raise ValidationError(f"Unknown reviewer action: {payload.action}")
    if payload.action != ReviewerAction.ACCEPTED and not (payload.notes or "").strip():
        raise ValidationError("A note is required when not accepting a recommendation")

    insight.reviewer_action = payload.action
    insight.reviewer_notes = payload.notes
    insight.reviewed_by = user.user_id
    insight.reviewed_at = datetime.now(timezone.utc)

    await AuditLogRepository(db).create(
        action="AI_INSIGHT_ACKNOWLEDGED",
        actor_id=user.user_id,
        actor_type=ActorType.USER,
        error_id=insight.error_id,
        after_value={"action": payload.action},
        reason=payload.notes,
        insight_id=insight.insight_id,
    )
    await db.commit()

    return InsightResponse(
        insight_id=insight.insight_id, insight_type=insight.insight_type,
        risk_band=insight.risk_band,
        risk_score=float(insight.risk_score) if insight.risk_score is not None else None,
        status=insight.status, model_name=insight.model_name,
        created_at=insight.created_at, reviewer_action=insight.reviewer_action,
        reviewer_notes=insight.reviewer_notes,
    )
