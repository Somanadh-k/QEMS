from pydantic import BaseModel


class SeverityBreakdown(BaseModel):
    severity: str
    count: int


class ReportSummaryResponse(BaseModel):
    total_errors: int
    open_count: int
    closed_count: int
    overdue_count: int
    by_severity: list[SeverityBreakdown]
