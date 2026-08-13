from pydantic import BaseModel


class RootCauseRequest(BaseModel):
    error_id: int


class RootCauseResponse(BaseModel):
    label: str = "AI Suggestion"
    suggested_root_cause: str
    confidence: str


class SimilarErrorItem(BaseModel):
    error_id: int
    qa_error_code: str
    title: str
    status: str


class SeverityPredictionRequest(BaseModel):
    title: str
    description: str


class SeverityPredictionResponse(BaseModel):
    label: str = "AI Suggestion"
    suggested_severity: str
    rationale: str


class ReportSummaryRequest(BaseModel):
    date_from: str
    date_to: str
    department_id: int | None = None


class ReportSummaryResponse(BaseModel):
    label: str = "AI Suggestion"
    summary: str


class SmartRecommendationRequest(BaseModel):
    category_id: int
    department_id: int


class SmartRecommendationResponse(BaseModel):
    label: str = "AI Suggestion"
    recommended_owner_hint: str
    sla_risk: str
    reasoning: str


class NLSearchRequest(BaseModel):
    query: str


class NLSearchResponse(BaseModel):
    label: str = "AI Suggestion"
    status: str | None = None
    severity: str | None = None
    department_name: str | None = None
    category_name: str | None = None
    date_from: str | None = None
    date_to: str | None = None
