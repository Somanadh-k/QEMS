"""Feature 2 (event-driven notifications) tests: dispatch, template rendering, retry,
and Gmail-unavailable fallback -- run against the real dev Postgres per conftest.py.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Category, Department, Notification, NotificationEvent, NotificationStatus, SLAPolicy
from app.repositories.notification_repository import NotificationRepository
from app.services.error_service import ErrorService
from app.services.notification_providers import GmailProvider, NotificationSendError, SmtpProvider
from app.services.notification_service import NotificationService
from app.services.notification_templates import render
from tests.test_error_lifecycle import _make_user


def test_template_render_substitutes_known_variables():
    rendered = render("Action Required: {{error_id}} due {{due_date}}", {"error_id": "QEMS-2026-00124", "due_date": "25 Sep"})
    assert rendered == "Action Required: QEMS-2026-00124 due 25 Sep"


def test_template_render_missing_variable_becomes_empty_string():
    # A template referencing a variable the caller didn't supply must never 500 at send
    # time -- it renders blank instead (notification_templates.render's whole point).
    assert render("Hello {{missing}}!", {}) == "Hello !"


def test_gmail_provider_not_configured_by_default(monkeypatch):
    monkeypatch.setattr("app.services.notification_providers.settings.google_client_id", "")
    monkeypatch.setattr("app.services.notification_providers.settings.gmail_sender", "")
    assert GmailProvider.is_configured() is False


async def _make_error(session, tag_prefix="notif"):
    tag = uuid.uuid4().hex[:8]
    department = Department(name=f"{tag_prefix} Dept {tag}")
    sla_policy = SLAPolicy(severity="High", sla_hours=999999)
    session.add_all([department, sla_policy])
    await session.flush()

    category = Category(name=f"{tag_prefix} Category {tag}", sla_policy_id=sla_policy.sla_policy_id)
    session.add(category)
    await session.flush()

    qa_user = await _make_user(session, "QA Reviewer", department.department_id, f"qa_{tag_prefix}_{tag}@qemscorp.dev")
    owner_user = await _make_user(
        session, "Department Owner", department.department_id, f"owner_{tag_prefix}_{tag}@qemscorp.dev"
    )
    error = await ErrorService(session).create_error(
        title="Notification test error",
        description="desc",
        category_id=category.category_id,
        severity="High",
        department_id=department.department_id,
        date_discovered=date.today(),
        raised_by=qa_user.user_id,
        assigned_to=owner_user.user_id,
        embedding=None,
        actor=owner_user,
    )
    return error, qa_user, owner_user


@pytest.mark.asyncio
async def test_dispatch_event_uses_template_when_ai_disabled(db_session, monkeypatch):
    monkeypatch.setattr("app.services.notification_service.settings.ai_narration_enabled", False)
    error, qa_user, owner_user = await _make_error(db_session)

    notification = await NotificationService(db_session).dispatch_event(
        NotificationEvent.MESSAGE_RECEIVED,
        recipient_id=owner_user.user_id,
        error=error,
        context={"sender": qa_user.full_name, "message": "please review"},
    )

    assert notification.subject == f"New message on {error.qa_error_code}"
    assert "please review" in notification.content
    assert notification.event_type == NotificationEvent.MESSAGE_RECEIVED


@pytest.mark.asyncio
async def test_dispatch_event_falls_back_to_smtp_when_gmail_not_configured(db_session, monkeypatch):
    """Gmail unavailable/unconfigured must never break notification delivery -- the
    service transparently uses SmtpProvider instead (spec: "Gmail failure" /
    "OAuth configuration validation" test)."""
    monkeypatch.setattr("app.services.notification_service.settings.ai_narration_enabled", False)
    monkeypatch.setattr(GmailProvider, "is_configured", staticmethod(lambda: False))

    sent = {}

    async def fake_smtp_send(self, to_address, subject, body):
        sent["to"] = to_address
        sent["subject"] = subject
        return "fake-message-id"

    monkeypatch.setattr(SmtpProvider, "send", fake_smtp_send)

    error, qa_user, owner_user = await _make_error(db_session)
    notification = await NotificationService(db_session).dispatch_event(
        NotificationEvent.REBUTTAL_SUBMITTED,
        recipient_id=qa_user.user_id,
        error=error,
        context={"sender": owner_user.full_name, "message": "I disagree"},
    )

    assert notification.status == NotificationStatus.SENT
    assert sent["to"] == qa_user.email


@pytest.mark.asyncio
async def test_dispatch_event_marks_failed_and_logs_on_send_error(db_session, monkeypatch):
    """Never silently swallow a Gmail/SMTP failure -- it must be recorded as FAILED with
    a NotificationLog row carrying the error message, and the error-management workflow
    itself must still have succeeded (the error/rebuttal this notification is *about* is
    already committed by the time dispatch_event runs)."""
    monkeypatch.setattr("app.services.notification_service.settings.ai_narration_enabled", False)
    monkeypatch.setattr(GmailProvider, "is_configured", staticmethod(lambda: False))

    async def failing_send(self, to_address, subject, body):
        raise NotificationSendError("SMTP server unreachable")

    monkeypatch.setattr(SmtpProvider, "send", failing_send)

    error, qa_user, owner_user = await _make_error(db_session)
    notification = await NotificationService(db_session).dispatch_event(
        NotificationEvent.EVIDENCE_REQUESTED,
        recipient_id=owner_user.user_id,
        error=error,
        context={"message": "please upload the updated document"},
    )

    assert notification.status == NotificationStatus.FAILED
    assert notification.next_retry_at is not None

    from app.models import NotificationLog
    from sqlalchemy import select as sa_select

    logs = (
        await db_session.execute(
            sa_select(NotificationLog).where(NotificationLog.notification_id == notification.notification_id)
        )
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == NotificationStatus.FAILED
    assert "unreachable" in logs[0].error_message


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure(db_session, monkeypatch):
    """Attempt 1 fails, attempt 2 (via NotificationService.retry) succeeds -- the
    exponential-backoff retry loop the spec asks for."""
    monkeypatch.setattr("app.services.notification_service.settings.ai_narration_enabled", False)
    monkeypatch.setattr(GmailProvider, "is_configured", staticmethod(lambda: False))

    call_count = {"n": 0}

    async def flaky_send(self, to_address, subject, body):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise NotificationSendError("Failed")
        return "ok-message-id"

    monkeypatch.setattr(SmtpProvider, "send", flaky_send)

    error, qa_user, owner_user = await _make_error(db_session)
    # _make_error assigns qa_user, which itself fires (and, via flaky_send, fails) an
    # ERROR_ASSIGNED notification -- reset the counter so it doesn't consume this test's
    # first "fail once" attempt before the explicit dispatch below even runs.
    call_count["n"] = 0
    service = NotificationService(db_session)
    notification = await service.dispatch_event(
        NotificationEvent.DECISION_UPDATED,
        recipient_id=owner_user.user_id,
        error=error,
        context={"decision": "Resolved", "message": "fixed"},
    )
    assert notification.status == NotificationStatus.FAILED
    assert notification.retry_count == 0

    await service.retry(notification)
    assert notification.status == NotificationStatus.SENT
    assert notification.retry_count == 1
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_retries(db_session, monkeypatch):
    """Bounded retry, not an uncontrolled loop: list_retryable stops returning a
    notification once it has exhausted settings.notification_max_retries."""
    notification = Notification(
        recipient_id=1, channel="email", subject="x", status=NotificationStatus.FAILED,
        retry_count=3, next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(notification)
    await db_session.flush()

    retryable = await NotificationRepository(db_session).list_retryable(datetime.now(timezone.utc), max_retries=3)
    assert notification.notification_id not in [n.notification_id for n in retryable]


@pytest.mark.asyncio
async def test_error_assignment_dispatches_error_assigned_notification(db_session, monkeypatch):
    """ErrorService.create_error with an assignee must fire ERROR_ASSIGNED end-to-end."""
    monkeypatch.setattr("app.services.notification_service.settings.ai_narration_enabled", False)
    monkeypatch.setattr(GmailProvider, "is_configured", staticmethod(lambda: False))

    async def noop_send(self, to_address, subject, body):
        return "noop"

    monkeypatch.setattr(SmtpProvider, "send", noop_send)

    tag = uuid.uuid4().hex[:8]
    department = Department(name=f"Assign Dept {tag}")
    sla_policy = SLAPolicy(severity="High", sla_hours=48)
    db_session.add_all([department, sla_policy])
    await db_session.flush()
    category = Category(name=f"Assign Category {tag}", sla_policy_id=sla_policy.sla_policy_id)
    db_session.add(category)
    await db_session.flush()

    raiser = await _make_user(db_session, "Department Owner", department.department_id, f"raiser_{tag}@qemscorp.dev")
    assignee = await _make_user(db_session, "QA Reviewer", department.department_id, f"assignee_{tag}@qemscorp.dev")

    error = await ErrorService(db_session).create_error(
        title="Assignment notification test",
        description="desc",
        category_id=category.category_id,
        severity="High",
        department_id=department.department_id,
        date_discovered=date.today(),
        raised_by=raiser.user_id,
        assigned_to=assignee.user_id,
        embedding=None,
        actor=raiser,
    )

    notifications = await NotificationRepository(db_session).list_by_error(error.error_id)
    assert any(n.event_type == NotificationEvent.ERROR_ASSIGNED and n.recipient_id == assignee.user_id for n in notifications)
