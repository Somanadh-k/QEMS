from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.models import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserRepository(db)

    async def login(self, email: str, password: str) -> tuple[str, str, User]:
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")

        access_token = create_access_token(user.user_id, user.role_names)
        refresh_token = create_refresh_token(user.user_id)
        return access_token, refresh_token, user

    async def refresh(self, refresh_token: str) -> str:
        try:
            payload = decode_token(refresh_token)
        except ValueError as exc:
            raise UnauthorizedError(str(exc)) from exc
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Refresh token required")

        user = await self.users.get_by_id(int(payload["sub"]))
        if user is None or not user.is_active:
            raise UnauthorizedError("User not found or inactive")
        return create_access_token(user.user_id, user.role_names)
