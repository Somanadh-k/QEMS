from pydantic import BaseModel


class EvidenceUploadResponse(BaseModel):
    evidence_id: int
    file_name: str
    file_url: str
    file_type: str
    file_size_kb: int
