# Spec — ksor-worker

## Goal
A FastAPI harness around three agents, each scoped to its own domain of the
Ibrahim Digital Solutions Amazon affiliate KSoR: a general grounded worker
(`/ask`), an unrestricted ungrounded assistant for contrast (`/compare`),
and a refund/returns specialist with real conversation memory (`/refund`).
This is the foundation for a later deploy to Vercel+Render or Azure
Container Apps — not built yet, on purpose (see Non-goals).

## Components
- `src/ksor_worker/common.py` — shared: `MODEL`, `MCP_URL`,
  `MCP_TIMEOUT_SECONDS`, `ALLOWED_ORIGINS`, `INSTRUCTIONS` (worker.py's
  KSOR-scoped prompt, including its refund carve-out), and the
  `is_refund_related()` keyword check + `REFUND_DECLINE_MESSAGE` constant
  that backstop that carve-out (see "The refund/general domain split"
  below).
- `src/ksor_worker/models.py` — the API's Pydantic contract: `AskRequest`,
  `AskResponse`, `RefundRequest`, `RefundResponse`.
- `src/ksor_worker/worker.py` — `async def run_grounded(query: str) -> str`.
- `src/ksor_worker/compare.py` — `async def run_ungrounded(query: str) -> str`,
  its own local, unrestricted `INSTRUCTIONS`.
- `src/ksor_worker/refund_agent.py` — `async def run_refund_agent(query:
str, session_id: str) -> str`, its own local `INSTRUCTIONS` restricting it
  to refunds/returns/cancellations, with real multi-turn memory via the
  SDK's `SQLiteSession`.
- `main.py` (project root) — the FastAPI app: `GET /health`, `POST /ask`,
  `POST /compare`, `POST /refund`.

## Model
`gpt-4o-mini` for all three agents, imported from `common.py` — kept
identical so the model itself is never a variable in any comparison.

## System prompts (three, by design)
- **worker.py** (`common.INSTRUCTIONS`): casts the agent as the Amazon
  affiliate assistant for Ibrahim Digital Solutions, instructed to answer
  only from the KSOR knowledge base and to say plainly when a question falls
  outside it rather than guessing — **and to decline refund/return/
  cancellation questions**, redirecting to the refund assistant instead.
- **compare.py** (its own local `INSTRUCTIONS`): a general Amazon affiliate
  marketing assistant with no scope restriction and no knowledge-base
  reference — free to answer from its own training knowledge. Unchanged by
  the refund work.
- **refund_agent.py** (its own local `INSTRUCTIONS`): answers only
  refund/return/cancellation questions (and their direct effects — commission
  reversal, the holding period, return windows) from the KSOR knowledge
  base; declines everything else the KSOR covers, even topics like product
  hunting or reviews.

## The refund/general domain split — and a real reliability finding

worker.py and refund_agent.py are meant to partition the KSOR's content by
topic through their prompts alone (MCP's `search` tool has no per-agent
category filter to enforce this with server-side). **Prompt-only
enforcement of worker.py's refund carve-out was tested and found
unreliable**: with a plainly refund-worded question ("If a customer
returns a product, what happens to my commission?"), worker.py answered it
directly — using the newly-added `refund-policy.md` content — on 3 out of 3
repeated calls, despite an explicit, front-loaded instruction not to. A
later attempt with a more specific instruction and `temperature=0`
*improved* consistency but did not fully fix it, and separately introduced
the opposite failure on an unrelated question (see `progress.md` for the
full sequence).

**Fix**: a deterministic keyword check, `is_refund_related()` in
`common.py`, runs in `main.py`'s `/ask` handler **before the agent runs at
all** — a keyword hit short-circuits straight to `REFUND_DECLINE_MESSAGE`
with no model call. The prompt instruction stays as a second layer, for
refund-adjacent phrasing (like "how long until my commission is final?")
that doesn't contain an obvious keyword — the refund agent's *own* fuzzy
in-domain detection (the reverse direction: recognizing an in-domain
question that doesn't say "refund") was tested and found to work reliably
through the prompt alone, so no code-level backstop was needed there.
`temperature=0` was kept on both agents regardless, since a lower-variance
classifier is a reasonable default even with the keyword backstop in place.

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

### `POST /refund` — refund/returns specialist, with memory
Request (`RefundRequest`): `{"query": "<question>", "session_id":
"<optional>"}`
Response (`RefundResponse`, `200`):
```json
{
  "query": "...",
  "answer": "...",
  "worker_type": "refund",
  "session_id": "...",
  "latency_ms": 1234.5
}
```
`session_id` is minted with `uuid4()` if the caller omits it, and always
comes back in the response — send the same `session_id` on the next call
to continue the same conversation; the SDK's `SQLiteSession` (keyed by that
id, in `refund_sessions.db`) automatically carries prior turns forward.
Same `502`/`500` error shape as `/ask`.

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
