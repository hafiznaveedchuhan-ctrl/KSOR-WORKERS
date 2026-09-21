from pydantic import BaseModel


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    query: str
    answer: str
    worker_type: str  # "grounded" or "ungrounded"
    latency_ms: float


class RefundRequest(BaseModel):
    query: str
    session_id: str | None = None  # minted server-side if omitted


class RefundResponse(BaseModel):
    query: str
    answer: str
    worker_type: str = "refund"
    session_id: str
    latency_ms: float
