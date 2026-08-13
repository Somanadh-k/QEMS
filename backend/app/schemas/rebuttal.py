from datetime import datetime

from pydantic import BaseModel


class RebuttalCreateRequest(BaseModel):
    justification: str


class RebuttalCreateResponse(BaseModel):
    rebuttal_id: int
    status: str
    created_at: datetime
