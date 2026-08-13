from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse, UserSummary
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Section 11.2 — no auth required; issues access + refresh tokens."""
    access_token, refresh_token, user = await AuthService(db).login(payload.email, payload.password)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserSummary(
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            department_id=user.department_id,
            roles=user.role_names,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Section 11.2 — refresh token required; issues a new access token."""
    access_token = await AuthService(db).refresh(payload.refresh_token)
    return RefreshResponse(access_token=access_token)
