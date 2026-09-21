# ksor-worker

Six small AI agents over one Amazon affiliate knowledge base (KSOR), each
proving a different piece of what a real agentic system needs beyond "call
an LLM": grounding, domain separation, memory, evaluation, governance, and
model routing.

Built on the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python),
talking to a [KSOR](https://github.com/panaversity/ksor) knowledge record
(the separate `handbook` repo) over MCP.

## The three HTTP endpoints (`main.py`)

| | `POST /ask` | `POST /compare` | `POST /refund` |
|---|---|---|---|
| Tools | KSOR MCP (`search`, `outline`, `read`) | none | KSOR MCP |
| Scope | Amazon affiliate, **excluding** refunds/returns | none — answers anything | **only** refunds/returns/cancellations |
| Memory | none (single-shot) | none | yes — `SQLiteSession`, keyed by `session_id` |
| Model | `gpt-4o-mini` | `gpt-4o-mini` | `gpt-4o-mini` |

```
  You ──▶ POST /ask ──▶ run_grounded() ──▶ MCP "search" ──▶ ksor serve
          (grounded,          │                                  │
           refund-excluded)   │                     Gemini embed → Neon (pgvector)
                               ▼                                  │
                        AskResponse JSON  ◀── OpenAI writes the answer from the hits

  You ──▶ POST /compare ──▶ run_ungrounded() ──▶ answers from the model's own
          (no tools, unrestricted)                training, right or wrong

  You ──▶ POST /refund ──▶ run_refund_agent() ──▶ MCP "search" (refund-scoped)
          (grounded, refund-only,      │
           carries session_id)         ▼
                              SQLiteSession remembers this conversation's
                              prior turns automatically on every call
```

**The point of `/ask` vs `/compare`:** `/ask` can only say what the
knowledge base actually contains, and abstains plainly when it doesn't.
`/compare` will confidently answer anything — right or wrong, in scope or
not — because nothing is checking it against a source.

**Why `/refund` is separate, not just another `/ask` topic:** its
system prompt is scoped to refunds/returns/cancellations only, and it
carries real multi-turn memory `/ask` deliberately doesn't have. The two
agents partition the record by topic — `/ask` declines anything
refund-shaped (enforced in code, not just prompt — see "A real bug," below);
`/refund` declines everything that isn't.

## Three more agents on top of the same pattern (CLI only, not HTTP)

| | `eval_agent.py` | `policy_agent.py` | `router_agent.py` |
|---|---|---|---|
| Run | `uv run python -m ksor_worker.eval_agent` | `uv run python -m ksor_worker.policy_agent` | `uv run python -m ksor_worker.router_agent` |
| Does | answers via KSOR, then a second judge agent checks the answer against the exact source chunks retrieved for it | detects and anonymizes PII (names, emails, phones, financial data, passwords) before the query reaches KSOR | classifies query complexity, then answers with `gpt-4o-mini` (simple) or `gpt-4o` (complex) |
| Output | `GROUNDED` / `PARTIALLY_GROUNDED` / `HALLUCINATED` + matched citations | original query, anonymized query, answer | query type, model selected, reason, answer |

These are standalone `input()`-loop tools, not FastAPI routes — asked for
as directly runnable demo/testing tools. `main.py` stays a 3-endpoint app.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
git clone <this repo>
cd ksor-worker
uv sync
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-...
```

Every agent that touches KSOR (`/ask`, `/refund`, and all three CLI
agents) needs a running KSOR MCP server (defaults to
`http://127.0.0.1:8080/mcp`, overridable with `MCP_URL`) — that's `ksor
serve` in the separate `handbook` repo.

## Run

```sh
uv run uvicorn main:app --reload --port 8000
```

Interactive docs at `http://localhost:8000/docs`, or use `curl`:

```sh
curl localhost:8000/health

curl -X POST localhost:8000/ask \
  -H 'content-type: application/json' \
  -d '{"query": "What is the Amazon affiliate program?"}'

curl -X POST localhost:8000/compare \
  -H 'content-type: application/json' \
  -d '{"query": "Who won the cricket world cup?"}'

curl -X POST localhost:8000/refund \
  -H 'content-type: application/json' \
  -d '{"query": "If a customer returns a product, what happens to my commission?"}'
```

`/refund` returns a `session_id` in its response — send that same id back
on the next call to continue the conversation with real memory:

```sh
curl -X POST localhost:8000/refund \
  -H 'content-type: application/json' \
  -d '{"query": "And for electronics specifically?", "session_id": "<id from the previous response>"}'
```

The three CLI agents run the same way, each its own process:

```sh
uv run python -m ksor_worker.eval_agent
uv run python -m ksor_worker.policy_agent
uv run python -m ksor_worker.router_agent
```

**Try the domain split**: ask `/ask` a refund question — it declines and
points to `/refund`. Ask `/refund` a non-refund question (even one KSOR
covers, like product sourcing) — it declines the other way. Ask `/ask`
something the record doesn't cover at all (e.g. *"Who won the cricket
world cup?"*) — a plain scope abstention, not a `/refund`-style decline
and not a fabricated answer.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | — | OpenAI API access for every agent |
| `MCP_URL` | no | `http://127.0.0.1:8080/mcp` | where the KSOR-connected agents look for the MCP server |
| `ALLOWED_ORIGINS` | no | `http://localhost:3000` | comma-separated origins `/refund` accepts browser requests from (the `handbook` site's widget) |

## Project layout

```
main.py          # FastAPI app — GET /health, POST /ask, POST /compare, POST /refund
src/ksor_worker/
├── common.py         # shared MODEL, MCP_URL, MCP_TIMEOUT_SECONDS, ALLOWED_ORIGINS,
│                      # INSTRUCTIONS (base KSOR prompt, no refund clause — see below),
│                      # is_refund_related()/REFUND_DECLINE_MESSAGE
├── models.py         # AskRequest/AskResponse, RefundRequest/RefundResponse
├── worker.py          # run_grounded() — /ask
├── compare.py         # run_ungrounded() — /compare, its own unrestricted prompt
├── refund_agent.py    # run_refund_agent() — /refund, its own prompt + SQLiteSession memory
├── eval_agent.py       # run_eval_agent() — CLI: answer + groundedness judge
├── policy_agent.py     # run_policy_agent() — CLI: PII detection + anonymized answer
└── router_agent.py     # run_router_agent() — CLI: complexity-based model routing
tests/test_health.py    # CI smoke test (FastAPI TestClient, no secrets needed)
docs/adr/                # 001: why the OpenAI Agents SDK; 002: why FastAPI;
│                         # 003: refund memory + the domain-split reliability saga;
│                         # 004: why eval/policy/router are CLI-only, no new KSOR content
spec.md          # full technical spec
plan.md          # build phases
tasks.md         # task tracker
progress.md      # build log — every bug found and fixed, with evidence
CLAUDE.md        # working rules for this project
```

## Real bugs this project hit (and fixed) — the interesting part

**The SDK's MCP timeout default is too short.** `MCPServerStreamableHttp`
defaults to a 5-second tool-call timeout — too short for a real
embedding-backed search (Gemini embed + pgvector query). It silently
turned into a generic tool error, and the model answered from its own
memory instead. Fixed: `MCP_TIMEOUT_SECONDS = 30` in `common.py`.

**Prompt-only domain-split enforcement was unreliable — in both
directions.** A refund-worded question answered directly despite an
explicit instruction not to (3/3). Rewording fixed that but broke a
*completely unrelated* question ("Who won the cricket world cup?") the
other way — it started getting the refund-decline message instead of a
scope abstention (3-4/4). Root cause: two similar "if X, reply with
escape-hatch Y" instructions in one prompt, and the model conflating them.
Fixed by removing the refund clause from the shared prompt entirely and
enforcing it as a deterministic keyword check (`is_refund_related()`) in
code, before any agent runs. Full account: `docs/adr/003-refund-agent-memory.md`.

**`refund_agent` fabricated a citation link.** Asked a refund question, it
reliably (3/3) appended `[refund policy](https://www.amazon.com)` — a URL
that appears nowhere in the actual source document. Fixed with an explicit
"never include a URL unless it appears verbatim in the retrieved content"
instruction, applied to every agent sharing `common.INSTRUCTIONS`.
Re-verified clean, 3/3.

Worth knowing if you build your own MCP-backed agent and get answers that
don't match what your record actually contains, or a citation that looks
suspiciously generic — these are the concrete failure modes to test for,
not hypothetical ones.

## Read next

Start with `CLAUDE.md`, then `spec.md`, `plan.md`, and `docs/adr/` (001
through 004, in order) for the full design reasoning; `tasks.md` and
`progress.md` track what's been built and verified, with evidence.
