from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Message, MessageAttachment, Role, User, UserRole


class MessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _base_query(self):
        return select(Message).options(
            selectinload(Message.attachments),
            selectinload(Message.sender).selectinload(User.user_roles).selectinload(UserRole.role),
        )

    async def list_by_error(self, error_id: int) -> list[Message]:
        result = await self.db.execute(
            self._base_query().where(Message.error_id == error_id).order_by(Message.created_at.asc())
        )
        return list(result.scalars().unique().all())

    async def get_by_id(self, message_id: int) -> Message | None:
        result = await self.db.execute(self._base_query().where(Message.message_id == message_id))
        return result.scalar_one_or_none()

    async def count_unread(self, error_id: int, exclude_sender_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Message).where(
                Message.error_id == error_id,
                Message.is_read.is_(False),
                Message.sender_id != exclude_sender_id,
            )
        )
        return result.scalar_one()

    async def add(self, message: Message) -> Message:
        self.db.add(message)
        await self.db.flush()
        return message

    async def add_attachment(self, attachment: MessageAttachment) -> MessageAttachment:
        self.db.add(attachment)
        await self.db.flush()
        return attachment

    async def get_attachment(self, attachment_id: int) -> MessageAttachment | None:
        result = await self.db.execute(
            select(MessageAttachment).where(MessageAttachment.attachment_id == attachment_id)
        )
        return result.scalar_one_or_none()
