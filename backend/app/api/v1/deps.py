from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.security import decode_token
from app.models import User
from app.repositories.user_repository import UserRepository


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Access token required")

    user = await UserRepository(db).get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def require_role(*allowed_roles: str):
    async def _guard(user: User = Depends(get_current_user)) -> User:
        if not set(user.role_names) & set(allowed_roles):
            raise PermissionDeniedError(f"Requires one of roles: {', '.join(allowed_roles)}")
        return user

    return _guard


# Roles that may see data outside their own department -- Admin and QA Reviewer already
# have cross-department duties everywhere else in this app (status transitions,
# decisions, audit verification), so they are unrestricted here too. Everyone else is
# scoped to their own department_id. Shared by every endpoint that needs department-level
# visibility (AI neighbour retrieval in signal.py, direct error/evidence reads).
GLOBAL_SCOPE_ROLES = {"Admin", "QA Reviewer"}


def visible_departments(user: User) -> list[int] | None:
    """None means unrestricted (all departments); otherwise the department_ids the user may see."""
    if set(user.role_names) & GLOBAL_SCOPE_ROLES:
        return None
    return [user.department_id] if user.department_id else []
