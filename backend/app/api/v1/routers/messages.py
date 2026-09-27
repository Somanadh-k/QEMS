from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, visible_departments
from app.core.db import get_db
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models import User
from app.repositories.error_repository import ErrorRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import (
    MessageAttachmentOut,
    MessageCreateRequest,
    MessageListResponse,
    MessageOut,
    MessageReadResponse,
)
from app.services.message_service import MessageService, to_message_out

router = APIRouter(tags=["communication"])


async def _load_authorized_error(error_id: int, db: AsyncSession, user: User):
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    # Identical scoping to GET /errors/{id} (deps.visible_departments) -- a conversation
    # is a view onto its error, so it can never be more visible than the error itself.
    visible = visible_departments(user)
    is_involved = user.user_id in (error.raised_by, error.assigned_to)
    if visible is not None and error.department_id not in visible and not is_involved:
        raise PermissionDeniedError(f"You do not have access to error {error_id}")
    return error


@router.get("/errors/{error_id}/messages", response_model=MessageListResponse)
async def list_messages(
    error_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    error = await _load_authorized_error(error_id, db, user)
    messages, unread_count, status = await MessageService(db).list_messages(error, user)
    return MessageListResponse(
        items=[to_message_out(m) for m in messages],
        total=len(messages),
        unread_count=unread_count,
        communication_status=status,
    )


@router.post("/errors/{error_id}/messages", response_model=MessageOut, status_code=201)
async def create_message(
    error_id: int,
    payload: MessageCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    error = await _load_authorized_error(error_id, db, user)
    message = await MessageService(db).create_message(
        error,
        user,
        payload.message,
        parent_message_id=payload.parent_message_id,
        message_type=payload.message_type,
    )
    await db.commit()
    return to_message_out(message)


async def _load_authorized_message(message_id: int, db: AsyncSession, user: User):
    message = await MessageRepository(db).get_by_id(message_id)
    if message is None:
        raise NotFoundError(f"Message {message_id} not found")
    await _load_authorized_error(message.error_id, db, user)
    return message


@router.patch("/messages/{message_id}/read", response_model=MessageReadResponse)
async def mark_message_read(
    message_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    message = await _load_authorized_message(message_id, db, user)
    message = await MessageService(db).mark_read(message, user)
    await db.commit()
    return MessageReadResponse(message_id=message.message_id, is_read=message.is_read)


@router.post("/messages/{message_id}/attachments", response_model=MessageAttachmentOut, status_code=201)
async def upload_attachment(
    message_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    message = await _load_authorized_message(message_id, db, user)
    body = await file.read()
    attachment = await MessageService(db).add_attachment(
        message, user, filename=file.filename, content_type=file.content_type, body=body
    )
    await db.commit()
    return MessageAttachmentOut.model_validate(attachment)


@router.get("/messages/attachments/{attachment_id}/url")
async def get_attachment_url(
    attachment_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    attachment = await MessageRepository(db).get_attachment(attachment_id)
    if attachment is None:
        raise NotFoundError(f"Attachment {attachment_id} not found")
    message = await _load_authorized_message(attachment.message_id, db, user)
    assert message.message_id == attachment.message_id

    url = await MessageService(db).presign_attachment(attachment, user)
    await db.commit()
    return {"url": url, "file_name": attachment.file_name}
