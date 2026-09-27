"""Dev seed: realistic activity across every transactional table, driven through the
same service-layer functions the real app calls (not raw INSERTs) -- so audit_logs,
error_transitions, and notifications populate as genuine side effects, not fabricated
rows.

Requires app.tasks.seed, app.tasks.seed_users, and app.tasks.seed_history to have
already run (roles/departments/categories/users, and a corpus large enough for the
Quality Signal engine to find real neighbours).

Does NOT populate ai_cost_ledger or ai_prompt_versions: both only ever get written on a
successful OpenAI call (see ai_gateway.py's recurrence_narrative -- it raises
AIUnavailable before either table is touched when no usable API key is configured), and
fabricating fake cost/usage rows would misrepresent real spend data. Configure a real
OPENAI_API_KEY and re-run this script to populate those two for real.

Run with: python -m app.tasks.seed_activity
"""

import asyncio
import io
from datetime import date, timedelta

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.datastructures import Headers

from app.api.v1.routers.evidence import upload_evidence
from app.core.db import AsyncSessionLocal
from app.models import BusinessCalendar, CalendarHoliday, Category, Department, Error, ErrorStatus, User, UserRole
from app.services.error_service import ErrorService
from app.services.escalation_service import EscalationService
from app.services.signal_service import SignalService


async def seed_activity() -> None:
    async with AsyncSessionLocal() as db:
        users = {
            u.email: u
            for u in (
                await db.execute(select(User).options(selectinload(User.user_roles).selectinload(UserRole.role)))
            )
            .scalars()
            .all()
        }
        if not users:
            print("No users found -- run app.tasks.seed and app.tasks.seed_users first.")
            return
        qa, owner = users["qa@qemscorp.dev"], users["owner@qemscorp.dev"]

        category = (await db.execute(select(Category).limit(1))).scalars().first()
        department = (await db.execute(select(Department).limit(1))).scalars().first()
        if category is None or department is None:
            print("No categories/departments found -- run app.tasks.seed first.")
            return

        error_service = ErrorService(db)

        # 1) Assigned on creation -> populates notifications.
        await error_service.create_error(
            title="Customer refund processed twice",
            description="Duplicate refund issued due to a race condition in the refund queue.",
            category_id=category.category_id, severity="High", department_id=department.department_id,
            date_discovered=date.today(), raised_by=owner.user_id, assigned_to=qa.user_id,
            embedding=None, actor=owner,
        )
        await db.commit()

        # 2) Full lifecycle with evidence -> rebuttals, qa_decisions, evidence.
        lifecycle_error = await error_service.create_error(
            title="Shipping label printed with wrong address",
            description="Warehouse system printed an outdated address for a recently-updated order.",
            category_id=category.category_id, severity="Medium", department_id=department.department_id,
            date_discovered=date.today(), raised_by=owner.user_id, assigned_to=None,
            embedding=None, actor=owner,
        )
        await db.commit()

        upload = UploadFile(
            filename="warehouse-screenshot.png",
            file=io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 128),
            headers=Headers({"content-type": "image/png"}),
        )
        await upload_evidence(lifecycle_error.error_id, upload, db=db, user=owner)

        lifecycle_error = await db.get(Error, lifecycle_error.error_id)
        await error_service.transition_status(lifecycle_error, ErrorStatus.IN_REVIEW, qa)
        await error_service.submit_rebuttal(
            lifecycle_error,
            "Address was correct at label print time; a system delay caused the mismatch.",
            owner,
        )
        await error_service.transition_status(lifecycle_error, ErrorStatus.QA_DECISION_PENDING, qa)
        await error_service.record_decision(
            lifecycle_error, "Resolved", "Confirmed timing issue; added an address-refresh check before print.", qa
        )
        await db.commit()

        # 3) A Critical error fired straight to the escalation engine -> escalations + sla_events.
        breached_error = await error_service.create_error(
            title="Critical: payment gateway timeout not retried",
            description="Payment gateway timeouts are not triggering automatic retries, causing failed checkouts.",
            category_id=category.category_id, severity="Critical", department_id=department.department_id,
            date_discovered=date.today() - timedelta(days=2), raised_by=owner.user_id, assigned_to=None,
            embedding=None, actor=owner,
        )
        await db.commit()
        breached_error = await db.get(Error, breached_error.error_id)
        # Same technique tests/test_sla_worker.py uses: EscalationService.fire() trusts the
        # caller's trigger classification rather than re-deriving it, so this doesn't need a
        # real elapsed SLA window to produce a genuine escalation + sla_event row.
        await EscalationService(db).fire(breached_error, "BREACH")
        await db.commit()

        # 4) Quality Signal on an already-clustered historical error (from seed_history) so it
        #    has real neighbours to find, rather than a fresh one-off that would just report
        #    NO_COMPARABLE_FINDINGS.
        clustered = (
            await db.execute(select(Error).where(Error.title.ilike("%identity%")).limit(1))
        ).scalars().first()
        if clustered:
            await SignalService(db).compute(clustered)
            await db.commit()
        else:
            print("No clustered historical error found -- run app.tasks.seed_history first for a real signal.")

        # 5) A couple of holidays on the default calendar.
        calendar = (await db.execute(select(BusinessCalendar).limit(1))).scalars().first()
        if calendar:
            this_year = date.today().year
            db.add_all(
                [
                    CalendarHoliday(calendar_id=calendar.calendar_id, holiday_date=date(this_year, 12, 25), name="Christmas Day"),
                    CalendarHoliday(calendar_id=calendar.calendar_id, holiday_date=date(this_year, 1, 1), name="New Year's Day"),
                ]
            )
            await db.commit()

    print("Activity seed complete: errors, evidence, rebuttals, decisions, escalations, an AI insight, and holidays populated.")
    print("ai_cost_ledger / ai_prompt_versions left empty -- need a real OPENAI_API_KEY to populate for real.")


if __name__ == "__main__":
    asyncio.run(seed_activity())
