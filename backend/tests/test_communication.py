"""Feature 1 (two-way communication) tests: create/list, authorization, attachments,
read status, ordering -- run against the real dev Postgres per conftest.py's convention,
rolled back after each test.
"""

import uuid
from datetime import date

import pytest

from app.api.v1.routers.messages import (
    create_message,
    list_messages,
    mark_message_read,
    upload_attachment,
)
from app.core.exceptions import PermissionDeniedError, ValidationError
from app.models import Category, Department, MessageType, SLAPolicy
from app.schemas.message import MessageCreateRequest
from app.services.error_service import ErrorService
from tests.test_error_lifecycle import _make_user


async def _make_error_with_parties(session):
    tag = uuid.uuid4().hex[:8]
    department = Department(name=f"Comms Test Dept {tag}")
    other_department = Department(name=f"Comms Test Dept Other {tag}")
    sla_policy = SLAPolicy(severity="High", sla_hours=999999)
    session.add_all([department, other_department, sla_policy])
    await session.flush()

    category = Category(name=f"Comms Test Category {tag}", sla_policy_id=sla_policy.sla_policy_id)
    session.add(category)
    await session.flush()

    qa_user = await _make_user(session, "QA Reviewer", department.department_id, f"qa_comms_{tag}@qemscorp.dev")
    owner_user = await _make_user(
        session, "Department Owner", department.department_id, f"owner_comms_{tag}@qemscorp.dev"
    )
    outsider = await _make_user(
        session, "Viewer", other_department.department_id, f"outsider_comms_{tag}@qemscorp.dev"
    )

    error = await ErrorService(session).create_error(
        title="Communication test error",
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
    return error, qa_user, owner_user, outsider


def test_communication_status_labels_follow_who_sent_last():
    """raised_by is the QA Auditor side, assigned_to is the stakeholder side (spec: "QA
    Auditor Creates QA Error -> Assigns stakeholder") -- the derived status must track
    who is waiting on whom accordingly, not the other way around."""
    from app.models import Error, Message, MessageType
    from app.services.message_service import compute_communication_status

    error = Error(error_id=1, status="Open", raised_by=10, assigned_to=20)

    qa_sent = Message(message_id=1, error_id=1, sender_id=10, message="please respond", message_type=MessageType.TEXT)
    assert compute_communication_status(error, [qa_sent]) == "Awaiting Stakeholder"

    stakeholder_sent = Message(message_id=2, error_id=1, sender_id=20, message="here you go", message_type=MessageType.TEXT)
    assert compute_communication_status(error, [qa_sent, stakeholder_sent]) == "Awaiting QA"

    evidence_request = Message(message_id=3, error_id=1, sender_id=10, message="need proof", message_type=MessageType.EVIDENCE_REQUEST)
    assert compute_communication_status(error, [qa_sent, evidence_request]) == "Evidence Requested"

    evidence_upload = Message(message_id=4, error_id=1, sender_id=20, message="attached", message_type=MessageType.EVIDENCE_UPLOAD)
    assert compute_communication_status(error, [qa_sent, evidence_request, evidence_upload]) == "Response Received"

    resolved_error = Error(error_id=2, status="Resolved", raised_by=10, assigned_to=20)
    assert compute_communication_status(resolved_error, [qa_sent]) == "Resolved"

    assert compute_communication_status(error, []) == "Under Review"


@pytest.mark.asyncio
async def test_create_and_retrieve_message(db_session):
    error, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)

    created = await create_message(
        error.error_id,
        MessageCreateRequest(message="Please review this error and provide supporting evidence."),
        db=db_session,
        user=qa_user,
    )
    assert created.sender_id == qa_user.user_id
    assert created.message_type == MessageType.TEXT

    listing = await list_messages(error.error_id, db=db_session, user=owner_user)
    assert listing.total == 1
    assert listing.items[0].message_id == created.message_id
    assert listing.items[0].sender_name == qa_user.full_name


@pytest.mark.asyncio
async def test_messages_are_ordered_oldest_first(db_session):
    error, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)

    first = await create_message(
        error.error_id, MessageCreateRequest(message="first"), db=db_session, user=qa_user
    )
    second = await create_message(
        error.error_id, MessageCreateRequest(message="second"), db=db_session, user=owner_user
    )

    listing = await list_messages(error.error_id, db=db_session, user=qa_user)
    assert [m.message_id for m in listing.items] == [first.message_id, second.message_id]


@pytest.mark.asyncio
async def test_reply_references_parent_message(db_session):
    error, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)

    parent = await create_message(
        error.error_id, MessageCreateRequest(message="I disagree with this error"), db=db_session, user=owner_user
    )
    reply = await create_message(
        error.error_id,
        MessageCreateRequest(message="Please upload the updated document.", parent_message_id=parent.message_id),
        db=db_session,
        user=qa_user,
    )
    assert reply.parent_message_id == parent.message_id


@pytest.mark.asyncio
async def test_reply_to_message_on_another_error_is_rejected(db_session):
    error_a, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)
    # Same parties, second error -- isolates the cross-error parent_message_id guard
    # from department/involvement authorization (covered separately above).
    error_b = await ErrorService(db_session).create_error(
        title="Second error, same parties",
        description="desc",
        category_id=error_a.category_id,
        severity="High",
        department_id=error_a.department_id,
        date_discovered=date.today(),
        raised_by=qa_user.user_id,
        assigned_to=owner_user.user_id,
        embedding=None,
        actor=owner_user,
    )

    parent = await create_message(
        error_a.error_id, MessageCreateRequest(message="on error A"), db=db_session, user=qa_user
    )
    with pytest.raises(ValidationError):
        await create_message(
            error_b.error_id,
            MessageCreateRequest(message="on error B", parent_message_id=parent.message_id),
            db=db_session,
            user=owner_user,
        )


