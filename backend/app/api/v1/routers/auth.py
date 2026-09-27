from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.exceptions import UnauthorizedError, ValidationError
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    UserSummary,
    UserUpdateRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Section 11.2 — no auth required; issues access + refresh tokens."""
    access_token, refresh_token, user = await AuthService(db).login(payload.email, payload.password)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_to_summary(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Section 11.2 — refresh token required; issues a new access token."""
    access_token = await AuthService(db).refresh(payload.refresh_token)
    return RefreshResponse(access_token=access_token)


def _user_to_summary(user: User) -> UserSummary:
    return UserSummary(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        department_id=user.department_id,
        roles=user.role_names,
        phone=user.phone,
        address=user.address,
        employee_id=user.employee_id,
    )


@router.get("/me", response_model=UserSummary)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return _user_to_summary(current_user)


@router.patch("/me", response_model=UserSummary)
async def update_me(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's profile (name, email, phone, address, password)."""
    # If a password change is requested, verify the current password first.
    if payload.new_password is not None:
        if not payload.current_password:
            raise ValidationError("current_password is required to set a new password")
        if not verify_password(payload.current_password, current_user.password_hash):
            raise UnauthorizedError("Current password is incorrect")

    # Check for email uniqueness if the email is being changed.
    repo = UserRepository(db)
    if payload.email is not None and payload.email != current_user.email:
        existing = await repo.get_by_email(payload.email)
        if existing is not None:
            raise ValidationError("A user with that email already exists")

    # Apply all provided fields.
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.email is not None:
        current_user.email = payload.email
    if payload.phone is not None:
        current_user.phone = payload.phone
    if payload.address is not None:
        current_user.address = payload.address
    if payload.new_password is not None:
        current_user.password_hash = hash_password(payload.new_password)

    await db.commit()
    await db.refresh(current_user)
    return _user_to_summary(current_user)
