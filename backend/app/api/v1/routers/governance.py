"""SLA, escalation and audit endpoints (proposal SLA-02, RS-08, section 13)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models import (
    ActorType,
    Error,
    Escalation,
    SLAEvent,
    SLAEventType,
    SLAMatrix,
    SLAState,
    User,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.error_repository import ErrorRepository
from app.services.escalation_service import EscalationService
from app.services.sla_service import SLAService

router = APIRouter(tags=["governance"])


class SLAStageView(BaseModel):
    stage: str
    event_type: str
    owner_role: str | None
    occurred_at: datetime
    due_at: datetime | None


class SLAView(BaseModel):
    sla_state: str
    sla_stage: str | None
    sla_due_at: datetime | None
    clock_owner_role: str | None
    consumption_ratio: float
    escalation_level: int
    timeline: list[SLAStageView]


class PauseRequest(BaseModel):
    reason: str


class AckRequest(BaseModel):
    next_action: str
    eta: datetime | None = None


class EscalationView(BaseModel):
    escalation_id: int
    error_id: int
    qa_error_code: str | None = None
    level: int
    trigger: str
    triggered_at: datetime
    acknowledged_at: datetime | None
    next_action: str | None


@router.get("/errors/{error_id}/sla", response_model=SLAView)
async def get_sla(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    state, ratio = await SLAService(db).evaluate(error)
    events = (
        await db.execute(
            select(SLAEvent).where(SLAEvent.error_id == error_id).order_by(SLAEvent.occurred_at)
        )
    ).scalars().all()

    return SLAView(
        sla_state=state,
        sla_stage=error.sla_stage,
        sla_due_at=error.sla_due_at,
        clock_owner_role=error.sla_clock_owner_role,
        consumption_ratio=round(ratio, 4),
        escalation_level=error.escalation_level or 0,
        timeline=[
            SLAStageView(
                stage=e.stage, event_type=e.event_type, owner_role=e.owner_role,
                occurred_at=e.occurred_at, due_at=e.due_at,
            )
            for e in events
        ],
    )


@router.post("/errors/{error_id}/sla/pause", response_model=SLAView)
async def pause_sla(
    error_id: int,
    payload: PauseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("Admin")),
):
    """Admin only, reason required, always audited.

    Pausing a clock is the obvious way to game a breach metric. It is not forbidden —
    legitimate pauses exist — but it is made expensive and visible rather than quiet.
    """
    if not payload.reason.strip():
        raise ValidationError("A reason is required to pause an SLA clock")

    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    error.sla_state = SLAState.PAUSED
    db.add(
        SLAEvent(
            error_id=error_id, stage=error.sla_stage or "RESPOND",
            event_type=SLAEventType.PAUSE, owner_role=error.sla_clock_owner_role,
            reason=payload.reason, actor_id=user.user_id,
        )
    )
    await AuditLogRepository(db).create(
        action="SLA_PAUSED", actor_id=user.user_id, actor_type=ActorType.USER,
        error_id=error_id, after_value={"sla_state": SLAState.PAUSED}, reason=payload.reason,
    )
    await db.commit()
    return await get_sla(error_id, db, user)


@router.get("/escalations", response_model=list[EscalationView])
async def list_escalations(
    acknowledged: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(Escalation, Error.qa_error_code)
        .join(Error, Error.error_id == Escalation.error_id)
        .order_by(Escalation.triggered_at.desc())
    )
    query = query.where(
        Escalation.acknowledged_at.isnot(None) if acknowledged else Escalation.acknowledged_at.is_(None)
    )
    # Non-admins see only what was escalated to them.
    if "Admin" not in user.role_names:
        query = query.where(Escalation.escalated_to == user.user_id)

    rows = (await db.execute(query)).all()
    return [
        EscalationView(
            escalation_id=e.escalation_id, error_id=e.error_id, qa_error_code=code,
            level=e.level, trigger=e.trigger, triggered_at=e.triggered_at,
            acknowledged_at=e.acknowledged_at, next_action=e.next_action,
        )
        for e, code in rows
    ]


@router.post("/escalations/{escalation_id}/ack", response_model=EscalationView)
async def acknowledge_escalation(
    escalation_id: int,
    payload: AckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Acknowledging requires a commitment — a bare 'seen' is not an outcome."""
    escalation = (
        await db.execute(select(Escalation).where(Escalation.escalation_id == escalation_id))
    ).scalar_one_or_none()
    if escalation is None:
        raise NotFoundError(f"Escalation {escalation_id} not found")
    # list_escalations already scopes reads to "escalated to you, or Admin sees all" --
    # this write path had no equivalent check, so anyone authenticated could acknowledge
    # an escalation routed to someone else, silencing an alert the actual owner never saw.
    if escalation.escalated_to != user.user_id and "Admin" not in user.role_names:
        raise PermissionDeniedError(f"Escalation {escalation_id} is not routed to you")
    if not payload.next_action.strip():
        raise ValidationError("A next action is required when acknowledging an escalation")

    await EscalationService(db).acknowledge(escalation, user, payload.next_action, payload.eta)
    await db.commit()

    code = (
        await db.execute(select(Error.qa_error_code).where(Error.error_id == escalation.error_id))
    ).scalar_one_or_none()
    return EscalationView(
        escalation_id=escalation.escalation_id, error_id=escalation.error_id,
        qa_error_code=code, level=escalation.level, trigger=escalation.trigger,
        triggered_at=escalation.triggered_at, acknowledged_at=escalation.acknowledged_at,
        next_action=escalation.next_action,
    )


@router.get("/sla/policies")
async def list_sla_policies(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("Admin", "QA Reviewer")),
):
    rows = (
        await db.execute(select(SLAMatrix).order_by(SLAMatrix.severity, SLAMatrix.stage))
    ).scalars().all()
    return [
        {
            "sla_id": r.sla_id, "severity": r.severity, "stage": r.stage,
            "budget_hours": float(r.budget_hours), "category_id": r.category_id,
            "department_id": r.department_id, "business_hours_only": r.business_hours_only,
            "effective_from": r.effective_from, "effective_to": r.effective_to,
            "specificity": r.specificity,
        }
        for r in rows
    ]


@router.get("/audit/verify")
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("Admin")),
):
    """Walk the hash chain and report the first break, if any."""
    return await AuditLogRepository(db).verify_chain()


@router.get("/errors/{error_id}/audit")
async def error_audit_trail(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("Admin", "QA Reviewer")),
):
    from app.models import AuditLog

    rows = (
        await db.execute(
            select(AuditLog).where(AuditLog.error_id == error_id).order_by(AuditLog.created_at)
        )
    ).scalars().all()
    return [
        {
            "audit_id": r.audit_id, "action": r.action, "actor_type": r.actor_type,
            "actor_id": r.actor_id, "reason": r.reason, "insight_id": r.insight_id,
            "before_value": r.before_value, "after_value": r.after_value,
            "created_at": r.created_at, "row_hash": r.row_hash,
        }
        for r in rows
    ]
