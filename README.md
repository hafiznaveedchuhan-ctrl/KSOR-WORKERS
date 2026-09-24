# ksor-worker

Eight small AI agents over one Amazon affiliate knowledge base (KSOR), each
proving a different piece of what a real agentic system needs beyond "call
an LLM": grounding, domain separation, memory, evaluation, governance,
model routing, and — the last one — real multi-agent orchestration.

Built on the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python),
talking to a [KSOR](https://github.com/panaversity/ksor) knowledge record
(the separate `handbook` repo) over MCP.

## The five HTTP endpoints (`main.py`)

| | `POST /ask` | `POST /compare` | `POST /refund` | `POST /chat` | `POST /triage` |
|---|---|---|---|---|---|
| Tools | KSOR MCP | none | KSOR MCP | KSOR MCP | KSOR MCP (per specialist) |
| Scope | Amazon affiliate, **excluding** refunds/returns | none — answers anything | **only** refunds/returns/cancellations | **everything**, refunds included — no split | routed to 1 of 5 specialists |
| Memory | none (single-shot) | none | yes — `SQLiteSession` | yes — its own `SQLiteSession` | yes — its own `SQLiteSession` |
| Model | `gpt-4o-mini` | `gpt-4o-mini` | `gpt-4o-mini` | `gpt-4o-mini` | `gpt-4o-mini` |
| Used by | `curl`/testing | `curl`/testing | `curl`/testing | **the `handbook` site widget** (General mode) | **the `handbook` site widget** (Smart Triage mode) |

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

  You ──▶ POST /chat ──▶ run_general_agent() ──▶ MCP "search" (no scope split)
          (grounded, everything          │
           including refunds,            ▼
           carries session_id)  its own SQLiteSession, separate from /refund's
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

**Why `/chat` exists on top of both:** a single chat widget needs one
assistant that just answers whatever it's asked — refunds included — not a
picker between two narrower agents. `/chat` reuses `/ask`'s exact prompt
(so it inherits the same anti-hallucination and abstention rules) but
skips the refund exclusion entirely, and adds memory `/ask` doesn't have.
It is not "better" than `/ask`/`/refund` — it's the right shape
specifically for one continuous conversation surface.

## Three more agents on top of the same pattern (CLI only, not HTTP)

| | `eval_agent.py` | `policy_agent.py` | `router_agent.py` |
|---|---|---|---|
| Run | `uv run python -m ksor_worker.eval_agent` | `uv run python -m ksor_worker.policy_agent` | `uv run python -m ksor_worker.router_agent` |
| Does | answers via KSOR, then a second judge agent checks the answer against the exact source chunks retrieved for it | detects and anonymizes PII (names, emails, phones, financial data, passwords) before the query reaches KSOR | classifies query complexity, then answers with `gpt-4o-mini` (simple) or `gpt-4o` (complex) |
| Output | `GROUNDED` / `PARTIALLY_GROUNDED` / `HALLUCINATED` + matched citations | original query, anonymized query, answer | query type, model selected, reason, answer |

These are standalone `input()`-loop tools, not FastAPI routes — asked for
as directly runnable demo/testing tools.

## The eighth agent: `POST /triage` — real orchestration

`triage_agent.py` is one `TriageAgent` that hands off to exactly one of 5
specialists using the OpenAI Agents SDK's own `handoffs` mechanism
(`Agent(handoffs=[...])`, `result.last_agent.name`) — not a keyword
`if/else` pretending to be one:

```
  You ──▶ POST /triage ──▶ TriageAgent decides ──▶ hands off to ONE of:
          {"query": "..."}         │                 KSORWorker        (general KSOR questions)
                                    │                 RefundSpecialist  (refunds/returns/cancellations)
                                    │                 PolicySpecialist  (redacts PII, then answers)
                                    │                 EvalSpecialist    (answers + self groundedness check)
                                    ▼                 RouterSpecialist  (model-selection advice, no KSOR tools)
                        {"answer": "...", "routed_to": "RefundSpecialist", ...}
```

`KSORWorker` and `RefundSpecialist` reuse `worker.py`'s/`refund_agent.py`'s
exact `INSTRUCTIONS`; `PolicySpecialist`/`EvalSpecialist`/`RouterSpecialist`
are new, deliberately simpler single-call `Agent`s built specifically for
this file, because a handoff target must be a single `Agent` — the three
CLI tools above are two-step pipelines, not one, and stay completely
untouched. Two real bugs found and fixed live while building this — the
SDK's default handoff leaking the triage agent's own tool-call noise into
a specialist's context, and a prior specialist's decline priming
`KSORWorker` to skip searching an unrelated question — are recorded with
their fixes in `docs/adr/005-triage-handoffs.md`. Session memory (its own
`SQLiteSession`, `triage_sessions.db`) carries across a handoff: ask a
refund question, then a completely different question in the same
session, and the second specialist can still recall the first turn.

Runs as an endpoint (`main.py` stays a 5-endpoint app) and, like the three
CLI agents above, also standalone: `uv run python -m
ksor_worker.triage_agent`.

## Human Gate — refunds >= 5000 PKR wait for a person

`RefundSpecialist` has one action tool, `request_refund(request_id, amount)`
(`refund_gate.py`). Below `REFUND_GATE_THRESHOLD` (default `5000`, PKR) it
issues straight away. At or above it, it fires `refund/approval.requested` and
tells the customer the refund is **pending, not issued**. An Inngest function
then suspends on `step.wait_for_event` for up to 24 hours — no polling loop, no
open request — until a human sends `refund/approval.decided`:

| Decision event | Result | `audit_log.db` row |
|---|---|---|
| `approved: true` | refund issued (simulated — no payment system here) | `refund_issued` |
| `approved: false` (or anything but `true`) | refund blocked, rejection message | `refund_blocked` |
| no event in 24h | escalated | `escalated_timeout` |

The decision is matched to the request by `request_id` (not customer id).
Design and limits: `docs/adr/006-refund-approval-gate.md`.

**Test it** (no OpenAI key needed — events are sent straight to Inngest):

```sh
# terminal 1 — the app (Inngest runs in dev mode unless INNGEST_SIGNING_KEY is set)
uv run uvicorn main:app --port 8000
# terminal 2 — the Inngest dev server + UI at http://localhost:8288
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest

# terminal 3 — a 6000 PKR request; terminal 1 prints "Approval needed for request r1: amount 6000 PKR"
curl -X POST http://localhost:8288/e/test -H 'content-type: application/json' \
  -d '{"name":"refund/approval.requested","data":{"request_id":"r1","amount":6000}}'

# approve it ...
curl -X POST http://localhost:8288/e/test -H 'content-type: application/json' \
  -d '{"name":"refund/approval.decided","data":{"request_id":"r1","approved":true}}'
# ... or reject a different request instead: request_id "r2", "approved": false

sqlite3 audit_log.db "select request_id, action, detail from audit_log"
```

Expect `r1 | refund_issued` after approving, and `r2 | refund_blocked` (and no
`refund_issued` for `r2`) after rejecting. To see the timeout branch without
waiting a day, start the app with `REFUND_GATE_TIMEOUT_SECONDS=10` and send a
request nobody answers: it ends as `escalated_timeout`. Unit tests (no
servers): `uv run --group dev python tests/test_refund_gate.py`.

## Evals — the golden dataset (`evals/`)

Every agent behavior we have fixed is now a test case, so a later change cannot silently undo it. `evals/datasets/golden.jsonl`
is the artifact (**95 cases**, 45% hard, 12 Roman Urdu); the harness, graders and LLM judges are tooling on top. It follows the Agent
Factory book (Course Nine "Eval-Driven Development", "Trusting the Checker"): failures first, real traffic over imagination, judge
calibrated against a human, a bar per category written down. Design: `docs/adr/007-golden-dataset-and-evals.md`.

| Layer | What | Needs |
|---|---|---|
| Dataset validation | schema, unique inputs, every grounded quote verbatim in `fixtures/kb_snapshot.json`, >=30% hard | nothing (runs in CI) |
| Deterministic graders | exact strings, routing, URL allowlist, verdict tokens, audit rows, length, latency | nothing for unit/in-process gate; worker + MCP for live |
| DeepEval + Ragas judges | relevancy, faithfulness, hallucination, scope/honesty GEval; context relevance/recall | `OPENAI_API_KEY` (judge = `gpt-4o`, never the agents' `gpt-4o-mini`) |

```sh
cd evals && uv sync                                   # its own uv project: the app's uv.lock is untouched
uv run pytest suites -m "not live"                    # offline: dataset + unit + in-process refund gate (no key, this is CI)
uv run python scripts/validate_dataset.py -v          # what is still awaiting owner review
uv run python scripts/mutation_check.py --offline     # break a guard on purpose; the dataset must catch it

# live (worker on :8000, KSOR MCP on :8080, OPENAI_API_KEY, Inngest dev server for the gate flows)
uv run python scripts/run_live.py --critical          # the smoke set
uv run python scripts/run_live.py                     # everything, 3 repeats, paced
uv run python scripts/capture_baseline.py runs/<ts>/results.jsonl --reason "..."   # then check_regressions.py on later runs
```

Case statuses: `active` (gates), `known_failing` (a documented open bug; reported `UNEXPECTED_PASS` when it starts passing, so it gets
promoted) and `blocked_until_stable` (the fact lives only in an unpublished draft doc; correct behavior today is to abstain). The bars are in
`evals/docs/critical-metrics.md`. Verdicts keep infra `ERROR` (5xx, timeouts) apart from behavioral `FAIL`.

**Baseline (provisional, 2026-09-24):** every category 100% of graded active cases over 3 repeats; 5 known-failing + 3 blocked-until-stable tracked apart; live mutation check 3/3 caught. Two real grounding leaks are open (cancellation steps, generic product-hunting advice) — see `progress.md`.

**The first run already paid for itself:** it caught that this repo's own refund-gate change (ADR 006) made `RefundSpecialist` decline
"When will I get my refund?" 6/6 (6/6 answered before the gate). The cause was a prompt addendum, not the tool; removing it fixed it (ADR 007).

Env for the harness: `WORKER_URL`, `EVAL_PACING_SECONDS` (4), `EVAL_TIMEOUT_SECONDS` (90), `EVAL_LATENCY_BUDGET_MS` (180000),
`EVAL_JUDGE_MODEL` (gpt-4o), `WORKER_AUDIT_DB`, `INNGEST_EVENT_URL`, `EVAL_EXPECT_TIMEOUT_SECONDS` (only for the timeout gate case).

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

Every agent that touches KSOR (`/ask`, `/refund`, `/chat`, `/triage`, and
all four CLI agents) needs a running KSOR MCP server (defaults to
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

curl -X POST localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"query": "If a customer returns a product, what happens to my commission?"}'

curl -X POST localhost:8000/triage \
  -H 'content-type: application/json' \
  -d '{"query": "mera refund kab aayega"}'
# {"answer": "...", "routed_to": "RefundSpecialist", ...}
```

`/refund`, `/chat`, and `/triage` each return a `session_id` in their
response — send that same id back on the next call to continue the
conversation with real memory (all three keep separate histories even for
the same id):

```sh
curl -X POST localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"query": "And how do I source good product images?", "session_id": "<id from the previous response>"}'
```

The four CLI agents run the same way, each its own process:

```sh
uv run python -m ksor_worker.eval_agent
uv run python -m ksor_worker.policy_agent
uv run python -m ksor_worker.router_agent
uv run python -m ksor_worker.triage_agent
```

**Try the domain split**: ask `/ask` a refund question — it declines and
points to `/refund`. Ask `/refund` a non-refund question (even one KSOR
covers, like product sourcing) — it declines the other way. Ask `/ask`
something the record doesn't cover at all (e.g. *"Who won the cricket
world cup?"*) — a plain scope abstention, not a `/refund`-style decline
and not a fabricated answer. **Then ask `/chat` the exact same refund
question** — it just answers, no decline, no split, same conversation
memory whichever topic you ask about next.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | — | OpenAI API access for every agent |
| `MCP_URL` | no | `http://127.0.0.1:8080/mcp` | where the KSOR-connected agents look for the MCP server |
| `ALLOWED_ORIGINS` | no | `http://localhost:3000` | comma-separated origins `/refund` and `/chat` accept browser requests from (the `handbook` site's widget) |
| `REFUND_GATE_THRESHOLD` | no | `5000` | refund amount (PKR) at or above which a human must approve |
| `REFUND_GATE_TIMEOUT_SECONDS` | no | `86400` | how long the gate waits for a decision before escalating |
| `INNGEST_SIGNING_KEY` / `INNGEST_EVENT_KEY` | production only | — | unset = Inngest dev mode (local dev server); set both for Inngest Cloud |

## Project layout

```
main.py          # FastAPI app — GET /health, POST /ask, POST /compare, POST /refund, POST /chat
src/ksor_worker/
├── common.py         # shared MODEL, MCP_URL, MCP_TIMEOUT_SECONDS, ALLOWED_ORIGINS,
│                      # INSTRUCTIONS (base KSOR prompt, no refund clause — see below),
│                      # is_refund_related()/REFUND_DECLINE_MESSAGE
├── models.py         # AskRequest/AskResponse, RefundRequest/RefundResponse, ChatRequest/ChatResponse
├── worker.py          # run_grounded() — /ask
├── compare.py         # run_ungrounded() — /compare, its own unrestricted prompt
├── refund_agent.py    # run_refund_agent() — /refund, its own prompt + SQLiteSession memory
├── general_agent.py    # run_general_agent() — /chat, common.INSTRUCTIONS, no refund gate, own SQLiteSession
├── triage_agent.py     # run_triage_agent() — /triage, 5 specialists via SDK handoffs
├── refund_gate.py      # request_refund tool + Inngest approval gate + audit_log.db writer
├── eval_agent.py       # run_eval_agent() — CLI: answer + groundedness judge
├── policy_agent.py     # run_policy_agent() — CLI: PII detection + anonymized answer
└── router_agent.py     # run_router_agent() — CLI: complexity-based model routing
tests/test_health.py    # CI smoke test (FastAPI TestClient, no secrets needed)
tests/test_refund_gate.py  # gate tool + audit log unit test (no secrets, no Inngest server)
evals/                    # golden dataset + harness (own uv project) — see "Evals" above
docs/adr/                # 001: why the OpenAI Agents SDK; 002: why FastAPI;
│                         # 003: refund memory + the domain-split reliability saga;
│                         # 004: why eval/policy/router are CLI-only, no new KSOR content
│                         # 005: triage handoffs; 006: refund approval gate + audit log;
│                         # 007: golden dataset + eval-driven development
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
