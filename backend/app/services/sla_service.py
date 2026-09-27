"""SLA clock resolution and evaluation (proposal SLA-02).

Deterministic throughout — no AI anywhere in this module. Deadline arithmetic has a
correct answer that a rule computes exactly and a model computes approximately, and
approximately is the wrong shape of answer for a number a director will quote.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessCalendar,
    CalendarHoliday,
    Error,
    SLAEvent,
    SLAEventType,
    SLAMatrix,
    SLAStage,
    SLAState,
)
from app.services.business_hours import (
    WorkCalendar,
    add_business_hours,
    consumption_ratio,
)

logger = logging.getLogger("qems.sla")

AT_RISK_THRESHOLD = 0.8

# Which role owns the clock during each stage. This is what stops time spent waiting on
# operations being charged to QA — the single thing that makes the breach metric
# survivable in a cross-functional argument.
STAGE_OWNER_ROLE: dict[str, str] = {
    SLAStage.RESPOND: "Department Owner",
    SLAStage.REBUT: "Department Owner",
    SLAStage.DECIDE: "QA Reviewer",
    SLAStage.CLOSE: "QA Reviewer",
}

_DEFAULT_CALENDAR = WorkCalendar()


class SLAService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._calendar_cache: dict[int, WorkCalendar] = {}

    # ------------------------------------------------------------------ policy
    async def resolve_policy(
        self,
        *,
        severity: str,
        stage: str,
        category_id: int | None = None,
        department_id: int | None = None,
        at: datetime | None = None,
    ) -> SLAMatrix | None:
        """Most-specific matching policy wins; NULL in a dimension is a wildcard.

        Ordering by specificity in Python rather than SQL keeps the tie-break rule in one
        readable place — the candidate set is tiny (at most a few rows per severity).
        """
        at = at or datetime.now(timezone.utc)
        rows = (
            await self.db.execute(
                select(SLAMatrix).where(
                    SLAMatrix.stage == stage,
                    SLAMatrix.effective_from <= at,
                    (SLAMatrix.effective_to.is_(None)) | (SLAMatrix.effective_to > at),
                    (SLAMatrix.severity.is_(None)) | (SLAMatrix.severity == severity),
                    (SLAMatrix.category_id.is_(None)) | (SLAMatrix.category_id == category_id),
                    (SLAMatrix.department_id.is_(None))
                    | (SLAMatrix.department_id == department_id),
                )
            )
        ).scalars().all()

        if not rows:
            # Nothing was effective at `at`. This happens for work that predates the
            # policy set — an import, a backfill, or a clock started before a policy was
            # first configured. Falling through to None would make the evaluator report
            # the error as permanently ON_TRACK, which is the most dangerous possible
            # answer, so fall back to the earliest policy that has ever applied.
            fallback = (
                await self.db.execute(
                    select(SLAMatrix)
                    .where(
                        SLAMatrix.stage == stage,
                        (SLAMatrix.severity.is_(None)) | (SLAMatrix.severity == severity),
                    )
                    .order_by(SLAMatrix.effective_from.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if fallback is None:
                # Genuinely unconfigured: a configuration problem, not a silent no-deadline.
                logger.warning(
                    "No SLA policy exists for severity=%s stage=%s category=%s department=%s",
                    severity, stage, category_id, department_id,
                )
                return None

            logger.info(
                "No policy effective at %s for severity=%s stage=%s; using earliest (sla_id=%s)",
                at.isoformat(), severity, stage, fallback.sla_id,
            )
            return fallback

        return max(rows, key=lambda r: (r.specificity, r.effective_from))

    # ---------------------------------------------------------------- calendar
    async def calendar_for(self, calendar_id: int | None) -> WorkCalendar:
        if calendar_id is None:
            return _DEFAULT_CALENDAR
        if calendar_id in self._calendar_cache:
            return self._calendar_cache[calendar_id]

        row = (
            await self.db.execute(
                select(BusinessCalendar).where(BusinessCalendar.calendar_id == calendar_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return _DEFAULT_CALENDAR

        holidays = (
            await self.db.execute(
                select(CalendarHoliday.holiday_date).where(
                    CalendarHoliday.calendar_id == calendar_id
                )
            )
        ).scalars().all()

        calendar = WorkCalendar(
            timezone=row.timezone,
            workday_start=row.workday_start,
            workday_end=row.workday_end,
            workdays=tuple(row.workdays),
            holidays=frozenset(holidays),
        )
        self._calendar_cache[calendar_id] = calendar
        return calendar

    # ------------------------------------------------------------------ clocks
    async def start_stage(
        self,
        error: Error,
        stage: str,
        *,
        actor_id: int | None = None,
        at: datetime | None = None,
    ) -> SLAEvent | None:
        """Begin a stage clock and record who owns it."""
        now = at or datetime.now(timezone.utc)
        policy = await self.resolve_policy(
            severity=error.severity,
            stage=stage,
            category_id=error.category_id,
            department_id=error.department_id,
            at=now,
        )

        due_at = None
        if policy is not None:
            calendar = (
                await self.calendar_for(policy.calendar_id)
                if policy.business_hours_only
                else None
            )
            budget = float(policy.budget_hours)
            due_at = (
                add_business_hours(now, budget, calendar)
                if calendar
                else now + timedelta(hours=budget)
            )

        error.sla_stage = stage
        error.sla_due_at = due_at
        error.sla_state = SLAState.ON_TRACK
        error.sla_clock_owner_role = STAGE_OWNER_ROLE.get(stage)
        error.sla_paused_ms = 0

        event = SLAEvent(
            error_id=error.error_id,
            stage=stage,
            event_type=SLAEventType.START,
            occurred_at=now,
            owner_role=error.sla_clock_owner_role,
            due_at=due_at,
            actor_id=actor_id,
            # Record which policy version governed this stage. Re-baselining a running
            # clock against a later policy edit would rewrite history.
            sla_id=policy.sla_id if policy else None,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def close_stage(
        self, error: Error, *, actor_id: int | None = None, at: datetime | None = None
    ) -> None:
        """Stop the current clock, recording whether it was met or breached."""
        if not error.sla_stage:
            return
        now = at or datetime.now(timezone.utc)
        met = error.sla_due_at is None or now <= error.sla_due_at

        self.db.add(
            SLAEvent(
                error_id=error.error_id,
                stage=error.sla_stage,
                event_type=SLAEventType.MET if met else SLAEventType.BREACH,
                occurred_at=now,
                owner_role=error.sla_clock_owner_role,
                due_at=error.sla_due_at,
                actor_id=actor_id,
            )
        )
        if met:
            error.sla_state = SLAState.MET
        await self.db.flush()

    async def evaluate(self, error: Error, now: datetime | None = None) -> tuple[str, float]:
        """Current state and consumption ratio for a running clock.

        Returns the state unchanged for paused or already-finished clocks so the worker
        never re-fires on them.
        """
        now = now or datetime.now(timezone.utc)
        if error.sla_state in (SLAState.PAUSED, SLAState.MET) or not error.sla_stage:
            return error.sla_state, 0.0

        start_event = (
            await self.db.execute(
                select(SLAEvent)
                .where(
                    SLAEvent.error_id == error.error_id,
                    SLAEvent.stage == error.sla_stage,
                    SLAEvent.event_type == SLAEventType.START,
                )
                .order_by(SLAEvent.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if start_event is None:
            return error.sla_state, 0.0

        policy = await self.resolve_policy(
            severity=error.severity,
            stage=error.sla_stage,
            category_id=error.category_id,
            department_id=error.department_id,
            at=start_event.occurred_at,
        )
        if policy is None:
            return error.sla_state, 0.0

        calendar = await self.calendar_for(policy.calendar_id)
        ratio = consumption_ratio(
            start_event.occurred_at,
            now,
            float(policy.budget_hours),
            calendar,
            paused_seconds=(error.sla_paused_ms or 0) / 1000.0,
        )

        if ratio >= 1.0:
            return SLAState.BREACHED, ratio
        if ratio >= AT_RISK_THRESHOLD:
            return SLAState.AT_RISK, ratio
        return SLAState.ON_TRACK, ratio
