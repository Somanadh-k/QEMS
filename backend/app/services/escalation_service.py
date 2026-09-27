"""Escalation firing (proposal SLA-02).

Two properties matter more than the routing logic itself:

* **Idempotency.** The unique constraint on (error_id, level, rule_id) means a worker
  replaying a missed window after downtime cannot re-fire an escalation it already sent.
  Without it, six hours of worker downtime ends with four hundred emails at 09:00 and a
  feature everyone disables.
* **Role resolution.** Targets resolve through roles, not hard-coded user ids, so a
  leaver cannot silently black-hole every level-2 escalation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActorType,
    Error,
    Escalation,
    EscalationRule,
    Role,
    SLAEvent,
    SLAEventType,
    User,
    UserRole,
)
from app.repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger("qems.escalation")

SEVERITY_RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


class EscalationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditLogRepository(db)

    async def _resolve_targets(self, rule: EscalationRule, error: Error) -> list[int]:
        if rule.target_user_id:
            return [rule.target_user_id]
        if not rule.target_role:
            # Never escalate to nobody: fall back to whoever raised the finding.
            return [error.raised_by]

        rows = (
            await self.db.execute(
                select(User.user_id)
                .join(UserRole, UserRole.user_id == User.user_id)
                .join(Role, Role.role_id == UserRole.role_id)
                .where(Role.role_name == rule.target_role, User.is_active.is_(True))
            )
        ).scalars().all()
        return list(rows) or [error.raised_by]

    async def _recently_fired(self, error_id: int, rule: EscalationRule, now: datetime) -> bool:
        cutoff = now - timedelta(minutes=rule.cooldown_minutes)
        existing = (
            await self.db.execute(
                select(Escalation.escalation_id).where(
                    Escalation.error_id == error_id,
                    Escalation.rule_id == rule.rule_id,
                    Escalation.triggered_at >= cutoff,
                )
            )
        ).first()
        return existing is not None

    async def fire(
        self, error: Error, trigger: str, now: datetime | None = None
    ) -> list[Escalation]:
        """Create escalations for every active rule matching this trigger and severity."""
        now = now or datetime.now(timezone.utc)
        rules = (
            await self.db.execute(
                select(EscalationRule).where(
                    EscalationRule.active.is_(True), EscalationRule.trigger == trigger
                )
            )
        ).scalars().all()

        created: list[Escalation] = []
        for rule in rules:
            if rule.severity_min and SEVERITY_RANK.get(error.severity, 0) < SEVERITY_RANK.get(
                rule.severity_min, 0
            ):
                continue
            if await self._recently_fired(error.error_id, rule, now):
                continue

            for target in await self._resolve_targets(rule, error):
                escalation = Escalation(
                    error_id=error.error_id,
                    level=rule.level,
                    rule_id=rule.rule_id,
                    escalated_to=target,
                    trigger=trigger,
                    triggered_at=now,
                )
                self.db.add(escalation)
                try:
                    # Savepoint so a duplicate does not poison the surrounding transaction.
                    async with self.db.begin_nested():
                        await self.db.flush()
                except IntegrityError:
                    # ux_escalation_once: already sent for this (error, level, rule).
                    logger.debug(
                        "Escalation already exists for error=%s level=%s rule=%s",
                        error.error_id, rule.level, rule.rule_id,
                    )
                    continue

                created.append(escalation)
                error.escalation_level = max(error.escalation_level or 0, rule.level)
                await self.audit.create(
                    action="SLA_ESCALATED",
                    actor_type=ActorType.SYSTEM,
                    error_id=error.error_id,
                    after_value={
                        "level": rule.level,
                        "trigger": trigger,
                        "escalated_to": target,
                    },
                    reason=f"{trigger} on stage {error.sla_stage}",
                )

        if created:
            self.db.add(
                SLAEvent(
                    error_id=error.error_id,
                    stage=error.sla_stage or "RESPOND",
                    event_type=SLAEventType.BREACH
                    if trigger == "BREACH"
                    else SLAEventType.AT_RISK,
                    occurred_at=now,
                    owner_role=error.sla_clock_owner_role,
                    due_at=error.sla_due_at,
                )
            )
            await self.db.flush()

        return created

    async def acknowledge(
        self, escalation: Escalation, user: User, next_action: str, eta: datetime | None
    ) -> Escalation:
        """Acknowledging alone is not enough — a commitment is recorded with it."""
        escalation.acknowledged_at = datetime.now(timezone.utc)
        escalation.acknowledged_by = user.user_id
        escalation.next_action = next_action
        escalation.eta = eta
        await self.audit.create(
            action="ESCALATION_ACKNOWLEDGED",
            actor_id=user.user_id,
            error_id=escalation.error_id,
            after_value={"next_action": next_action, "eta": eta.isoformat() if eta else None},
        )
        await self.db.flush()
        return escalation
