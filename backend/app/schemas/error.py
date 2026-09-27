from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ErrorCreateRequest(BaseModel):
    # max_length matches the errors.title column (String(200)); without it an
    # over-length title reaches asyncpg as a StringDataRightTruncationError, which is
    # not an IntegrityError and was surfacing as an unhandled 500 (finding D-04).
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    category_id: int
    severity: str
    department_id: int
    date_discovered: date
    assigned_to: int | None = None
    # Recurrence is a property of a process, not a category. Without this the
    # process-concentration component of the recurrence score (weight 0.25) can never
    # fire for anything created through the API.
    process_id: int | None = None


class ErrorCreateResponse(BaseModel):
    error_id: int
    qa_error_code: str
    status: str
    due_at: datetime | None
    created_at: datetime


class ErrorStatusUpdateRequest(BaseModel):
    status: str
    admin_override: bool = False


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: int
    file_name: str
    file_url: str
    file_type: str
    file_size_kb: int
    uploaded_by: int
    sha256: str | None = None


class RebuttalSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rebuttal_id: int
    raised_by: int
    justification: str
    status: str
    created_at: datetime


class DecisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision_id: int
    decided_by: int
    decision: str
    notes: str
    decided_at: datetime


class ErrorListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error_id: int
    qa_error_code: str
    title: str
    status: str
    severity: str
    department_id: int
    category_id: int
    due_at: datetime | None
    created_at: datetime
    # Governance fields, so the queue can sort and colour by risk without a second call.
    sla_state: str | None = None
    sla_due_at: datetime | None = None
    sla_clock_owner_role: str | None = None
    risk_score: float | None = None
    escalation_level: int | None = None


class ErrorListResponse(BaseModel):
    items: list[ErrorListItem]
    total: int
    page: int
    page_size: int


class ErrorDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error_id: int
    qa_error_code: str
    title: str
    description: str
    category_id: int
    process_id: int | None = None
    severity: str
    status: str
    department_id: int
    raised_by: int
    assigned_to: int | None
    date_discovered: date
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    evidence: list[EvidenceSummary]
    rebuttals: list[RebuttalSummary]
    decisions: list[DecisionSummary]
