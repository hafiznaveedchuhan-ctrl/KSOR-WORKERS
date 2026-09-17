from pydantic import BaseModel


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    query: str
    answer: str
    worker_type: str  # "grounded" or "ungrounded"
    latency_ms: float
