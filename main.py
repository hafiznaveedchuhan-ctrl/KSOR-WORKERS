import time

from agents import AgentsException
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from mcp.shared.exceptions import MCPError

from ksor_worker.compare import run_ungrounded
from ksor_worker.models import AskRequest, AskResponse
from ksor_worker.worker import run_grounded

load_dotenv()

app = FastAPI(title="KSOR Worker")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    start = time.perf_counter()
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
