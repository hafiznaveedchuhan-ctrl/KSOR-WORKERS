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


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None  # minted server-side if omitted


class ChatResponse(BaseModel):
    query: str
    answer: str
    worker_type: str = "general"
    session_id: str
    latency_ms: float


class TriageRequest(BaseModel):
    query: str
    session_id: str | None = None  # minted server-side if omitted


class TriageResponse(BaseModel):
    query: str
    answer: str
    routed_to: str  # the specialist Agent's name, from result.last_agent.name
    session_id: str
    latency_ms: float
