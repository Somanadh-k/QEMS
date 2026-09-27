"""Background workers (finding F-06: nothing ran on a schedule before this).

APScheduler runs in-process alongside the API. That is the right call at this stage —
one deployable, no broker — and the seam is drawn so that moving to Celery later means
changing how `run_*` is invoked, not rewriting what it does. Each job owns its session,
commits once, and never assumes the previous run succeeded.

Every job is idempotent by construction: SLA state is recomputed from sla_events rather
than incremented, and escalations are protected by a unique constraint. A worker that
was down for six hours must be able to catch up without double-firing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models import ActorType, Error, ErrorStatus, NotificationEvent, Rebuttal, SLAState
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.notification_repository import NotificationRepository
from app.services.escalation_service import EscalationService
from app.services.gmail_inbound_service import process_inbound as process_gmail_inbound
from app.services.notification_service import NotificationService
from app.services.risk_service import compute_risk
from app.services.sla_service import SLAService

logger = logging.getLogger("qems.worker")
settings = get_settings()

TERMINAL_STATUSES = {ErrorStatus.CLOSED}
# Deliberately wider than TERMINAL_STATUSES (which only run_sla_tick uses, unchanged):
# a Resolved/Rejected error is no longer "awaiting" anyone, so it shouldn't generate a
# deadline reminder even though its SLA clock is still technically open until Closed.
DEADLINE_IRRELEVANT_STATUSES = {ErrorStatus.CLOSED, ErrorStatus.RESOLVED, ErrorStatus.REJECTED}
DEADLINE_APPROACHING_WINDOW_HOURS = 24


async def run_sla_tick() -> dict:
    """Recompute SLA state and risk for every open error; fire escalations on breach.

    Returns a summary so the job is observable and testable without reading logs.
    """
    summary = {"examined": 0, "at_risk": 0, "breached": 0, "escalations": 0}
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        sla = SLAService(db)
        escalations = EscalationService(db)
        audit = AuditLogRepository(db)

        errors = (
            await db.execute(
                select(Error).where(Error.status.notin_(list(TERMINAL_STATUSES)))
            )
        ).scalars().all()

        for error in errors:
            summary["examined"] += 1
            previous_state = error.sla_state
            state, ratio = await sla.evaluate(error, now)

            open_rebuttal = (
                await db.execute(
                    select(Rebuttal.rebuttal_id).where(
                        Rebuttal.error_id == error.error_id, Rebuttal.status == "Pending"
                    )
                )
            ).first() is not None

            score, breakdown = compute_risk(
                error,
                sla_ratio=ratio,
                recurrence_band=None,  # populated once the signal engine runs (QS-01)
                has_open_rebuttal=open_rebuttal,
                now=now,
            )
            error.risk_score = score
            error.risk_score_breakdown = breakdown
            error.risk_computed_at = now

            if state != previous_state:
                error.sla_state = state
                await audit.create(
                    action="SLA_STATE_CHANGED",
                    actor_type=ActorType.SYSTEM,
                    error_id=error.error_id,
                    before_value={"sla_state": previous_state},
                    after_value={"sla_state": state, "consumption": round(ratio, 3)},
                )

            if state == SLAState.AT_RISK:
                summary["at_risk"] += 1
                summary["escalations"] += len(await escalations.fire(error, "AT_RISK", now))
            elif state == SLAState.BREACHED:
                summary["breached"] += 1
                summary["escalations"] += len(await escalations.fire(error, "BREACH", now))

        await db.commit()

    logger.info("sla_tick %s", summary)
    return summary


async def run_deadline_notification_tick() -> dict:
    """DEADLINE_APPROACHING / ERROR_OVERDUE (Feature 2). Each fires at most once per
    error -- NotificationRepository.exists_for_event de-duplicates across ticks, since
    this job runs every 5 minutes and an error can sit "due tomorrow" for a full day.
    """
    summary = {"examined": 0, "deadline_approaching": 0, "overdue": 0}
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        notifications = NotificationService(db)
        repo = NotificationRepository(db)

        errors = (
            await db.execute(
                select(Error).where(
                    Error.status.notin_(list(DEADLINE_IRRELEVANT_STATUSES)),
                    Error.due_at.isnot(None),
                )
            )
        ).scalars().all()

        for error in errors:
            summary["examined"] += 1
            recipient_id = error.assigned_to or error.raised_by
            if recipient_id is None:
                continue

            hours_to_due = (error.due_at - now).total_seconds() / 3600
            if 0 <= hours_to_due <= DEADLINE_APPROACHING_WINDOW_HOURS:
                if not await repo.exists_for_event(error.error_id, NotificationEvent.DEADLINE_APPROACHING):
                    await notifications.dispatch_event(
                        NotificationEvent.DEADLINE_APPROACHING,
                        recipient_id=recipient_id,
                        error=error,
                        context={"due_date": error.due_at.strftime("%d %B %Y %H:%M UTC")},
                    )
                    summary["deadline_approaching"] += 1
            elif hours_to_due < 0:
                if not await repo.exists_for_event(error.error_id, NotificationEvent.ERROR_OVERDUE):
                    await notifications.dispatch_event(
                        NotificationEvent.ERROR_OVERDUE,
                        recipient_id=recipient_id,
                        error=error,
                        context={"due_date": error.due_at.strftime("%d %B %Y %H:%M UTC")},
                    )
                    summary["overdue"] += 1

        await db.commit()

    logger.info("deadline_notification_tick %s", summary)
    return summary


async def run_notification_retry_tick() -> dict:
    """Exponential-backoff retry for FAILED notifications (Feature 2's retry requirement).

    Bounded by settings.notification_max_retries -- this is not an uncontrolled loop: a
    notification that still fails after that many attempts stays FAILED for good and is
    only visible via GET /errors/{id}/notifications, not retried further.
    """
    summary = {"attempted": 0, "sent": 0, "still_failed": 0}
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        repo = NotificationRepository(db)
        service = NotificationService(db)

        for notification in await repo.list_retryable(now, settings.notification_max_retries):
            summary["attempted"] += 1
            await service.retry(notification)
            if notification.status == "SENT":
                summary["sent"] += 1
            else:
                summary["still_failed"] += 1

        await db.commit()

    logger.info("notification_retry_tick %s", summary)
    return summary


async def run_gmail_inbound_tick() -> dict:
    """No-op when Gmail OAuth isn't configured -- see GmailProvider.is_configured()."""
    async with AsyncSessionLocal() as db:
        return await process_gmail_inbound(db)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_sla_tick,
        "interval",
        minutes=5,
        id="sla_tick",
        # If the process was asleep, run once on resume rather than once per missed window.
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        run_deadline_notification_tick,
        "interval",
        minutes=5,
        id="deadline_notification_tick",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        run_notification_retry_tick,
        "interval",
        minutes=5,
        id="notification_retry_tick",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        run_gmail_inbound_tick,
        "interval",
        minutes=2,
        id="gmail_inbound_tick",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )
    return scheduler
