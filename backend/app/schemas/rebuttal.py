from datetime import datetime

from pydantic import BaseModel, Field


class RebuttalCreateRequest(BaseModel):
    # A blank justification defeats the purpose of the rebuttal-review workflow for
    # the QA Reviewer who has to act on it (finding D-06).
    justification: str = Field(min_length=1)


class RebuttalCreateResponse(BaseModel):
    rebuttal_id: int
    status: str
    created_at: datetime
