from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DecisionCreateRequest(BaseModel):
    # Was a bare `str`, relying only on the DB's ck_qa_decision_value CHECK constraint
    # to reject a bad value (finding D-09) -- safe, but a generic constraint-violation
    # 422 rather than a clear field-level validation error. Literal gives the same
    # safety with a message naming the allowed values.
    decision: Literal["Resolved", "Rejected", "Escalated"]
    notes: str


class DecisionCreateResponse(BaseModel):
    decision_id: int
    status: str
    decided_at: datetime
