import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role, visible_departments
from app.core.db import get_db
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models import User
from app.repositories.error_repository import ErrorRepository
from app.schemas.error import (
    ErrorCreateRequest,
    ErrorCreateResponse,
    ErrorDetailResponse,
    ErrorListResponse,
    ErrorStatusUpdateRequest,
)
from app.services.embedding_service import generate_embedding
from app.services.error_service import ErrorService
from app.services.signal_service import source_hash, source_text

router = APIRouter(prefix="/errors", tags=["errors"])
logger = logging.getLogger("qems.errors")


@router.post("", response_model=ErrorCreateResponse, status_code=201)
async def create_error(
    payload: ErrorCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Section 11.3 — creates a new QA error and generates its QEMS-YYYY-NNNNN code."""
    # Embed at creation. This previously called the legacy AIService, which raises
    # whenever no usable OpenAI key is configured; the exception was swallowed and the
    # error was stored with a NULL vector. Those errors were then invisible to every
    # similarity search until something happened to request their signal, so recurrence
    # and duplicate detection silently missed them. The embedding service falls back to
    # a local embedder, so a vector is always produced.
    embedding: list[float] | None = None
    embedding_model: str | None = None
    try:
        result = await generate_embedding(f"{payload.title}\n{payload.description}")
        embedding, embedding_model = result.vector, result.model
    except Exception:  # noqa: BLE001 — AI is supplementary; never blocks error creation (13.7)
        logger.warning("Embedding generation failed for new error; continuing without it", exc_info=True)

    error = await ErrorService(db).create_error(
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        severity=payload.severity,
        department_id=payload.department_id,
        date_discovered=payload.date_discovered,
        raised_by=user.user_id,
        assigned_to=payload.assigned_to,
        process_id=payload.process_id,
        embedding=embedding,
        actor=user,
    )

    # Record which model produced the vector and a hash of the text it came from, so a
    # description edited later is detectable as stale rather than silently mismatched.
    if embedding is not None:
        error.embedding_model = embedding_model
        error.embedded_at = datetime.now(timezone.utc)
        error.embedding_source_hash = source_hash(error)

    await db.commit()
    return ErrorCreateResponse(
        error_id=error.error_id,
        qa_error_code=error.qa_error_code,
        status=error.status,
        due_at=error.due_at,
        created_at=error.created_at,
    )


@router.get("", response_model=ErrorListResponse)
async def list_errors(
    status: str | None = None,
    department_id: int | None = None,
    severity: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Section 11.3 — results scoped by role/department in a production deployment."""
    items, total = await ErrorRepository(db).list(
        status=status, department_id=department_id, severity=severity, page=page, page_size=page_size
    )
    return ErrorListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{error_id}", response_model=ErrorDetailResponse)
async def get_error(error_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Section 11.3 — full detail including evidence, rebuttal, and decision sub-objects.

    Finding D-07: this previously returned any error to any authenticated user
    regardless of department. Scoped the same way AI neighbour retrieval already is
    (signal.py) -- Admin/QA Reviewer are unrestricted, everyone else is limited to
    their own department, plus whoever raised or is assigned the error -- a department
    picker on creation lets someone file against a department that isn't their own (e.g.
    reporting a defect found in another team), and department scoping alone would then
    lock the very person who filed it out of their own record.
    """
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    visible = visible_departments(user)
    is_involved = user.user_id in (error.raised_by, error.assigned_to)
    if visible is not None and error.department_id not in visible and not is_involved:
        raise PermissionDeniedError(f"You do not have access to error {error_id}")

    return error


@router.patch("/{error_id}/status", response_model=ErrorDetailResponse)
async def update_status(
    error_id: int,
    payload: ErrorStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Section 11.3 — transitions the error per the Section 7.6 state machine."""
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    is_admin_override = payload.admin_override and "Admin" in user.role_names
    error = await ErrorService(db).transition_status(
        error, payload.status, user, admin_override=is_admin_override
    )
    await db.commit()
    return await ErrorRepository(db).get_by_id(error.error_id)
