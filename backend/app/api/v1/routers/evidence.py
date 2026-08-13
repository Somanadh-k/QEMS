import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.models import Evidence, User
from app.repositories.error_repository import ErrorRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidence import EvidenceUploadResponse
from app.services.storage_service import upload_evidence_file

router = APIRouter(prefix="/errors", tags=["evidence"])
settings = get_settings()

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf", "application/msword",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@router.post("/{error_id}/evidence", response_model=EvidenceUploadResponse, status_code=201)
async def upload_evidence(
    error_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Section 11.4 — multipart upload; validated for type/size (Section 4.6/14.5)."""
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError(f"Unsupported file type: {file.content_type}")

    body = await file.read()
    size_kb = len(body) // 1024
    if size_kb > settings.max_upload_size_mb * 1024:
        raise ValidationError(f"File exceeds {settings.max_upload_size_mb}MB limit")

    object_key = f"evidence/{uuid.uuid4()}_{file.filename}"
    file_url = await upload_evidence_file(object_key, body, file.content_type)
    # MinIO bucket is public-read for this local setup (see storage_service.py docstring) —
    # production should generate short-lived presigned URLs per Section 14.5 instead.

    evidence = Evidence(
        error_id=error_id,
        file_name=file.filename or stored_name,
        file_url=file_url,
        file_type=file.content_type,
        file_size_kb=size_kb,
        uploaded_by=user.user_id,
    )
    await EvidenceRepository(db).add(evidence)
    await db.commit()

    return EvidenceUploadResponse(
        evidence_id=evidence.evidence_id,
        file_name=evidence.file_name,
        file_url=evidence.file_url,
        file_type=evidence.file_type,
        file_size_kb=evidence.file_size_kb,
    )
