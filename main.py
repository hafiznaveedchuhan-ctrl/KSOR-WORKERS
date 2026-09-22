import time
import uuid

from agents import AgentsException
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.shared.exceptions import MCPError

from ksor_worker.common import ALLOWED_ORIGINS, REFUND_DECLINE_MESSAGE, is_refund_related
from ksor_worker.compare import run_ungrounded
from ksor_worker.general_agent import run_general_agent
from ksor_worker.models import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResponse,
    RefundRequest,
    RefundResponse,
    TriageRequest,
    TriageResponse,
)
from ksor_worker.refund_agent import run_refund_agent
from ksor_worker.triage_agent import run_triage_agent
from ksor_worker.worker import run_grounded

load_dotenv()

app = FastAPI(title="KSOR Worker")

# Needed for /refund and /chat: the site widget calls this API directly from
# the browser (system/site is a static export with no live server of its own
# to proxy through — see docs/adr/003-refund-agent-memory.md).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["content-type"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    start = time.perf_counter()
    # Deterministic backstop, checked before the agent runs at all — see
    # the comment on REFUND_KEYWORDS in common.py for why this exists
    # alongside (not instead of) the prompt instruction.
    if is_refund_related(request.query):
        return AskResponse(
            query=request.query,
            answer=REFUND_DECLINE_MESSAGE,
            worker_type="grounded",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
    try:
        answer = await run_grounded(request.query)
    except (MCPError, AgentsException) as exc:
        # MCPError: a tool call timed out mid-session (see the 5s-default
        # bug this project already hit and fixed in common.py).
        # AgentsException (e.g. UserError): the MCP connection itself
        # couldn't be established — the server is down/unreachable.
        # Both mean "the grounding backend failed", not "our code is
        # broken" — 502, and never a fabricated answer either way.
        raise HTTPException(
            status_code=502, detail=f"KSOR MCP server unavailable: {exc}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Grounded worker failed: {exc}"
        ) from exc
    latency_ms = (time.perf_counter() - start) * 1000
    return AskResponse(
        query=request.query,
        answer=answer,
        worker_type="grounded",
        latency_ms=latency_ms,
    )


@app.post("/compare", response_model=AskResponse)
async def compare(request: AskRequest) -> AskResponse:
    start = time.perf_counter()
    try:
        answer = await run_ungrounded(request.query)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Compare worker failed: {exc}"
        ) from exc
    latency_ms = (time.perf_counter() - start) * 1000
    return AskResponse(
        query=request.query,
        answer=answer,
        worker_type="ungrounded",
        latency_ms=latency_ms,
    )


@app.post("/refund", response_model=RefundResponse)
async def refund(request: RefundRequest) -> RefundResponse:
    session_id = request.session_id or str(uuid.uuid4())
    start = time.perf_counter()
    try:
        answer = await run_refund_agent(request.query, session_id)
    except (MCPError, AgentsException) as exc:
        raise HTTPException(
            status_code=502, detail=f"KSOR MCP server unavailable: {exc}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Refund agent failed: {exc}"
        ) from exc
    latency_ms = (time.perf_counter() - start) * 1000
    return RefundResponse(
        query=request.query,
        answer=answer,
        session_id=session_id,
        latency_ms=latency_ms,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """The general assistant behind the site widget — answers anything in
    the KSOR record, refunds included, with memory. Deliberately not
    behind the is_refund_related() gate /ask uses: this endpoint is meant
    to be the single, unrestricted-by-topic surface for one chat UI."""
    session_id = request.session_id or str(uuid.uuid4())
    start = time.perf_counter()
    try:
        answer = await run_general_agent(request.query, session_id)
    except (MCPError, AgentsException) as exc:
        raise HTTPException(
            status_code=502, detail=f"KSOR MCP server unavailable: {exc}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"General assistant failed: {exc}"
        ) from exc
    latency_ms = (time.perf_counter() - start) * 1000
    return ChatResponse(
        query=request.query,
        answer=answer,
        session_id=session_id,
        latency_ms=latency_ms,
    )


@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> TriageResponse:
    """Real orchestration: hands off to one of 5 specialist Agents via the
    SDK's own handoffs mechanism. `routed_to` is result.last_agent.name —
    the specialist that actually produced the answer — never hardcoded or
    guessed. See triage_agent.py and docs/adr/005-triage-handoffs.md."""
    session_id = request.session_id or str(uuid.uuid4())
    start = time.perf_counter()
    try:
        answer, routed_to = await run_triage_agent(request.query, session_id)
    except (MCPError, AgentsException) as exc:
        raise HTTPException(
            status_code=502, detail=f"KSOR MCP server unavailable: {exc}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Triage agent failed: {exc}"
        ) from exc
    latency_ms = (time.perf_counter() - start) * 1000
    return TriageResponse(
        query=request.query,
        answer=answer,
        routed_to=routed_to,
        session_id=session_id,
        latency_ms=latency_ms,
    )
