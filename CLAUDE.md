# CLAUDE.md — ksor-worker

Read spec.md, plan.md, tasks.md, docs/adr/001-use-openai-agents-sdk.md,
docs/adr/002-fastapi-harness.md, docs/adr/003-refund-agent-memory.md,
docs/adr/004-eval-policy-router-agents.md, and
docs/adr/005-triage-handoffs.md before making any change here.
This is its own repository — separate from `handbook` (Node/npm) on
purpose, no shared repo, no copies. Never import from `handbook` or assume
it's on disk.

1. Purpose: `main.py` (FastAPI) exposes four HTTP agents —
   `/ask` (grounded, KSOR MCP-connected, general Amazon-affiliate scope,
   **excluding** refunds/returns), `/compare` (no tools, a general
   assistant with no scope restriction, for contrast), `/refund`
   (grounded, KSOR MCP-connected, scoped **only** to refunds/returns/
   cancellations, with real multi-turn memory), and `/chat` (grounded,
   **no topic split at all** — answers refunds and everything else from
   one agent, with memory; this is what the `handbook` site's widget
   calls — see `general_agent.py` and rule 3a). Three more agents —
   `eval_agent.py`, `policy_agent.py`, `router_agent.py` — are standalone
   CLI tools (`uv run python -m ksor_worker.<name>`), not FastAPI
   endpoints; see rule 4a. All agents that reuse `common.INSTRUCTIONS` use
   the same `MODEL` from common.py for their base answering step.
2. `common.py` is the single source for `MODEL`, `MCP_URL`,
   `MCP_TIMEOUT_SECONDS`, `ALLOWED_ORIGINS`, worker.py's `INSTRUCTIONS`
   (its KSOR-scoped prompt — **no refund clause in it, on purpose, see
   rule 3**), and the `is_refund_related()`/`REFUND_DECLINE_MESSAGE` pair
   — never duplicate any of them. compare.py and refund_agent.py each keep
   their own `INSTRUCTIONS` defined locally, not in common.py — do not
   merge either back into a shared constant without the user asking for
   that again.
3. **The worker.py/refund_agent.py domain split is enforced two DIFFERENT
   ways, on purpose — do not "simplify" this to one mechanism.**
   `main.py`'s `/ask` handler, and every one of `eval_agent.py`/
   `policy_agent.py`/`router_agent.py` (which all reuse
   `common.INSTRUCTIONS`), check `is_refund_related()` in code *before*
   building an agent at all, short-circuiting to `REFUND_DECLINE_MESSAGE`
   on a match. **`common.INSTRUCTIONS` carries no refund-related clause at
   all** — a prompt-embedded version of this exclusion was tried, found
   unreliable, and then found to cause a *worse* bug (declining plainly
   unrelated questions like "who won the cricket world cup?" 3 times out
   of 4) before being removed entirely. Never re-add a refund clause to
   `common.INSTRUCTIONS` — the keyword gate is the *only* enforcement for
   this direction now. `refund_agent.py`'s reverse direction (recognizing
   an in-domain question that doesn't literally say "refund," like "how
   long until my commission is final?") was tested separately and found to
   work through its own prompt alone, so it keeps that prompt and has no
   code-level backstop. Full sequence in `progress.md` and
   `docs/adr/003-refund-agent-memory.md`.
   1. **`/chat` (`general_agent.py`) deliberately does NOT apply the
      `is_refund_related()` gate.** It reuses `common.INSTRUCTIONS`
      exactly as `/ask` does, but skips the gate on purpose — the point of
      this endpoint is one assistant with no topic split, refunds
      included. Don't add the gate here "for consistency" — that would
      just reintroduce `/refund`'s exclusion on an endpoint that exists
      specifically to not have one.
4. `worker.py`/`compare.py`/`refund_agent.py`/`general_agent.py` are
   library functions only (`run_grounded`/`run_ungrounded`/
   `run_refund_agent`/`run_general_agent`) — **no `input()`, no
   `__main__` block, no standalone CLI mode.** `main.py` is the only
   entrypoint for these four; test through its HTTP endpoints (`uvicorn`
   + `curl`/`/docs`), not by running these files directly.
   1. **Exception, deliberate**: `eval_agent.py`, `policy_agent.py`, and
      `router_agent.py` DO have `input()`/`__main__` CLI loops — they were
      asked for as standalone runnable tools
      (`uv run python -m ksor_worker.<name>`), not HTTP endpoints. Don't
      "fix" this inconsistency by either stripping their CLI mode or
      adding matching FastAPI routes without being asked.
