import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Error, ErrorStatus, QADecision, Rebuttal, SLAPolicy, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.decision_repository import DecisionRepository
from app.repositories.error_repository import ErrorRepository
from app.repositories.rebuttal_repository import RebuttalRepository
from app.services.error_state_machine import assert_valid_transition
from app.services.notification_service import NotificationService

logger = logging.getLogger("qems.error_service")


class ErrorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.errors = ErrorRepository(db)
        self.audit = AuditLogRepository(db)
        self.notifications = NotificationService(db)
        self.rebuttals = RebuttalRepository(db)
        self.decisions = DecisionRepository(db)

    async def _compute_due_at(self, category_id: int, created_at: datetime) -> datetime | None:
        result = await self.db.execute(
            select(SLAPolicy.sla_hours)
            .join(Category, Category.sla_policy_id == SLAPolicy.sla_policy_id)
            .where(Category.category_id == category_id)
        )
        sla_hours = result.scalar_one_or_none()
        if sla_hours is None:
            return None
        return created_at + timedelta(hours=sla_hours)

    async def create_error(
        self,
        *,
        title: str,
        description: str,
        category_id: int,
        severity: str,
        department_id: int,
        date_discovered: date,
        raised_by: int,
        assigned_to: int | None,
        embedding: list[float] | None,
        actor: User,
    ) -> Error:
        now = datetime.now(timezone.utc)
        due_at = await self._compute_due_at(category_id, now)

        error = Error(
            qa_error_code="PENDING",  # replaced below once error_id is known
            title=title,
            description=description,
            category_id=category_id,
            severity=severity,
            status=ErrorStatus.OPEN,
            department_id=department_id,
            raised_by=raised_by,
            assigned_to=assigned_to,
            date_discovered=date_discovered,
            due_at=due_at,
            description_embedding=embedding,
        )
        await self.errors.add(error)

        # Section 4.4: QEMS-YYYY-NNNNN, server-side, DB-sequence-backed (error_id), immutable once set.
        error.qa_error_code = f"QEMS-{now.year}-{error.error_id:05d}"
        await self.db.flush()

        await self.audit.create(
            actor_id=actor.user_id,
            action="ERROR_CREATED",
            error_id=error.error_id,
            after_value={"status": error.status, "qa_error_code": error.qa_error_code},
        )

        if assigned_to:
            await self.notifications.notify(
                recipient_id=assigned_to,
                subject=f"[{error.qa_error_code}] New error assigned to you",
                error_id=error.error_id,
                body=(
                    f"A new QA error has been assigned to you.\n\n"
                    f"Error: {error.qa_error_code} — {title}\n"
                    f"Severity: {severity}\n"
                    f"Due: {due_at.isoformat() if due_at else 'n/a'}\n\n"
                    f"{description}"
                ),
            )

        return error

    async def transition_status(
        self, error: Error, target_status: str, actor: User, admin_override: bool = False
    ) -> Error:
        is_admin = "Admin" in actor.role_names
        assert_valid_transition(error.status, target_status, admin_override=admin_override and is_admin)

        before = {"status": error.status}
        error.status = target_status
        if target_status == ErrorStatus.CLOSED:
            error.closed_at = datetime.now(timezone.utc)
        await self.db.flush()

        await self.audit.create(
            actor_id=actor.user_id,
            action="ERROR_STATUS_CHANGED" if not admin_override else "ERROR_STATUS_ADMIN_OVERRIDE",
            error_id=error.error_id,
            before_value=before,
            after_value={"status": error.status},
        )
        return error

    async def submit_rebuttal(self, error: Error, justification: str, actor: User) -> Rebuttal:
        """Section 4.8: Department Owner disputes an error; routes to QA for review."""
        assert_valid_transition(error.status, ErrorStatus.REBUTTAL_RAISED)

        rebuttal = Rebuttal(error_id=error.error_id, raised_by=actor.user_id, justification=justification)
        await self.rebuttals.add(rebuttal)
        await self.transition_status(error, ErrorStatus.REBUTTAL_RAISED, actor)

        await self.notifications.notify(
            recipient_id=error.raised_by,
            subject=f"[{error.qa_error_code}] Rebuttal raised for review",
            error_id=error.error_id,
            body=(
                f"A rebuttal has been raised on {error.qa_error_code} — {error.title}.\n\n"
                f"Justification:\n{justification}"
            ),
        )
        return rebuttal

    async def record_decision(
        self, error: Error, decision: str, notes: str, actor: User
    ) -> QADecision:
        """Section 4.9: QA final decision. Closes the workflow; only Admin may edit further (logged)."""
        if error.status != ErrorStatus.QA_DECISION_PENDING:
            assert_valid_transition(error.status, ErrorStatus.QA_DECISION_PENDING)
            await self.transition_status(error, ErrorStatus.QA_DECISION_PENDING, actor)

        qa_decision = QADecision(
            error_id=error.error_id, decided_by=actor.user_id, decision=decision, notes=notes
        )
        await self.decisions.add(qa_decision)

        if decision == "Escalated":
            # Stays in QA Decision Pending for a senior reviewer; workflow is not closed.
            await self.audit.create(
                actor_id=actor.user_id,
                action="ERROR_ESCALATED",
                error_id=error.error_id,
                after_value={"notes": notes},
            )
        else:
            next_status = ErrorStatus.RESOLVED if decision == "Resolved" else ErrorStatus.REJECTED
            await self.transition_status(error, next_status, actor)
            await self.transition_status(error, ErrorStatus.CLOSED, actor)

        await self.notifications.notify(
            recipient_id=error.raised_by,
            subject=f"[{error.qa_error_code}] QA decision recorded: {decision}",
            error_id=error.error_id,
            body=(
                f"A QA decision has been recorded on {error.qa_error_code} — {error.title}.\n\n"
                f"Decision: {decision}\n"
                f"Notes:\n{notes}"
            ),
        )
        return qa_decision
