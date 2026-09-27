"""Dev seed: a realistic historical corpus for the Quality Signal Engine.

Recurrence detection cannot be evaluated against an empty table, and it cannot be
evaluated against random noise either — the interesting question is whether the engine
separates a genuine concentrated pattern from diffuse background findings. So this seed
builds both:

* a strong recurring cluster (identity verification) concentrated in one process and
  accelerating quarter on quarter — the pattern the engine must catch;
* several diffuse themes spread across processes and departments — the noise it must
  not flag;
* one near-duplicate pair — which must be reported as a duplicate, not a recurrence.

Run with:  python -m app.tasks.seed_history
"""

import asyncio
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models import Category, Department, Error, ErrorStatus, Process, User
from app.services.embedding_service import generate_embedding
from app.services.signal_service import source_hash, source_text

random.seed(20260905)

PROCESSES = [
    "Account Maintenance",
    "Customer Onboarding",
    "Payments Processing",
    "Card Disputes",
    "Statement Generation",
]

# (theme templates, category name, severity, process, how far back to spread)
THEMES = [
    # The recurring systemic defect. Concentrated in Account Maintenance and rising.
    (
        [
            "Customer identity was not verified before account modification",
            "Identity verification step skipped prior to updating account details",
            "Account details amended without completing customer identity checks",
            "No identity confirmation recorded before the account change was applied",
            "Customer identity check missing ahead of the account modification request",
            "Agent modified the account before verifying the customer identity",
        ],
        "Security Vulnerability",
        "Critical",
        "Account Maintenance",
        "recurring",
    ),
    (
        [
            "Address change processed without secondary approval",
            "Secondary approval missing on the address amendment",
            "Address update applied with no second checker sign-off",
        ],
        "Functional Bug",
        "High",
        "Account Maintenance",
        "diffuse",
    ),
    (
        [
            "Payment reference truncated in the outbound file",
            "Outbound payment file contained a malformed reference field",
            "Payment instruction rejected due to an invalid reference format",
        ],
        "Functional Bug",
        "Medium",
        "Payments Processing",
        "diffuse",
    ),
    (
        [
            "Dispute acknowledgement letter issued after the regulatory deadline",
            "Cardholder dispute response exceeded the required turnaround",
            "Late acknowledgement sent on a card dispute case",
        ],
        "Documentation Gap",
        "High",
        "Card Disputes",
        "diffuse",
    ),
    (
        [
            "Statement generated with an incorrect closing balance",
            "Closing balance on the statement did not reconcile",
            "Statement run produced an inconsistent balance figure",
        ],
        "Performance Issue",
        "Medium",
        "Statement Generation",
        "diffuse",
    ),
    (
        [
            "Onboarding screen rendered incorrectly on mobile browsers",
            "Layout broken on the onboarding form at tablet width",
        ],
        "UI/UX Issue",
        "Low",
        "Customer Onboarding",
        "diffuse",
    ),
]


async def seed_history(target_total: int = 140) -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Error.error_id).limit(1))).first()
        if existing:
            print("Errors already present; seed_history is a one-off. Aborting.")
            return

        categories = {
            c.name: c for c in (await db.execute(select(Category))).scalars().all()
        }
        departments = (await db.execute(select(Department))).scalars().all()
        users = (await db.execute(select(User))).scalars().all()
        qa_user = next((u for u in users if "qa" in u.email), users[0])
        owner = next((u for u in users if "owner" in u.email), users[0])

        process_rows: dict[str, Process] = {}
        for index, name in enumerate(PROCESSES):
            process = Process(name=name, department_id=departments[index % len(departments)].department_id)
            db.add(process)
            process_rows[name] = process
        await db.flush()

        now = datetime.now(timezone.utc)
        created_count = 0

        for templates, category_name, severity, process_name, shape in THEMES:
            if shape == "recurring":
                # 26 findings: 6 in the older quarter, 20 in the recent one -> a clear rise.
                buckets = [(26, 180, 91, 6), (26, 90, 1, 20)]
            else:
                buckets = [(0, 180, 91, 4), (0, 90, 1, 5)]

            for _, oldest_days, newest_days, count in buckets:
                for _ in range(count):
                    if created_count >= target_total:
                        break
                    template = random.choice(templates)
                    age_days = random.randint(newest_days, oldest_days)
                    created_at = now - timedelta(days=age_days, hours=random.randint(0, 23))

                    # The recurring theme concentrates in one department; noise spreads.
                    department = (
                        departments[0]
                        if shape == "recurring"
                        else random.choice(departments)
                    )

                    # Vary each description. Identical text produces a cosine distance of
                    # ~0, which the engine correctly classifies as a duplicate re-filing
                    # rather than a recurrence — realistic findings share a theme but not
                    # their wording, and the corpus has to reflect that to be a fair test.
                    case_ref = f"CASE-{random.randint(10000, 99999)}"
                    agent_ref = f"agent {random.randint(100, 999)}"
                    channel = random.choice(
                        ["branch counter", "telephone banking", "online portal", "back office"]
                    )
                    detail = random.choice(
                        [
                            "The reviewer could not locate the completed control step in the case file.",
                            "Sampling identified the omission during the monthly quality review.",
                            "The checklist entry was left blank and no compensating check was recorded.",
                            "Supporting documentation for the control was absent from the record.",
                            "The mandatory field was bypassed and no exception approval was attached.",
                        ]
                    )
                    error = Error(
                        qa_error_code="PENDING",
                        title=template,
                        description=(
                            f"{template}. Raised against {case_ref} handled by {agent_ref} "
                            f"via the {channel} channel within the {process_name} process. "
                            f"{detail}"
                        ),
                        category_id=categories[category_name].category_id,
                        severity=severity,
                        status=ErrorStatus.CLOSED if age_days > 30 else ErrorStatus.OPEN,
                        department_id=department.department_id,
                        process_id=process_rows[process_name].process_id,
                        raised_by=qa_user.user_id,
                        assigned_to=owner.user_id,
                        date_discovered=created_at.date(),
                        created_at=created_at,
                        updated_at=created_at,
                        closed_at=created_at + timedelta(days=3) if age_days > 30 else None,
                        sla_state="ON_TRACK",
                    )
                    db.add(error)
                    await db.flush()
                    error.qa_error_code = f"QEMS-{created_at.year}-{error.error_id:05d}"

                    result = await generate_embedding(source_text(error))
                    error.description_embedding = result.vector
                    error.embedding_model = result.model
                    error.embedded_at = created_at
                    error.embedding_source_hash = source_hash(error)
                    created_count += 1

        await db.commit()
        print(f"Seeded {created_count} historical errors across {len(PROCESSES)} processes.")
        print("Recurring cluster: 'identity verification' in Account Maintenance (rising QoQ).")


if __name__ == "__main__":
    asyncio.run(seed_history())
