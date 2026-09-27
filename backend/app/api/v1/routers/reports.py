import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Numeric, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_role
from app.core.db import get_db
from app.core.exceptions import ValidationError
from app.models import Category, Department, Error, User
from app.schemas.report import ReportSummaryResponse, SeverityBreakdown

router = APIRouter(prefix="/reports", tags=["reports"])


def _filters(date_from, date_to, department_id, category_id, severity):
    conditions = []
    if date_from:
        conditions.append(Error.date_discovered >= date_from)
    if date_to:
        conditions.append(Error.date_discovered <= date_to)
    if department_id:
        conditions.append(Error.department_id == department_id)
    if category_id:
        conditions.append(Error.category_id == category_id)
    if severity:
        conditions.append(Error.severity == severity)
    return conditions


@router.get("/summary")
async def report_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: int | None = None,
    category_id: int | None = None,
    severity: str | None = None,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("QA Reviewer", "Admin", "Viewer", "Department Owner")),
):
    """Aggregated in SQL.

    Finding F-07: this previously pulled page_size=1000 and filtered with Python list
    comprehensions, so the 1001st error silently vanished from every leadership number.
    Counting is now done by the database, which is both correct at any size and faster.
    """
    conditions = _filters(date_from, date_to, department_id, category_id, severity)
    now = datetime.now(timezone.utc)

    totals = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(Error.status != "Closed").label("open_count"),
                func.count().filter(Error.status == "Closed").label("closed_count"),
                func.count()
                .filter(Error.sla_due_at < now, Error.status != "Closed")
                .label("overdue_count"),
                func.count().filter(Error.sla_state == "BREACHED").label("breached_count"),
                func.count().filter(Error.sla_state == "AT_RISK").label("at_risk_count"),
                func.avg(cast(Error.risk_score, Numeric)).label("avg_risk"),
            ).where(*conditions)
        )
    ).one()

    by_severity = (
        await db.execute(
            select(Error.severity, func.count().label("count"))
            .where(*conditions)
            .group_by(Error.severity)
            .order_by(func.count().desc())
        )
    ).all()

    if format == "json":
        return ReportSummaryResponse(
            total_errors=totals.total,
            open_count=totals.open_count,
            closed_count=totals.closed_count,
            overdue_count=totals.overdue_count,
            by_severity=[SeverityBreakdown(severity=s, count=c) for s, c in by_severity],
        )

    rows = (
        await db.execute(
            select(
                Error.qa_error_code, Error.title, Error.severity, Error.status,
                Error.sla_state, Error.risk_score, Department.name, Category.name,
                Error.created_at,
            )
            .join(Department, Department.department_id == Error.department_id)
            .join(Category, Category.category_id == Error.category_id)
            .where(*conditions)
            .order_by(Error.created_at.desc())
        )
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["qa_error_code", "title", "severity", "status", "sla_state", "risk_score",
         "department", "category", "created_at"]
    )
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=qems_report.csv"},
    )


@router.get("/analytics/trends")
async def trends(
    days: int = Query(default=180, ge=30, le=730),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("QA Reviewer", "Admin", "Viewer", "Department Owner")),
):
    """Monthly volume by severity, plus the per-process concentration leadership asks for."""
    monthly = (
        await db.execute(
            select(
                func.date_trunc("month", Error.created_at).label("month"),
                func.count().label("total"),
                func.count().filter(Error.status == "Closed").label("closed"),
                func.count().filter(Error.severity.in_(["High", "Critical"])).label("high_sev"),
            )
            .where(Error.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
            .group_by("month")
            .order_by("month")
        )
    ).all()

    return {
        "monthly": [
            {"month": m.isoformat() if m else None, "total": t, "closed": c, "high_severity": h}
            for m, t, c, h in monthly
        ]
    }
