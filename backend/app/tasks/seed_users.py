"""Dev-only: create one user per role for manual/smoke testing.

Run with: python -m app.tasks.seed_users
"""

import asyncio

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.models import Department, Role, User, UserRole

TEST_USERS = [
    ("Ada Admin", "admin@qemscorp.dev", "Admin"),
    ("Quinn QA", "qa@qemscorp.dev", "QA Reviewer"),
    ("Owen Owner", "owner@qemscorp.dev", "Department Owner"),
    ("Vic Viewer", "viewer@qemscorp.dev", "Viewer"),
]
TEST_PASSWORD = "Password123!"


async def seed_users() -> None:
    async with AsyncSessionLocal() as session:
        department = (await session.execute(select(Department).limit(1))).scalar_one()
        roles = {r.role_name: r for r in (await session.execute(select(Role))).scalars().all()}

        for full_name, email, role_name in TEST_USERS:
            existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if existing:
                continue
            user = User(
                full_name=full_name,
                email=email,
                password_hash=hash_password(TEST_PASSWORD),
                department_id=department.department_id,
            )
            session.add(user)
            await session.flush()
            session.add(UserRole(user_id=user.user_id, role_id=roles[role_name].role_id))

        await session.commit()
    print(f"Seed complete: {len(TEST_USERS)} test users (password: {TEST_PASSWORD})")


if __name__ == "__main__":
    asyncio.run(seed_users())
