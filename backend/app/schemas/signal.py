from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NeighbourItem(BaseModel):
    error_id: int
    qa_error_code: str
    title: str
    status: str
    severity: str
    created_at: datetime | None = None
    distance: float


class ScoreComponent(BaseModel):
    name: str
    weight: float
    value: float
    contribution: float


class SignalResponse(BaseModel):
    """Facts and narrative are deliberately separate keys.

    The UI renders `metrics` above `narrative` and can render metrics alone when the
    status is DEGRADED, which is what makes an outage a cosmetic loss.
    """

    status: str
    insight_id: int | None = None
    risk_band: str | None = None
    risk_score: float | None = None
    metrics: dict | None = None
    score_breakdown: dict | None = None
    narrative: dict | None = None
    neighbours: list[NeighbourItem] = Field(default_factory=list)
    provenance: dict | None = None
    reviewer_action: str | None = None
    disclaimer: str | None = None
    corpus_size: int | None = None
    required: int | None = None
    neighbours_found: int | None = None
    duplicate_of: dict | None = None


class InsightAckRequest(BaseModel):
    action: str  # ACCEPTED | PARTIALLY_ACCEPTED | REJECTED | NO_ACTION
    notes: str | None = None


class InsightResponse(BaseModel):
    # `model_name` is a real domain field (which LLM produced this), not a pydantic
    # attribute; opt out of the protected-namespace warning rather than renaming it.
    model_config = ConfigDict(protected_namespaces=())

    insight_id: int
    insight_type: str
    risk_band: str | None
    risk_score: float | None
    status: str
    model_name: str
    created_at: datetime
    reviewer_action: str | None
    reviewer_notes: str | None
