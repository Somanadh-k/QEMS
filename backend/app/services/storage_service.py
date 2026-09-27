"""Evidence object storage.

Talks to a local MinIO instance in dev — an S3-compatible server, so swapping this for
real AWS S3, Supabase Storage, or Azure Blob's S3-compatible endpoint in production is a
config change (S3_ENDPOINT_URL/credentials), not a code change.

SECURITY (finding F-03): this module previously returned a permanent public URL of the
form {s3_public_url}/{bucket}/{key} and stored it on the evidence row. Anyone who ever
saw that link could read the evidence forever, with no authorisation check and no way to
revoke it — including after the error closed or the uploader left the company. Objects
are now addressed by an opaque storage key and read through short-lived presigned URLs
minted per request, after an authorisation check, and logged.

boto3 is synchronous; every call here runs off the event loop so an evidence upload
never blocks other requests.
"""

import asyncio
import functools
import hashlib
import uuid
from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.exceptions import QEMSError

settings = get_settings()

# Long enough to open a document, short enough that a leaked link is worthless.
PRESIGNED_URL_TTL_SECONDS = 300


class StorageError(QEMSError):
    status_code = 502
    code = "storage_error"


# Shared between evidence uploads (evidence.py) and message attachments (message_service.py)
# so the two upload paths can't silently drift apart on what's allowed.
ALLOWED_ATTACHMENT_TYPES = {
    "image/jpeg", "image/png", "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        # Pin SigV4. Without this botocore negotiated SigV2 against the MinIO endpoint,
        # which produces ?AWSAccessKeyId=...&Signature=... links — a deprecated scheme
        # with weaker guarantees and no scoped expiry semantics.
        config=Config(signature_version="s3v4"),
    )


def build_storage_key(original_filename: str | None, prefix: str = "evidence") -> str:
    """An opaque, collision-free key that never trusts the client-supplied name.

    A filename from a multipart upload is attacker-controlled: it can contain path
    separators, traversal sequences, or nothing at all. Only the extension is carried
    over, and only after validation. `prefix` just partitions the bucket by feature
    (evidence/ vs messages/); it plays no role in access control, which is always by
    presigned URL (see presign_evidence_url).
    """
    suffix = ""
    if original_filename:
        candidate = PurePosixPath(original_filename).suffix
        if len(candidate) <= 10 and candidate.replace(".", "").isalnum():
            suffix = candidate.lower()
    return f"{prefix}/{uuid.uuid4().hex}{suffix}"


def _put_object_sync(key: str, body: bytes, content_type: str) -> None:
    _client().put_object(
        Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=content_type
    )


def _delete_object_sync(key: str) -> None:
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)


def _presign_sync(key: str, download_name: str, ttl: int) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            # Force the browser to save under the original name without ever letting
            # that name influence the storage key.
            "ResponseContentDisposition": f'attachment; filename="{download_name}"',
        },
        ExpiresIn=ttl,
    )


async def upload_evidence_file(key: str, body: bytes, content_type: str) -> None:
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None, functools.partial(_put_object_sync, key, body, content_type)
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Evidence storage is unavailable: {exc}") from exc


async def delete_evidence_file(key: str) -> None:
    """Used to clean up an orphaned object when the database write fails after upload."""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, functools.partial(_delete_object_sync, key))
    except (ClientError, BotoCoreError):
        # Best-effort cleanup; a leaked object is preferable to masking the real error.
        pass


async def presign_evidence_url(
    key: str, download_name: str, ttl: int = PRESIGNED_URL_TTL_SECONDS
) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, functools.partial(_presign_sync, key, download_name, ttl)
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Could not generate evidence link: {exc}") from exc


def sha256_of(body: bytes) -> str:
    """Content hash stored at upload, so a swapped file is provable rather than deniable."""
    return hashlib.sha256(body).hexdigest()