5. `run_grounded`/`run_refund_agent`/`run_general_agent` (and the
   answering step inside `eval_agent`/`policy_agent`/`router_agent`) must
   never answer from the
   model's own memory when the KSOR tools return nothing relevant — the
   abstention text passes through `result.final_output` exactly as the
   tool call returns it, no rewriting. In `main.py`, an MCP failure
   (`MCPError` or `AgentsException`) is a `502`, never a fabricated `200`
   answer; the three CLI agents catch the same pair and print a clear
   `[error]` line instead of crashing.
6. Never commit `.env` — it holds `OPENAI_API_KEY`. `.env.example` stays a
   bare placeholder plus `MCP_URL`'s default. `refund_sessions.db` and
   `general_sessions.db` (the refund and general agents' own
   `SQLiteSession` stores — deliberately separate files, so a `/refund`
   conversation and a `/chat` conversation for the same `session_id` never
   share history) are runtime state, not source — gitignored, never
   committed.
7. Python 3.12, managed with `uv` only — no pip/poetry/conda commands here.
   Dev-only deps (currently just `httpx`, for the CI smoke test) go in the
   `dev` dependency group, not the main dependency list.
8. **Session/conversation memory is deliberately in scope for
   `refund_agent.py` and `general_agent.py` specifically** (the SDK's own
   `SQLiteSession`) — this is an intentional exception to "no database,"
   not a reversal of it. No Dockerfile, no Azure/Render config, no user
   database, no auth — all still explicitly future phases (see spec.md's
   Non-goals). Don't add those speculatively.
9. **Not every new agent needs new knowledge-base content.**
   `eval_agent`/`policy_agent`/`router_agent` are infrastructure/governance
   layers over the *existing* record, not new business domains — none of
   them got a new `handbook` document, and that was a deliberate judgment
   call (see ADR-004), not an oversight. Only add KSOR content for a new
   agent when it represents a genuinely new business domain the record
   doesn't cover yet, the way the refund agent did.
10. After any change that completes or alters a task, update tasks.md and
    append a line to progress.md. Don't let either drift from the code.
11. **`POST /triage` (`triage_agent.py`) is real SDK orchestration, not a
    keyword dispatcher.** One `TriageAgent` hands off to one of 5
    specialist `Agent`s via the OpenAI Agents SDK's own `handoffs`
    mechanism; `routed_to` in the response is `result.last_agent.name`,
    never hardcoded or inferred client-side. `KSORWorker` and
    `RefundSpecialist` inside it are the SAME `INSTRUCTIONS` as
    `worker.py`/`refund_agent.py` — but `PolicySpecialist`/
    `EvalSpecialist`/`RouterSpecialist` are NEW, deliberately simpler
    single-call `Agent`s built only for this file. **Don't "simplify" by
    trying to hand off to `run_eval_agent`/`run_policy_agent`/
    `run_router_agent` directly** — a handoff target must be a single
    `Agent` instance, and those three are two-step Python pipelines, not
    Agents; see docs/adr/005-triage-handoffs.md for why, and the three
    original CLI tools stay completely untouched.
    1. Every specialist is wrapped in `handoff(agent,
       input_filter=handoff_filters.remove_all_tools)`, never passed bare —
       found live that the SDK's default handoff leaks the triage agent's
       own tool-call/output items into what the specialist sees, and that
       derailed a strict domain check. **Never drop this filter.**
    2. `KSORWorker` inside `triage_agent.py` specifically carries
       `tool_choice="required"` — found live that, in a multi-specialist
       session, a prior turn's DECLINE from a different specialist can
       prime this agent to skip searching and self-decline an unrelated,
       in-scope question. Don't remove this or add it to `worker.py`'s
       standalone `INSTRUCTIONS`-based agent — `/ask` and `/chat` never
       carry a decline-flavored turn in their own history, so they don't
       need it, and `RefundSpecialist`'s own decline-without-searching path
       is intentional (see `refund_agent.py`) and must NOT get this flag.
    3. `triage_sessions.db` (its own `SQLiteSession` store, gitignored) is
       separate from `refund_sessions.db`/`general_sessions.db` — same
       reasoning as those two.
    4. `triage_agent.py` has its own `_cli()`/`__main__` (`uv run python -m
       ksor_worker.triage_agent`) — a deliberate exception matching rule
       4.1's precedent for `eval_agent.py`/`policy_agent.py`/
       `router_agent.py`, not a rule-4 violation.
