from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, visible_departments
from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models import ActorType, Error, Evidence, EvidenceAccessLog, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.error_repository import ErrorRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidence import EvidenceUploadResponse
from app.services.storage_service import (
    ALLOWED_ATTACHMENT_TYPES as ALLOWED_TYPES,
    PRESIGNED_URL_TTL_SECONDS,
    build_storage_key,
    delete_evidence_file,
    presign_evidence_url,
    sha256_of,
    upload_evidence_file,
)

router = APIRouter(prefix="/errors", tags=["evidence"])
settings = get_settings()


@router.post("/{error_id}/evidence", response_model=EvidenceUploadResponse, status_code=201)
async def upload_evidence(
    error_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError(f"Unsupported file type: {file.content_type}")

    body = await file.read()
    if len(body) == 0:
        raise ValidationError("Uploaded file is empty")
    size_kb = len(body) // 1024
    if size_kb > settings.max_upload_size_mb * 1024:
        raise ValidationError(f"File exceeds {settings.max_upload_size_mb}MB limit")

    # Finding F-04: the previous implementation read `file.filename or stored_name`,
    # where `stored_name` was never bound — any upload without a filename raised
    # NameError and returned a 500 *after* the object was already in the bucket.
    # The storage key is now generated independently of the client-supplied name, and a
    # missing name falls back to a stable placeholder.
    storage_key = build_storage_key(file.filename)
    display_name = (file.filename or "").strip() or f"evidence-{storage_key[-12:]}"

    await upload_evidence_file(storage_key, body, file.content_type)

    evidence = Evidence(
        error_id=error_id,
        file_name=display_name,
        # Retained for backwards compatibility with existing rows and the current UI, but
        # no longer a readable location — reads go through GET /evidence/{id}/url.
        file_url=storage_key,
        storage_key=storage_key,
        sha256=sha256_of(body),
        file_type=file.content_type,
        file_size_kb=size_kb,
        uploaded_by=user.user_id,
    )
    try:
        await EvidenceRepository(db).add(evidence)
        await AuditLogRepository(db).create(
            action="EVIDENCE_UPLOADED", actor_id=user.user_id, actor_type=ActorType.USER,
            error_id=error_id,
            after_value={"file_name": display_name, "sha256": evidence.sha256},
        )
        await db.commit()
    except Exception:
        # Never leave an object in the bucket that no row points at.
        await db.rollback()
        await delete_evidence_file(storage_key)
        raise

    return EvidenceUploadResponse(
        evidence_id=evidence.evidence_id,
        file_name=evidence.file_name,
        file_url=evidence.file_url,
        file_type=evidence.file_type,
        file_size_kb=evidence.file_size_kb,
        uploaded_by=evidence.uploaded_by,
        sha256=evidence.sha256,
    )


@router.get("/evidence/{evidence_id}/url")
async def get_evidence_url(
    evidence_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mint a short-lived link after an authorisation check, and log the read.

    Finding F-03: evidence was previously served from a permanent public URL stored on
    the row, readable by anyone who ever saw the link, with no authorisation check and no
    revocation. Links now expire in five minutes and every issue is recorded, so evidence
    access is auditable rather than merely possible.

    Finding D-07-EVIDENCE: authentication alone was being treated as authorisation --
    any authenticated user could mint a link to evidence on any error, regardless of
    department. Scoped the same way as GET /errors/{id} (D-07) and AI neighbour
    retrieval (signal.py): Admin/QA Reviewer unrestricted, everyone else limited to
    their own department, plus whoever raised or is assigned the parent error (same
    department-mismatch escape hatch as D-07's fix in errors.py -- see that docstring).
    This check runs before the presigned URL is ever generated.
    """
    row = (
        await db.execute(
            select(Evidence, Error.department_id, Error.raised_by, Error.assigned_to)
            .join(Error, Error.error_id == Evidence.error_id)
            .where(Evidence.evidence_id == evidence_id)
        )
    ).first()
    if row is None:
        raise NotFoundError(f"Evidence {evidence_id} not found")
    evidence, department_id, raised_by, assigned_to = row

    visible = visible_departments(user)
    is_involved = user.user_id in (raised_by, assigned_to)
    if visible is not None and department_id not in visible and not is_involved:
        raise PermissionDeniedError(f"You do not have access to evidence {evidence_id}")

    key = evidence.storage_key or evidence.file_url
    url = await presign_evidence_url(key, evidence.file_name)

    db.add(
        EvidenceAccessLog(
            evidence_id=evidence_id, accessed_by=user.user_id, action="PRESIGNED_URL_ISSUED"
        )
    )
    await db.commit()

    return {
        "url": url,
        "expires_in_seconds": PRESIGNED_URL_TTL_SECONDS,
        "file_name": evidence.file_name,
        "sha256": evidence.sha256,
    }
