from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import User
from app.repositories.error_repository import ErrorRepository
from app.schemas.decision import DecisionCreateRequest, DecisionCreateResponse
from app.services.error_service import ErrorService

router = APIRouter(prefix="/errors", tags=["decisions"])


# 201: this creates a qa_decisions row, matching POST /errors and POST /rebuttals.
# Previously 200, which made the API inconsistent for generated clients (finding O-03).
@router.post("/{error_id}/decision", response_model=DecisionCreateResponse, status_code=201)
async def record_decision(
    error_id: int,
    payload: DecisionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Section 11.6 / 4.9 — records the final decision and closes the workflow."""
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    decision = await ErrorService(db).record_decision(error, payload.decision, payload.notes, user)
    await db.commit()
    await db.refresh(error)
    return DecisionCreateResponse(
        decision_id=decision.decision_id, status=error.status, decided_at=decision.decided_at
    )
