# Spec — ksor-worker

## Goal
A FastAPI harness around four HTTP-facing agents over the Ibrahim Digital
Solutions Amazon affiliate KSoR: a general grounded worker excluding
refunds (`/ask`), an unrestricted ungrounded assistant for contrast
(`/compare`), a refund/returns specialist with real conversation memory
(`/refund`), and a general assistant with no topic split at all — refunds
included — also with memory (`/chat`, the site widget's backend) — plus
three standalone CLI tools that add evaluation, governance, and
model-routing on top of the same grounded-answer pattern (`eval_agent.py`,
`policy_agent.py`, `router_agent.py`; see ADR-004). This is the foundation
for a later deploy to Vercel+Render or Azure Container Apps — not built
yet, on purpose (see Non-goals).

## Components
- `src/ksor_worker/common.py` — shared: `MODEL`, `MCP_URL`,
  `MCP_TIMEOUT_SECONDS`, `ALLOWED_ORIGINS`, `INSTRUCTIONS` (the base
  KSOR-scoped prompt every grounded agent's answering step reuses — **no
  refund clause**, see "The refund/general domain split" below), and the
  `is_refund_related()` keyword check + `REFUND_DECLINE_MESSAGE` constant
  that are now the *sole* enforcement of `/ask`'s refund exclusion
  (`/chat` deliberately does not use this gate).
- `src/ksor_worker/models.py` — the API's Pydantic contract: `AskRequest`,
  `AskResponse`, `RefundRequest`, `RefundResponse`, `ChatRequest`,
  `ChatResponse`.
- `src/ksor_worker/worker.py` — `async def run_grounded(query: str) -> str`.
- `src/ksor_worker/compare.py` — `async def run_ungrounded(query: str) -> str`,
  its own local, unrestricted `INSTRUCTIONS`.
- `src/ksor_worker/refund_agent.py` — `async def run_refund_agent(query:
str, session_id: str) -> str`, its own local `INSTRUCTIONS` restricting it
  to refunds/returns/cancellations, with real multi-turn memory via the
  SDK's `SQLiteSession` (`refund_sessions.db`).
- `src/ksor_worker/general_agent.py` — `async def run_general_agent(query:
str, session_id: str) -> str`, reuses `common.INSTRUCTIONS` (no topic
  restriction), its own `SQLiteSession` (`general_sessions.db`, kept
  separate from the refund agent's).
- `src/ksor_worker/eval_agent.py` — `async def run_eval_agent(query: str) ->
tuple[str, EvalVerdict]`: answers via KSOR, then judges the answer against
  the exact source chunks retrieved for it. CLI only.
- `src/ksor_worker/policy_agent.py` — `async def run_policy_agent(query:
str) -> dict`: detects and anonymizes sensitive data before the (anonymized)
  query reaches KSOR. CLI only.
- `src/ksor_worker/router_agent.py` — `async def run_router_agent(query:
str) -> dict`: classifies query complexity, then answers using `gpt-4o-mini`
  or `gpt-4o` accordingly. CLI only.
- `main.py` (project root) — the FastAPI app: `GET /health`, `POST /ask`,
  `POST /compare`, `POST /refund`, `POST /chat`.

## Model
`gpt-4o-mini` (`common.MODEL`) for `/ask`, `/compare`, `/refund`,
`eval_agent`, and `policy_agent` — kept identical so the model itself is
never a variable in any comparison between them. `router_agent` is the one
deliberate exception: it answers with `gpt-4o-mini` or `gpt-4o` depending
on its own classification (that's its entire purpose), though its
classifier step always runs on `gpt-4o-mini` regardless of what it
decides.

## System prompts
- **worker.py** (`common.INSTRUCTIONS`, also reused by `eval_agent.py`/
  `policy_agent.py`/`router_agent.py`'s answering step): casts the agent as
  the Amazon affiliate assistant for Ibrahim Digital Solutions, instructed
  to answer only from the KSOR knowledge base and to say plainly when a
  question falls outside it rather than guessing. **Carries no
  refund-related clause at all** — see the domain-split section below for
  why.
- **compare.py** (its own local `INSTRUCTIONS`): a general Amazon affiliate
  marketing assistant with no scope restriction and no knowledge-base
  reference — free to answer from its own training knowledge. Unaffected
  by the refund work.
- **refund_agent.py** (its own local `INSTRUCTIONS`): answers only
  refund/return/cancellation questions (and their direct effects — commission
  reversal, the holding period, return windows) from the KSOR knowledge
  base; declines everything else the KSOR covers, even topics like product
  hunting or reviews.

## The refund/general domain split — enforced by code alone, not prompt

worker.py and refund_agent.py partition the KSOR's content by topic (MCP's
`search` tool has no per-agent category filter to enforce this with
server-side). **Prompt-only enforcement of worker.py's refund exclusion
was tried twice and failed twice, in two different ways**, before landing
on the current design:

1. A plainly refund-worded question answered directly, using
   `refund-policy.md`'s own content, on 3/3 calls despite an explicit
   instruction not to.
2. After rewording, that case was fixed, but a **plainly unrelated**
   question ("Who won the cricket world cup?") started getting the refund
   decline message on 3/4 calls — the model was conflating two
   similar-looking "if X, reply with escape-hatch Y" instructions in one
   prompt.

**Current design**: `common.INSTRUCTIONS` carries no refund clause at all.
`is_refund_related()` — a plain keyword match ("refund," "return,"
"cancel," "reversed," etc.) — is the **sole** enforcement, checked in code
before any agent that reuses `common.INSTRUCTIONS` is built: `main.py`'s
`/ask` handler, and each of `eval_agent.py`/`policy_agent.py`/
`router_agent.py`. A match short-circuits straight to
`REFUND_DECLINE_MESSAGE` with no model call at all. Accepted trade-off: a
genuinely refund-adjacent question with no matching keyword (e.g. "how
long until my commission is final?") is no longer redirected to the
refund agent — it gets answered normally from KSOR content instead, which
is a minor, low-stakes gap next to the false-positive bug it replaced.

`refund_agent.py`'s *reverse* direction (recognizing an in-domain question
that doesn't say "refund") is a different, separately-tested mechanism —
its own prompt was found to work reliably (not the shared
`common.INSTRUCTIONS`), so it keeps that prompt and has no code-level
backstop. `temperature=0` is kept on every agent built from
`common.INSTRUCTIONS` regardless of the keyword gate, since a
lower-variance classifier is a reasonable default on its own. Full
sequence: `progress.md` and `docs/adr/003-refund-agent-memory.md`.

## Three CLI agents on top of the same pattern (see ADR-004)

- **`eval_agent.py`**: answers a query the same way `/ask` does, then a
  second, separate judge agent (structured `EvalVerdict` output) checks
  whether the answer is actually supported by the exact source chunks the
  first agent's `search` tool call returned (read from the run's own
  `ToolCallOutputItem`s, not a second search) — verdict `GROUNDED`,
  `PARTIALLY_GROUNDED`, or `HALLUCINATED`. An honest abstention ("outside
  this knowledge base's scope") is itself `GROUNDED`, never
  `HALLUCINATED` — declining without evidence is correct behavior, not a
  fabrication (a real, tested-and-fixed judge bug — see progress.md).
- **`policy_agent.py`**: a detector agent (structured `PiiDetection`
  output) finds and replaces names/emails/phones/financial data/passwords
  with bracketed placeholders before the *anonymized* query ever reaches
  KSOR.
- **`router_agent.py`**: a classifier agent (structured `RoutingDecision`
  output, always running on `gpt-4o-mini` regardless of its answer) picks
  `gpt-4o-mini` for a simple/factual question or `gpt-4o` for a
  multi-step/comparative one, then answers with the selected model.

All three are standalone, `input()`-loop CLI tools
(`uv run python -m ksor_worker.<name>`) — not FastAPI endpoints; this is a
deliberate exception to the "no CLI mode" rule that applies to
`worker.py`/`compare.py`/`refund_agent.py` (see `CLAUDE.md` rule 4a).

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

### `POST /chat` — general assistant, no topic split, with memory
Same request/response shape as `/refund` (`ChatRequest`/`ChatResponse`,
`"worker_type": "general"`), backed by `general_agent.py`'s
`run_general_agent()`. This is what the `handbook` site's widget calls.
Reuses `common.INSTRUCTIONS` exactly as `/ask` does, but — unlike `/ask` —
does **not** apply the `is_refund_related()` gate, so a refund question is
answered directly, in the same conversation as anything else. Memory via
its own `SQLiteSession` in `general_sessions.db` — deliberately separate
from `refund_sessions.db`, so the same `session_id` used against `/refund`
and against `/chat` never shares history between the two.

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

The three CLI agents run the same way, each its own process, each also
needing `ksor serve` up:
```sh
uv run python -m ksor_worker.eval_agent
uv run python -m ksor_worker.policy_agent
uv run python -m ksor_worker.router_agent
```

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
