# Spec — ksor-worker

## Goal
A FastAPI harness around two agents: one grounded and scoped to the
Ibrahim Digital Solutions Amazon affiliate KSoR via MCP, one a general,
unrestricted Amazon affiliate assistant with no tools and no scope limit.
`POST /ask` and `POST /compare` answer the same question through each, so
the gap between a grounded and an ungrounded answer is visible in one HTTP
call each. This is the foundation for a later deploy to Vercel+Render or
Azure Container Apps — not built yet, on purpose (see Non-goals).

## Components
- `src/ksor_worker/common.py` — shared: `MODEL`, `MCP_URL`,
  `MCP_TIMEOUT_SECONDS`, and `INSTRUCTIONS` (the grounded worker's
  KSOR-scoped prompt only).
- `src/ksor_worker/models.py` — the API's Pydantic contract: `AskRequest`,
  `AskResponse`.
- `src/ksor_worker/worker.py` — `async def run_grounded(query: str) -> str`.
- `src/ksor_worker/compare.py` — `async def run_ungrounded(query: str) -> str`,
  its own local, unrestricted `INSTRUCTIONS`.
- `main.py` (project root) — the FastAPI app: `GET /health`, `POST /ask`,
  `POST /compare`.

## Model
`gpt-4o-mini` for both workers, imported from `common.py` — kept identical so
the model itself is never a variable in the comparison.

## System prompts (two, by design)
- **worker.py** (`common.INSTRUCTIONS`): casts the agent as the Amazon
  affiliate assistant for Ibrahim Digital Solutions, instructed to answer
  only from the KSOR knowledge base and to say plainly when a question falls
  outside it rather than guessing.
- **compare.py** (its own local `INSTRUCTIONS`): a general Amazon affiliate
  marketing assistant with no scope restriction and no knowledge-base
  reference — free to answer from its own training knowledge.

## HTTP API (`main.py`)

### `GET /health`
`200 {"status": "ok"}`. No dependencies — doesn't touch OpenAI or MCP, so it
works even with no `.env` and no `ksor serve` running. This is what CI's
smoke test checks.

### `POST /ask` — grounded
Request (`AskRequest`): `{"query": "<question>"}`
Response (`AskResponse`, `200`):
```json
{
  "query": "...",
  "answer": "...",
  "worker_type": "grounded",
  "latency_ms": 1234.5
}
```
Errors:
- `502` — the KSOR MCP server is unreachable, or a tool call inside it timed
  out (`agents.AgentsException` or `mcp.shared.exceptions.MCPError`).
  Verified live: with `ksor serve` stopped, this returns a clean `502`
  naming the real cause, never a fabricated answer.
- `500` — anything else unexpected (e.g. a bad `OPENAI_API_KEY`).

### `POST /compare` — ungrounded
Same request/response shape, `"worker_type": "ungrounded"`. No MCP
dependency, so this only fails on `500` (e.g. a bad `OPENAI_API_KEY`).

## MCP connection

`run_grounded()` opens its own `MCPServerStreamableHttp` **per call**
(`async with`, opened and closed inside the function) rather than one
shared, app-lifespan connection. Simpler and correctness-safe under
concurrent requests for a first version — a shared connection is a real
optimization but adds lifecycle/concurrency concerns not worth it yet (see
`docs/adr/002-fastapi-harness.md`).

**On "stateless" MCP**: there is no `stateless=` constructor argument on
`MCPServerStreamableHttp` — the streamable-HTTP transport is inherently
stateless per tool call; that's a transport property, not a flag to set.

## Environment
- `OPENAI_API_KEY` — required, from `.env`.
- `MCP_URL` — optional override, defaults to `http://127.0.0.1:8080/mcp`
  (assumes `ksor serve` is already running locally with
  `KSOR_AUTH=disabled-local`, per handbook's own dev setup — no auth headers
  are sent).

## Local run
```sh
uv sync
cp .env.example .env   # fill in OPENAI_API_KEY
uv run uvicorn main:app --reload --port 8000
```
`/ask` additionally needs `ksor serve` running (in the separate `handbook`
project) on the URL named by `MCP_URL`.

## Future deployment targets (not built yet)
Vercel+Render (split: a Render web service for the FastAPI app, since it's a
long-lived Python process, not a Vercel Function-shaped app) or Azure
Container Apps (a single container running `uvicorn`). Either needs a
`Dockerfile` and CI/CD wiring — explicitly out of scope for this phase (see
Non-goals and rule 6 in `CLAUDE.md`).

## Non-goals
No CLI mode (removed — `worker.py`/`compare.py` are library functions only,
no `input()` anywhere). No multi-turn memory beyond a single request, no
persistence, no authentication, no database/session storage, no
Dockerfile/Azure/Render config yet — all explicitly future phases.
