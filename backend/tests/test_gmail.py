"""Gmail integration tests: QEMS-ID parsing, OAuth config validation, unknown
error/sender handling -- all against a fake provider, never real Gmail/network.
"""

import uuid
from datetime import date

import pytest

from app.models import AuditLog, Category, Department, SLAPolicy
from app.services import gmail_inbound_service
from app.services.error_service import ErrorService
from app.services.notification_providers import GmailProvider, _extract_email
from sqlalchemy import select
from tests.test_error_lifecycle import _make_user


def test_qems_id_regex_matches_standard_code():
    match = gmail_inbound_service.QEMS_ID_RE.search("Re: Action Required: QEMS-2026-00124")
    assert match is not None
    assert match.group(0) == "QEMS-2026-00124"


def test_qems_id_regex_does_not_match_malformed_code():
    assert gmail_inbound_service.QEMS_ID_RE.search("QEMS-26-124") is None
    assert gmail_inbound_service.QEMS_ID_RE.search("just a normal reply, no code here") is None


def test_extract_email_from_display_name_header():
    assert _extract_email("Jane Doe <jane@corp.com>") == "jane@corp.com"


def test_extract_email_from_bare_address():
    assert _extract_email("jane@corp.com") == "jane@corp.com"


@pytest.fixture
def gmail_unconfigured(monkeypatch):
    # The dev .env may hold real Gmail credentials; these tests must never touch them.
    monkeypatch.setattr("app.services.notification_providers.settings.google_refresh_token", "")


def test_gmail_provider_not_configured_returns_no_replies(gmail_unconfigured):
    provider = GmailProvider()
    assert provider.is_configured() is False
    assert provider.fetch_unread_replies() == []


class _FakeGmailProvider:
    """Stands in for a configured GmailProvider without ever touching the network."""

    def __init__(self, replies):
        self._replies = replies
        self.marked_processed = []

    def is_configured(self):
        return True

    def fetch_unread_replies(self):
        return self._replies

    def mark_processed(self, gmail_id):
        self.marked_processed.append(gmail_id)


@pytest.mark.asyncio
async def test_process_inbound_skipped_when_gmail_not_configured(db_session, gmail_unconfigured):
    summary = await gmail_inbound_service.process_inbound(db_session)
    assert summary["skipped"] is True


async def _make_error_for_gmail(session):
    tag = uuid.uuid4().hex[:8]
    department = Department(name=f"Gmail Dept {tag}")
    sla_policy = SLAPolicy(severity="High", sla_hours=999999)
    session.add_all([department, sla_policy])
    await session.flush()
    category = Category(name=f"Gmail Category {tag}", sla_policy_id=sla_policy.sla_policy_id)
    session.add(category)
    await session.flush()

    raiser = await _make_user(session, "Department Owner", department.department_id, f"raiser_gmail_{tag}@qemscorp.dev")
    assignee = await _make_user(session, "QA Reviewer", department.department_id, f"assignee_gmail_{tag}@qemscorp.dev")
    error = await ErrorService(session).create_error(
        title="Gmail inbound test",
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
    return error, raiser, assignee


@pytest.mark.asyncio
async def test_process_inbound_attaches_reply_from_known_party(db_session, monkeypatch):
    error, raiser, _assignee = await _make_error_for_gmail(db_session)
    fake = _FakeGmailProvider(
        [{"gmail_id": "g1", "from_email": raiser.email, "subject": f"Re: {error.qa_error_code}", "body": "I disagree with this error."}]
    )
    monkeypatch.setattr(gmail_inbound_service, "GmailProvider", lambda: fake)

    summary = await gmail_inbound_service.process_inbound(db_session)
    assert summary == {
        "skipped": False, "fetched": 1, "attached": 1,
        "rejected_unknown_error": 0, "rejected_unknown_sender": 0,
    }
    assert fake.marked_processed == ["g1"]


@pytest.mark.asyncio
async def test_process_inbound_rejects_unknown_qems_code(db_session, monkeypatch):
    fake = _FakeGmailProvider(
        [{"gmail_id": "g2", "from_email": "someone@corp.com", "subject": "Re: QEMS-1999-99999", "body": "text"}]
    )
    monkeypatch.setattr(gmail_inbound_service, "GmailProvider", lambda: fake)

    summary = await gmail_inbound_service.process_inbound(db_session)
    assert summary["rejected_unknown_error"] == 1
    assert summary["attached"] == 0

    logged = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "GMAIL_REPLY_REJECTED"))
    ).scalars().all()
    assert any("QEMS-1999-99999" in (row.reason or "") for row in logged)


@pytest.mark.asyncio
async def test_process_inbound_rejects_sender_not_party_to_error(db_session, monkeypatch):
    error, _raiser, _assignee = await _make_error_for_gmail(db_session)
    fake = _FakeGmailProvider(
        [{"gmail_id": "g3", "from_email": "stranger@corp.com", "subject": error.qa_error_code, "body": "I want in on this"}]
    )
    monkeypatch.setattr(gmail_inbound_service, "GmailProvider", lambda: fake)

    summary = await gmail_inbound_service.process_inbound(db_session)
    assert summary["rejected_unknown_sender"] == 1
    assert summary["attached"] == 0
    assert fake.marked_processed == ["g3"]  # still marked read -- never left to be reprocessed forever


@pytest.mark.asyncio
async def test_process_inbound_ignores_mail_with_no_qems_code(db_session, monkeypatch):
    fake = _FakeGmailProvider(
        [{"gmail_id": "g4", "from_email": "someone@corp.com", "subject": "Unrelated newsletter", "body": "buy now"}]
    )
    monkeypatch.setattr(gmail_inbound_service, "GmailProvider", lambda: fake)

    summary = await gmail_inbound_service.process_inbound(db_session)
    assert summary["fetched"] == 1
    assert summary["attached"] == 0
    assert summary["rejected_unknown_error"] == 0  # never even looked for one
    assert fake.marked_processed == ["g4"]