@pytest.mark.asyncio
async def test_outsider_cannot_read_or_post_messages(db_session):
    error, qa_user, _owner_user, outsider = await _make_error_with_parties(db_session)
    await create_message(error.error_id, MessageCreateRequest(message="internal"), db=db_session, user=qa_user)

    with pytest.raises(PermissionDeniedError):
        await list_messages(error.error_id, db=db_session, user=outsider)

    with pytest.raises(PermissionDeniedError):
        await create_message(
            error.error_id, MessageCreateRequest(message="injected"), db=db_session, user=outsider
        )


@pytest.mark.asyncio
async def test_unread_count_excludes_own_messages(db_session):
    error, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)

    await create_message(error.error_id, MessageCreateRequest(message="from QA"), db=db_session, user=qa_user)

    # The sender never counts their own message as unread.
    as_sender = await list_messages(error.error_id, db=db_session, user=qa_user)
    assert as_sender.unread_count == 0

    # The counterpart has one unread message waiting.
    as_counterpart = await list_messages(error.error_id, db=db_session, user=owner_user)
    assert as_counterpart.unread_count == 1


@pytest.mark.asyncio
async def test_mark_message_read_updates_state_and_is_idempotent(db_session):
    error, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)
    message = await create_message(
        error.error_id, MessageCreateRequest(message="from QA"), db=db_session, user=qa_user
    )

    result = await mark_message_read(message.message_id, db=db_session, user=owner_user)
    assert result.is_read is True

    # Reading twice is a no-op, not an error.
    result_again = await mark_message_read(message.message_id, db=db_session, user=owner_user)
    assert result_again.is_read is True


@pytest.mark.asyncio
async def test_sender_reading_own_message_does_not_mark_it_read_by_them():
    """A sender's own message is never 'read' in the sense that matters (someone else
    saw it) just because the sender is the one who fetched it back."""
    from app.models import Message
    from app.services.message_service import MessageService

    class _FakeDB:
        async def flush(self):
            pass

    message = Message(message_id=1, error_id=1, sender_id=42, message="hi", is_read=False)

    class _FakeUser:
        user_id = 42

    service = MessageService.__new__(MessageService)
    service.db = _FakeDB()
    result = await service.mark_read(message, _FakeUser())
    assert result.is_read is False


@pytest.mark.asyncio
async def test_attachment_upload_and_presigned_download(db_session, monkeypatch):
    """Exercises add_attachment/presign_attachment against a fake storage backend (no
    real S3/MinIO dependency for this test) -- same isolation approach as mocking any
    other external I/O boundary; the authorization + persistence logic is what's under
    test here, not boto3 itself (that's exercised for real by
    test_error_lifecycle.test_evidence_upload_response_includes_hash_and_uploader)."""
    import app.services.message_service as message_service_module

    uploaded = {}

    async def fake_upload(key, body, content_type):
        uploaded["key"] = key

    async def fake_presign(key, download_name, ttl=300):
        return f"https://storage.example/{key}?signed=1"

    async def fake_delete(key):
        pass

    monkeypatch.setattr(message_service_module, "upload_evidence_file", fake_upload)
    monkeypatch.setattr(message_service_module, "presign_evidence_url", fake_presign)
    monkeypatch.setattr(message_service_module, "delete_evidence_file", fake_delete)

    error, qa_user, owner_user, _outsider = await _make_error_with_parties(db_session)
    message = await create_message(
        error.error_id, MessageCreateRequest(message="please see attached"), db=db_session, user=qa_user
    )

    from fastapi import UploadFile
    from starlette.datastructures import Headers
    import io

    upload = UploadFile(
        filename="proof.pdf",
        file=io.BytesIO(b"%PDF-1.4 fake pdf content"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    attachment = await upload_attachment(message.message_id, upload, db=db_session, user=owner_user)
    assert attachment.file_name == "proof.pdf"
    assert uploaded["key"].startswith("messages/")

    # Sending an attachment on a TEXT message reclassifies it as EVIDENCE_UPLOAD, which
    # is what drives the "Response Received" derived communication status.
    listing = await list_messages(error.error_id, db=db_session, user=qa_user)
    assert listing.items[0].message_type == MessageType.EVIDENCE_UPLOAD
    assert listing.items[0].attachments[0].file_name == "proof.pdf"


@pytest.mark.asyncio
async def test_attachment_rejects_disallowed_file_type(db_session):
    error, qa_user, _owner_user, _outsider = await _make_error_with_parties(db_session)
    message = await create_message(
        error.error_id, MessageCreateRequest(message="hi"), db=db_session, user=qa_user
    )

    from fastapi import UploadFile
    from starlette.datastructures import Headers
    import io

    upload = UploadFile(
        filename="virus.exe",
        file=io.BytesIO(b"MZ"),
        headers=Headers({"content-type": "application/x-msdownload"}),
    )
    with pytest.raises(ValidationError):
        await upload_attachment(message.message_id, upload, db=db_session, user=qa_user)
