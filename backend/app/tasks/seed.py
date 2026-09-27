"""One-off dev seed: baseline roles, a department, categories and SLA policies.

Run with: python -m app.tasks.seed
"""

import asyncio

from app.core.db import AsyncSessionLocal
from app.models import Category, Department, Role, SLAPolicy

DEFAULT_ROLES = ["Admin", "QA Reviewer", "Department Owner", "Viewer"]
DEFAULT_SLA_POLICIES = [("Critical", 4), ("High", 24), ("Medium", 72), ("Low", 168)]
DEFAULT_DEPARTMENTS = ["Engineering", "Quality Assurance", "DevOps", "Product", "Customer Support"]
DEFAULT_CATEGORIES = ["Functional Bug", "UI/UX Issue", "Performance Issue", "Security Vulnerability", "Documentation Gap"]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for name in DEFAULT_ROLES:
            session.add(Role(role_name=name))
        for severity, hours in DEFAULT_SLA_POLICIES:
            session.add(SLAPolicy(severity=severity, sla_hours=hours))
        for name in DEFAULT_DEPARTMENTS:
            session.add(Department(name=name))
        await session.flush()

        policies = (await session.execute(SLAPolicy.__table__.select())).fetchall()
        default_policy_id = policies[2].sla_policy_id  # Medium
        for name in DEFAULT_CATEGORIES:
            session.add(Category(name=name, sla_policy_id=default_policy_id))

        await session.commit()
    print("Seed complete: roles, SLA policies, departments, categories inserted.")


if __name__ == "__main__":
    asyncio.run(seed())
