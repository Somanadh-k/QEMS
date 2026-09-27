import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.core.security import hash_password
from app.models import Category, Department, ErrorStatus, Role, SLAPolicy, User, UserRole
from app.repositories.error_repository import ErrorRepository
from app.services.error_service import ErrorService


async def _get_or_create_role(session, role_name: str) -> Role:
    existing = (await session.execute(select(Role).where(Role.role_name == role_name))).scalar_one_or_none()
    if existing:
        return existing
    role = Role(role_name=role_name)
    session.add(role)
    await session.flush()
    return role


async def _make_user(session, role_name: str, department_id: int, email: str) -> User:
    role = await _get_or_create_role(session, role_name)

    user = User(
        full_name=role_name, email=email, password_hash=hash_password("x"), department_id=department_id
    )
    session.add(user)
    await session.flush()

    session.add(UserRole(user_id=user.user_id, role_id=role.role_id))
    await session.flush()
    await session.refresh(user, attribute_names=["user_roles"])
    for ur in user.user_roles:
        await session.refresh(ur, attribute_names=["role"])
    return user


async def _make_category_and_department(session) -> tuple[Category, Department]:
    # Unique per call (not a hardcoded literal) since these tests run against the real
    # dev Postgres, not an isolated per-run database -- see test_error_authorization.py's
    # identical convention, adopted here after a stale "Test Dept" row from a prior
    # non-clean run (e.g. a killed process) collided with this fixture's unique constraint.
    tag = uuid.uuid4().hex[:8]
    department = Department(name=f"Test Dept {tag}")
    sla_policy = SLAPolicy(severity="High", sla_hours=24)
    session.add_all([department, sla_policy])
    await session.flush()

    category = Category(name=f"Test Category {tag}", sla_policy_id=sla_policy.sla_policy_id)
    session.add(category)
    await session.flush()
    return category, department


@pytest.mark.asyncio
async def test_qa_error_code_is_generated_and_immutable(db_session):
    category, department = await _make_category_and_department(db_session)
    qa_user = await _make_user(db_session, "QA Reviewer", department.department_id, "qa1@qemscorp.dev")

    service = ErrorService(db_session)
    error = await service.create_error(
        title="Test error",
        description="Something went wrong",
        category_id=category.category_id,
        severity="High",
        department_id=department.department_id,
        date_discovered=date.today(),
        raised_by=qa_user.user_id,
        assigned_to=None,
        embedding=None,
        actor=qa_user,
    )

    assert error.qa_error_code.startswith("QEMS-")
    assert error.qa_error_code.endswith(f"{error.error_id:05d}")
    assert error.status == ErrorStatus.OPEN
    assert error.due_at is not None  # SLA due date computed from category's policy


@pytest.mark.asyncio
async def test_full_lifecycle_open_to_closed(db_session):
    category, department = await _make_category_and_department(db_session)
    qa_user = await _make_user(db_session, "QA Reviewer", department.department_id, "qa2@qemscorp.dev")
    owner_user = await _make_user(db_session, "Department Owner", department.department_id, "owner2@qemscorp.dev")

    service = ErrorService(db_session)
    error = await service.create_error(
        title="Lifecycle test",
        description="desc",
        category_id=category.category_id,
        severity="Medium",
        department_id=department.department_id,
        date_discovered=date.today(),
        raised_by=qa_user.user_id,
        assigned_to=None,
        embedding=None,
        actor=qa_user,
    )

    await service.transition_status(error, ErrorStatus.IN_REVIEW, qa_user)
    assert error.status == ErrorStatus.IN_REVIEW

    await service.submit_rebuttal(error, "I disagree", owner_user)
    assert error.status == ErrorStatus.REBUTTAL_RAISED

    await service.record_decision(error, "Resolved", "Confirmed fixed", qa_user)
    assert error.status == ErrorStatus.CLOSED
    assert error.closed_at is not None

    # Re-fetch through the repository's eager-loaded query to check the child collections
    # (the `error` object above never loaded them, and async ORM can't lazy-load outside
    # a greenlet context).
    reloaded = await ErrorRepository(db_session).get_by_id(error.error_id)
    assert len(reloaded.rebuttals) == 1
    assert len(reloaded.decisions) == 1


@pytest.mark.asyncio
async def test_invalid_transition_raises_conflict(db_session):
    category, department = await _make_category_and_department(db_session)
    qa_user = await _make_user(db_session, "QA Reviewer", department.department_id, "qa3@qemscorp.dev")

    service = ErrorService(db_session)
    error = await service.create_error(
        title="Bad transition test",
        description="desc",
        category_id=category.category_id,
        severity="Low",
        department_id=department.department_id,
        date_discovered=date.today(),
        raised_by=qa_user.user_id,
        assigned_to=None,
        embedding=None,
        actor=qa_user,
    )

    with pytest.raises(ConflictError):
        await service.transition_status(error, ErrorStatus.CLOSED, qa_user)


@pytest.mark.asyncio
async def test_evidence_upload_response_includes_hash_and_uploader(db_session):
    """QEMS_Demo_Runbook.md Step 6 narrates the SHA-256 hash and the uploader as visible
    evidence metadata; both are real columns on Evidence but were previously missing from
    EvidenceUploadResponse/EvidenceSummary, so the API silently dropped them.

    upload_evidence() commits internally (it's a router function, not a service), so
    calling it directly with db_session -- as every other test in this file does with
    non-committing service calls -- persists its rows for real past this fixture's final
    rollback. A unique email avoids colliding on repeat runs, matching the same
    already-established convention in test_error_authorization.py.
    """
    import io
    import uuid

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from app.api.v1.routers.evidence import upload_evidence

    category, department = await _make_category_and_department(db_session)
    qa_user = await _make_user(
        db_session, "QA Reviewer", department.department_id, f"qa_evidence_{uuid.uuid4().hex[:8]}@qemscorp.dev"
    )
    error = await ErrorService(db_session).create_error(
        title="Evidence metadata test",
        description="desc",
        category_id=category.category_id,
        severity="Low",
        department_id=department.department_id,
        date_discovered=date.today(),
        raised_by=qa_user.user_id,
        assigned_to=None,
        embedding=None,
        actor=qa_user,
    )

    upload = UploadFile(
        filename="evidence.png",
        file=io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64),
        headers=Headers({"content-type": "image/png"}),
    )

    response = await upload_evidence(error.error_id, upload, db=db_session, user=qa_user)

    assert response.uploaded_by == qa_user.user_id
    assert response.sha256 is not None and len(response.sha256) == 64
