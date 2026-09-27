"""Two-way communication (Feature 1): one conversation thread per QA Error.

Authorization mirrors evidence.py/errors.py exactly (visible_departments + "involved"
escape hatch) rather than inventing a separate communication ACL -- a message is just
another view onto the same error, so it inherits the same access boundary.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models import ActorType, Error, Message, MessageAttachment, MessageType, NotificationEvent, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import MessageAttachmentOut, MessageOut
from app.services.notification_service import NotificationService
from app.services.storage_service import (
    ALLOWED_ATTACHMENT_TYPES,
    build_storage_key,
    delete_evidence_file,
    presign_evidence_url,
    upload_evidence_file,
)

MAX_ATTACHMENT_SIZE_MB = 15

# Communication status (spec Feature 1): derived from the conversation + the error's own
# workflow status, not a second, unrelated state machine.
STATUS_RESOLVED = "Resolved"
STATUS_EVIDENCE_REQUESTED = "Evidence Requested"
STATUS_RESPONSE_RECEIVED = "Response Received"
STATUS_AWAITING_QA = "Awaiting QA"
STATUS_AWAITING_STAKEHOLDER = "Awaiting Stakeholder"
STATUS_UNDER_REVIEW = "Under Review"

_TERMINAL_ERROR_STATUSES = {"Resolved", "Rejected", "Closed"}


def compute_communication_status(error: Error, messages: list[Message]) -> str:
    if error.status in _TERMINAL_ERROR_STATUSES:
        return STATUS_RESOLVED
    if not messages:
        return STATUS_UNDER_REVIEW

    last = messages[-1]
    # Per the QEMS workflow, the QA Auditor *raises* the error and assigns it to the
    # stakeholder who must respond (error_service.create_error's docstring / the spec's
    # own "QA Auditor Creates QA Error -> Assigns stakeholder") -- so raised_by is the
    # QA side of the conversation, assigned_to is the stakeholder side.
    is_qa_sender = last.sender_id == error.raised_by
    if last.message_type == MessageType.EVIDENCE_REQUEST:
        return STATUS_EVIDENCE_REQUESTED
    if last.message_type == MessageType.EVIDENCE_UPLOAD:
        return STATUS_RESPONSE_RECEIVED
    return STATUS_AWAITING_STAKEHOLDER if is_qa_sender else STATUS_AWAITING_QA


def _sender_role(sender: User) -> str:
    return sender.role_names[0] if sender.role_names else "User"


def to_message_out(message: Message) -> MessageOut:
    return MessageOut(
        message_id=message.message_id,
        error_id=message.error_id,
        sender_id=message.sender_id,
        sender_name=message.sender.full_name,
        sender_role=_sender_role(message.sender),
        message=message.message,
        message_type=message.message_type,
        parent_message_id=message.parent_message_id,
        is_read=message.is_read,
        created_at=message.created_at,
        updated_at=message.updated_at,
        attachments=[MessageAttachmentOut.model_validate(a) for a in message.attachments],
    )


class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.messages = MessageRepository(db)
        self.audit = AuditLogRepository(db)
        self.notifications = NotificationService(db)

    async def list_messages(self, error: Error, user: User) -> tuple[list[Message], int, str]:
        messages = await self.messages.list_by_error(error.error_id)
        unread = await self.messages.count_unread(error.error_id, exclude_sender_id=user.user_id)
        status = compute_communication_status(error, messages)
        return messages, unread, status

    async def create_message(
        self, error: Error, sender: User, text: str, *, parent_message_id: int | None, message_type: str
    ) -> Message:
        if message_type not in {mt.value for mt in MessageType}:
            raise ValidationError(f"Invalid message_type: {message_type}")

        if parent_message_id is not None:
            parent = await self.messages.get_by_id(parent_message_id)
            if parent is None or parent.error_id != error.error_id:
                raise ValidationError("parent_message_id must reference a message on the same error")

        message = Message(
            error_id=error.error_id,
            sender_id=sender.user_id,
            parent_message_id=parent_message_id,
            message=text,
            message_type=message_type,
        )
        await self.messages.add(message)
        message = await self.messages.get_by_id(message.message_id)

        await self.audit.create(
            actor_id=sender.user_id,
            action="MESSAGE_CREATED",
            actor_type=ActorType.USER,
            error_id=error.error_id,
            after_value={"message_id": message.message_id, "message_type": message_type},
        )

        await self._notify_counterpart(error, message)
        return message

    async def _notify_counterpart(self, error: Error, message: Message) -> None:
        # The "other side" of the two-way thread: whichever of assignee/raiser didn't
        # send this message. Falls back to the raiser when there's no assignee yet.
        counterpart_id = error.raised_by if message.sender_id == error.assigned_to else error.assigned_to
        counterpart_id = counterpart_id or error.raised_by
        if counterpart_id == message.sender_id:
            return  # no one else to notify (e.g. self-authored note on an unassigned error)

        event = (
            NotificationEvent.EVIDENCE_REQUESTED
            if message.message_type == MessageType.EVIDENCE_REQUEST
            else NotificationEvent.MESSAGE_RECEIVED
        )
        await self.notifications.dispatch_event(
            event,
            recipient_id=counterpart_id,
            error=error,
            context={"sender": message.sender.full_name, "message": message.message},
        )

    async def mark_read(self, message: Message, user: User) -> Message:
        if message.sender_id == user.user_id:
            return message  # a sender reading their own message isn't a read receipt
        if not message.is_read:
            message.is_read = True
            await self.db.flush()
            await self.audit.create(
                actor_id=user.user_id,
                action="MESSAGE_READ",
                actor_type=ActorType.USER,
                error_id=message.error_id,
                after_value={"message_id": message.message_id},
            )
        return message

    async def add_attachment(self, message: Message, user: User, *, filename: str, content_type: str, body: bytes) -> MessageAttachment:
        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise ValidationError(f"Unsupported file type: {content_type}")
        if len(body) == 0:
            raise ValidationError("Uploaded file is empty")
        size_kb = len(body) // 1024
        if size_kb > MAX_ATTACHMENT_SIZE_MB * 1024:
            raise ValidationError(f"File exceeds {MAX_ATTACHMENT_SIZE_MB}MB limit")

        storage_key = build_storage_key(filename, prefix="messages")
        display_name = (filename or "").strip() or f"attachment-{storage_key[-12:]}"
        await upload_evidence_file(storage_key, body, content_type)

        try:
            attachment = MessageAttachment(
                message_id=message.message_id,
                file_name=display_name,
                file_type=content_type,
                file_size_kb=size_kb,
                storage_key=storage_key,
                uploaded_by=user.user_id,
            )
            await self.messages.add_attachment(attachment)
            # Keep the already-loaded in-memory relationship in sync -- selectinload
            # treats a relationship it has already populated on this identity-mapped
            # instance as current and won't re-query it, so without this a caller that
            # re-lists messages in the same session/request would see a stale empty list.
            message.attachments.append(attachment)
            if message.message_type == MessageType.TEXT:
                message.message_type = MessageType.EVIDENCE_UPLOAD
            await self.audit.create(
                actor_id=user.user_id,
                action="ATTACHMENT_UPLOADED",
                actor_type=ActorType.USER,
                error_id=message.error_id,
                after_value={"message_id": message.message_id, "file_name": display_name},
            )
        except Exception:
            await self.db.rollback()
            await delete_evidence_file(storage_key)
            raise
        return attachment

    async def presign_attachment(self, attachment: MessageAttachment, user: User) -> str:
        url = await presign_evidence_url(attachment.storage_key, attachment.file_name)
        await self.audit.create(
            actor_id=user.user_id,
            action="ATTACHMENT_DOWNLOADED",
            actor_type=ActorType.USER,
            after_value={"attachment_id": attachment.attachment_id},
        )
        return url
