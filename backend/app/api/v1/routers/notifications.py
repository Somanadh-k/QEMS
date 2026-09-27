from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role, visible_departments
from app.core.db import get_db
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models import NotificationEvent, User
from app.repositories.error_repository import ErrorRepository
from app.repositories.notification_repository import NotificationRepository, NotificationTemplateRepository
from app.schemas.notification import (
    NotificationOut,
    NotificationTemplateOut,
    NotificationTemplateUpdateRequest,
    NotificationTestRequest,
)
from app.services.notification_service import NotificationService

router = APIRouter(tags=["notifications"])


@router.get("/errors/{error_id}/notifications", response_model=list[NotificationOut])
async def list_error_notifications(
    error_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    error = await ErrorRepository(db).get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")

    visible = visible_departments(user)
    is_involved = user.user_id in (error.raised_by, error.assigned_to)
    if visible is not None and error.department_id not in visible and not is_involved:
        raise PermissionDeniedError(f"You do not have access to error {error_id}")

    return await NotificationRepository(db).list_by_error(error_id)


@router.get("/notifications/unread-count")
async def unread_notification_count(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Feeds the Navbar bell badge -- notifications addressed to the current user only."""
    count = await NotificationRepository(db).count_unread_for_recipient(user.user_id)
    return {"count": count}


@router.post("/notifications/test", response_model=NotificationOut, status_code=201)
async def send_test_notification(
    payload: NotificationTestRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("Admin")),
):
    if payload.event_type not in {e.value for e in NotificationEvent}:
        raise ValidationError(f"Unknown event_type: {payload.event_type}")

    error = None
    if payload.error_id is not None:
        error = await ErrorRepository(db).get_by_id(payload.error_id)
        if error is None:
            raise NotFoundError(f"Error {payload.error_id} not found")

    notification = await NotificationService(db).dispatch_event(
        payload.event_type,
        recipient_id=payload.recipient_id,
        error=error,
        context={
            "severity": "High", "category": "Test Category", "sender": "QEMS",
            "due_date": "n/a", "message": "This is a test notification.", "decision": "Resolved",
        },
    )
    await db.commit()
    return notification


@router.get("/notification-templates", response_model=list[NotificationTemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), _user: User = Depends(require_role("Admin"))):
    return await NotificationTemplateRepository(db).list_all()


@router.patch("/notification-templates/{template_id}", response_model=NotificationTemplateOut)
async def update_template(
    template_id: int,
    payload: NotificationTemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("Admin")),
):
    repo = NotificationTemplateRepository(db)
    template = await repo.get_by_id(template_id)
    if template is None:
        raise NotFoundError(f"Notification template {template_id} not found")

    if payload.subject_template is not None:
        template.subject_template = payload.subject_template
    if payload.body_template is not None:
        template.body_template = payload.body_template
    if payload.enabled is not None:
        template.enabled = payload.enabled

    await db.commit()
    await db.refresh(template)
    return template
