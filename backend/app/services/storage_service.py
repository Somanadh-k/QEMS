"""Evidence object storage (Section 6.2, 14.5).

Talks to a local MinIO instance in dev — an S3-compatible server, so swapping this for real
AWS S3, Supabase Storage, or Azure Blob's S3-compatible endpoint in production is a config
change (S3_ENDPOINT_URL/credentials), not a code change.

boto3 is synchronous; every call here runs off the event loop via asyncio.to_thread so an
evidence upload never blocks other requests.
"""

import asyncio
import functools

import boto3

from app.core.config import get_settings

settings = get_settings()


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def _put_object_sync(key: str, body: bytes, content_type: str) -> str:
    client = _client()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=content_type)
    return f"{settings.s3_public_url}/{settings.s3_bucket}/{key}"


async def upload_evidence_file(key: str, body: bytes, content_type: str) -> str:
    """Uploads bytes to the evidence bucket and returns the file's public URL."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(_put_object_sync, key, body, content_type))
