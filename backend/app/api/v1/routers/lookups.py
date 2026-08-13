from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models import Category, Department, User, UserRole
from app.schemas.lookups import CategoryOut, DepartmentOut, UserOut

router = APIRouter(tags=["lookups"])

"""Small reference-data endpoints the report doesn't list explicitly (Section 11), but that
the frontend needs to populate dropdowns (department/category on error creation) and to resolve
user_id -> name for display (rebuttal/decision authors, assignees) — the core resource endpoints
only ever return IDs, matching the report's DDL, which stores foreign keys, not denormalized names."""


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    result = await db.execute(select(Department).order_by(Department.name))
    return result.scalars().all()


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    result = await db.execute(
        select(User).options(selectinload(User.user_roles).selectinload(UserRole.role)).where(User.is_active)
    )
    return [
        UserOut(user_id=u.user_id, full_name=u.full_name, department_id=u.department_id, roles=u.role_names)
        for u in result.scalars().all()
    ]
