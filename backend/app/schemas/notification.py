from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: int
    error_id: int | None
    recipient_id: int
    event_type: str | None
    channel: str
    subject: str
    status: str
    retry_count: int
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class NotificationTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    subject_template: str
    body_template: str
    enabled: bool
    updated_at: datetime


class NotificationTemplateUpdateRequest(BaseModel):
    subject_template: str | None = Field(default=None, min_length=1, max_length=300)
    body_template: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None


class NotificationTestRequest(BaseModel):
    event_type: str
    recipient_id: int
    error_id: int | None = None
