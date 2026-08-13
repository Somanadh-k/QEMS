from datetime import datetime

from pydantic import BaseModel


class DecisionCreateRequest(BaseModel):
    decision: str  # Resolved | Rejected | Escalated
    notes: str


class DecisionCreateResponse(BaseModel):
    decision_id: int
    status: str
    decided_at: datetime
