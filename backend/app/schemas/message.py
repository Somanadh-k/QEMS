from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageCreateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    parent_message_id: int | None = None
    # EVIDENCE_REQUEST is the only variant a client may set directly; EVIDENCE_UPLOAD is
    # derived server-side (message_service) from an attachment actually being present.
    message_type: str = "TEXT"


class MessageAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attachment_id: int
    file_name: str
    file_type: str
    file_size_kb: int
    uploaded_by: int
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    error_id: int
    sender_id: int
    sender_name: str
    sender_role: str
    message: str
    message_type: str
    parent_message_id: int | None
    is_read: bool
    created_at: datetime
    updated_at: datetime
    attachments: list[MessageAttachmentOut] = []


class MessageListResponse(BaseModel):
    items: list[MessageOut]
    total: int
    unread_count: int
    communication_status: str


class MessageReadResponse(BaseModel):
    message_id: int
    is_read: bool
