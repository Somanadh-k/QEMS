from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import User
from app.repositories.error_repository import ErrorRepository
from app.schemas.rebuttal import RebuttalCreateRequest, RebuttalCreateResponse
from app.services.error_service import ErrorService

router = APIRouter(prefix="/errors", tags=["rebuttals"])


@router.post("/{error_id}/rebuttals", response_model=RebuttalCreateResponse, status_code=201)
async def submit_rebuttal(
    error_id: int,
    payload: RebuttalCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("Department Owner", "Admin")),
):
    """Section 11.5 / 4.8 — Department Owner assigned to the error submits a rebuttal."""
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    rebuttal = await ErrorService(db).submit_rebuttal(error, payload.justification, user)
    await db.commit()
    return RebuttalCreateResponse(
        rebuttal_id=rebuttal.rebuttal_id, status=rebuttal.status, created_at=rebuttal.created_at
    )
