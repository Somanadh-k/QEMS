"""Regression tests for D-07 / D-07-EVIDENCE: department/ownership scoping on direct
error and evidence reads.

Reuses the user builder from test_error_lifecycle.py rather than duplicating it (see the
existing cross-module import convention in test_audit_chain.py / test_audit_concurrency.py,
which import from tests.conftest). Departments/categories/emails are generated with a
per-call unique tag rather than reusing test_error_lifecycle's hardcoded "Test Dept"
literal, since these tests run against the real dev Postgres (per conftest.py), not an
isolated per-run test database, and must not collide with each other or with unrelated
data across repeated runs.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.api.v1.routers.errors import get_error
from app.api.v1.routers.evidence import get_evidence_url
from app.core.exceptions import PermissionDeniedError
from app.models import Category, Department, Evidence, SLAPolicy
from app.services.error_service import ErrorService
from tests.test_error_lifecycle import _make_user


async def _make_two_departments_and_error(session):
    """Dept A holds the error under test; Dept B exists only to prove cross-department
    access is denied.

    Uses unique, per-call department/SLA-policy/category names (rather than the
    hardcoded literals in test_error_lifecycle._make_category_and_department) so this
    file's own tests never collide with each other or with residual data across runs,
    given these tests run against the real dev Postgres, not an isolated test database.
    """
    tag = uuid.uuid4().hex[:8]
    dept_a = Department(name=f"Authz Test Dept A {tag}")
    dept_b = Department(name=f"Authz Test Dept B {tag}")
    sla_policy = SLAPolicy(severity="Low", sla_hours=999999)
    session.add_all([dept_a, dept_b, sla_policy])
    await session.flush()

    category = Category(name=f"Authz Test Category {tag}", sla_policy_id=sla_policy.sla_policy_id)
    session.add(category)
    await session.flush()

    qa_a = await _make_user(session, "QA Reviewer", dept_a.department_id, f"qa_authz_a_{tag}@qemscorp.dev")

    error = await ErrorService(session).create_error(
        title="Authorization scoping test",
        description="desc",
        category_id=category.category_id,
        severity="Low",
        department_id=dept_a.department_id,
        date_discovered=date.today(),
        raised_by=qa_a.user_id,
        assigned_to=None,
        embedding=None,
        actor=qa_a,
    )

    evidence = Evidence(
        error_id=error.error_id,
        file_name="authz-test.png",
        file_url="evidence/authz-test.png",
        storage_key="evidence/authz-test.png",
        file_type="image/png",
        file_size_kb=1,
        uploaded_by=qa_a.user_id,
    )
    session.add(evidence)
    await session.flush()

    return dept_a, dept_b, error, evidence, tag


@pytest.mark.asyncio
async def test_admin_can_access_error_in_any_department(db_session):
    dept_a, dept_b, error, _evidence, tag = await _make_two_departments_and_error(db_session)
    admin = await _make_user(db_session, "Admin", dept_b.department_id, f"admin_authz_{tag}@qemscorp.dev")

    result = await get_error(error.error_id, db=db_session, user=admin)
    assert result.error_id == error.error_id


@pytest.mark.asyncio
async def test_qa_reviewer_in_another_department_can_still_access_error(db_session):
    """QA Reviewer is global-scope, matching its existing cross-department duties
    elsewhere in the app (status transitions, decisions, audit verification)."""
    dept_a, dept_b, error, _evidence, tag = await _make_two_departments_and_error(db_session)
    qa_b = await _make_user(db_session, "QA Reviewer", dept_b.department_id, f"qa_authz_b_{tag}@qemscorp.dev")

    result = await get_error(error.error_id, db=db_session, user=qa_b)
    assert result.error_id == error.error_id


@pytest.mark.asyncio
async def test_same_department_user_can_access_error(db_session):
    dept_a, dept_b, error, _evidence, tag = await _make_two_departments_and_error(db_session)
    owner_a = await _make_user(db_session, "Department Owner", dept_a.department_id, f"owner_authz_a_{tag}@qemscorp.dev")

    result = await get_error(error.error_id, db=db_session, user=owner_a)
    assert result.error_id == error.error_id


@pytest.mark.asyncio
async def test_cross_department_user_cannot_access_error(db_session):
    dept_a, dept_b, error, _evidence, tag = await _make_two_departments_and_error(db_session)
    viewer_b = await _make_user(db_session, "Viewer", dept_b.department_id, f"viewer_authz_b_{tag}@qemscorp.dev")

    with pytest.raises(PermissionDeniedError):
        await get_error(error.error_id, db=db_session, user=viewer_b)


@pytest.mark.asyncio
async def test_cross_department_owner_cannot_access_error(db_session):
    """Department Owner (not just Viewer) is also scoped -- the rule is department-based,
    not role-name-based, for any non-global-scope role."""
    dept_a, dept_b, error, _evidence, tag = await _make_two_departments_and_error(db_session)
    owner_b = await _make_user(db_session, "Department Owner", dept_b.department_id, f"owner_authz_b_{tag}@qemscorp.dev")

    with pytest.raises(PermissionDeniedError):
        await get_error(error.error_id, db=db_session, user=owner_b)


@pytest.mark.asyncio
async def test_same_department_user_can_get_evidence_url(db_session):
    dept_a, dept_b, error, evidence, tag = await _make_two_departments_and_error(db_session)
    owner_a = await _make_user(
        db_session, "Department Owner", dept_a.department_id, f"owner_authz_evid_a_{tag}@qemscorp.dev"
    )

    result = await get_evidence_url(evidence.evidence_id, db=db_session, user=owner_a)
    assert "url" in result


@pytest.mark.asyncio
async def test_cross_department_user_cannot_get_evidence_url(db_session):
    dept_a, dept_b, error, evidence, tag = await _make_two_departments_and_error(db_session)
    viewer_b = await _make_user(
        db_session, "Viewer", dept_b.department_id, f"viewer_authz_evid_b_{tag}@qemscorp.dev"
    )

    with pytest.raises(PermissionDeniedError):
        await get_evidence_url(evidence.evidence_id, db=db_session, user=viewer_b)


@pytest.mark.asyncio
async def test_raiser_can_access_own_error_filed_against_another_department(db_session):
    """The department picker on creation lets anyone file against a department that
    isn't their own (e.g. reporting a defect found in another team). Department scoping
    alone would then lock the raiser out of the very error they just filed -- found live
    while walking QEMS_Demo_Runbook.md's Step 3->Step 5 as Department Owner."""
    dept_a, dept_b, _error, _evidence, tag = await _make_two_departments_and_error(db_session)
    owner_b = await _make_user(db_session, "Department Owner", dept_b.department_id, f"owner_authz_raiser_{tag}@qemscorp.dev")

    error = await ErrorService(db_session).create_error(
        title="Filed against another department",
        description="desc",
        category_id=(await db_session.execute(select(Category).where(Category.name.like(f"Authz Test Category {tag}")))).scalar_one().category_id,
        severity="Low",
        department_id=dept_a.department_id,
        date_discovered=date.today(),
        raised_by=owner_b.user_id,
        assigned_to=None,
        embedding=None,
        actor=owner_b,
    )

    result = await get_error(error.error_id, db=db_session, user=owner_b)
    assert result.error_id == error.error_id


@pytest.mark.asyncio
async def test_assignee_can_access_error_in_another_department(db_session):
    dept_a, dept_b, _error, _evidence, tag = await _make_two_departments_and_error(db_session)
    reviewer_b = await _make_user(db_session, "Department Owner", dept_b.department_id, f"assignee_authz_{tag}@qemscorp.dev")
    raiser_a = await _make_user(db_session, "Department Owner", dept_a.department_id, f"raiser_authz_{tag}@qemscorp.dev")

    error = await ErrorService(db_session).create_error(
        title="Assigned across departments",
        description="desc",
        category_id=(await db_session.execute(select(Category).where(Category.name.like(f"Authz Test Category {tag}")))).scalar_one().category_id,
        severity="Low",
        department_id=dept_a.department_id,
        date_discovered=date.today(),
        raised_by=raiser_a.user_id,
        assigned_to=reviewer_b.user_id,
        embedding=None,
        actor=raiser_a,
    )

    result = await get_error(error.error_id, db=db_session, user=reviewer_b)
    assert result.error_id == error.error_id
