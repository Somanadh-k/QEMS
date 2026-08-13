import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import User
from app.repositories.error_repository import ErrorRepository
from app.schemas.error import (
    ErrorCreateRequest,
    ErrorCreateResponse,
    ErrorDetailResponse,
    ErrorListResponse,
    ErrorStatusUpdateRequest,
)
from app.services.ai_service import AIService, get_ai_service
from app.services.error_service import ErrorService

router = APIRouter(prefix="/errors", tags=["errors"])
logger = logging.getLogger("qems.errors")


@router.post("", response_model=ErrorCreateResponse, status_code=201)
async def create_error(
    payload: ErrorCreateRequest,
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
    user: User = Depends(get_current_user),
):
    """Section 11.3 — creates a new QA error and generates its QEMS-YYYY-NNNNN code."""
    embedding: list[float] | None = None
    try:
        embedding = await ai.generate_embedding(f"{payload.title}\n{payload.description}")
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
        embedding=embedding,
        actor=user,
    )
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
async def get_error(error_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """Section 11.3 — full detail including evidence, rebuttal, and decision sub-objects."""
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")
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
