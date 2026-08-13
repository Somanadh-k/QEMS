import csv
import io
from collections import Counter
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_role
from app.core.db import get_db
from app.core.exceptions import ValidationError
from app.models import User
from app.repositories.error_repository import ErrorRepository
from app.schemas.report import ReportSummaryResponse, SeverityBreakdown

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
async def report_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: int | None = None,
    format: str = Query(default="json", pattern="^(json|csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("QA Reviewer", "Admin", "Viewer")),
):
    """Section 11.7 — filtered report by date range/department/category/severity."""
    errors, total = await ErrorRepository(db).list(department_id=department_id, page=1, page_size=1000)
    if date_from:
        errors = [e for e in errors if e.date_discovered >= date_from]
    if date_to:
        errors = [e for e in errors if e.date_discovered <= date_to]

    now = datetime.now(timezone.utc)
    open_count = sum(1 for e in errors if e.status != "Closed")
    closed_count = sum(1 for e in errors if e.status == "Closed")
    overdue_count = sum(1 for e in errors if e.due_at and e.due_at < now and e.status != "Closed")
    severity_counts = Counter(e.severity for e in errors)

    if format == "json":
        return ReportSummaryResponse(
            total_errors=len(errors),
            open_count=open_count,
            closed_count=closed_count,
            overdue_count=overdue_count,
            by_severity=[SeverityBreakdown(severity=s, count=c) for s, c in severity_counts.items()],
        )

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["qa_error_code", "title", "severity", "status", "department_id", "created_at"])
        for e in errors:
            writer.writerow([e.qa_error_code, e.title, e.severity, e.status, e.department_id, e.created_at])
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=qems_report.csv"},
        )

    raise ValidationError("PDF export is not implemented yet — use format=json or format=csv")
