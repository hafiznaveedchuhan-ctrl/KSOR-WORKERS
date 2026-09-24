# Tasks — ksor-worker

## CLI-era build (done)

| # | Task                                          | Status  |
|---|------------------------------------------------|---------|
| 1 | uv project init + deps                         | done    |
| 2 | Governance docs (CLAUDE/spec/plan/tasks/ADR-001)| done    |
| 3 | common.py                                       | done    |
| 4 | worker.py (CLI)                                 | done    |
| 5 | compare.py (CLI)                                | done    |
| 6 | Verify both with uv run                         | done    |
| 7 | progress.md entry                               | done    |

## FastAPI harness build (this pass)

| # | Task                                                    | Status |
|---|----------------------------------------------------------|--------|
| 8  | Add fastapi/uvicorn/pydantic deps; remove stale scaffold script | done |
| 9  | `src/ksor_worker/models.py` (AskRequest/AskResponse)     | done |
| 10 | `common.py`: rename `KSOR_MCP_URL` → `MCP_URL`           | done |
| 11 | `worker.py`: refactor to `run_grounded()`, drop CLI       | done |
| 12 | `compare.py`: refactor to `run_ungrounded()`, drop CLI    | done |
| 13 | `main.py`: `/health`, `/ask`, `/compare`, 502 vs 500      | done |
| 14 | `.env.example` updated (`OPENAI_API_KEY`, `MCP_URL`)      | done |
| 15 | `.github/workflows/ci.yml` (this repo's own, TestClient)  | done |
| 16 | `tests/test_health.py`                                    | done |
| 17 | docs updated: spec/plan/tasks/README/CLAUDE/ADR-002       | done |
| 18 | Verify: no `input()` anywhere                              | done |
| 19 | Verify: `/health` → 200                                    | done |
| 20 | Verify: `/ask` with `ksor serve` DOWN → clean 502          | done |
| 21 | Verify: `/compare` → 200, ungrounded answer                | done |
| 22 | Verify: `/ask` with `ksor serve` UP → grounded 200 answer  | done |
| 23 | `handbook` repo cleanup (remove copied ksor-worker/ + its CI) | done |
| 24 | Create the new standalone `ksor-worker` GitHub repo         | waiting on user |
| 25 | First push to the new repo + confirm its CI is green        | pending |
| 26 | progress.md entry for this pass                             | done |

## Refund agent + knowledge docs + widget build (this pass)

| # | Task                                                          | Status |
|---|------------------------------------------------------------------|--------|
| 27 | 3 knowledge docs in `handbook`: product-sourcing, product-listing, refund-policy | done |
| 28 | `handbook`: `npm run check` + `ksor build` + `ksor ingest --flip` | done |
| 29 | `common.py`: worker.py refund carve-out, `ALLOWED_ORIGINS`, `is_refund_related()`, `REFUND_DECLINE_MESSAGE` | done |
| 30 | `src/ksor_worker/refund_agent.py` (`run_refund_agent`, `SQLiteSession` memory) | done |
| 31 | `models.py`: `RefundRequest`/`RefundResponse`                     | done |
| 32 | `main.py`: `POST /refund`, CORS middleware, keyword-check backstop | done |
| 33 | `worker.py`/`refund_agent.py`: `ModelSettings(temperature=0)`      | done |
| 34 | `.gitignore`: `*.db` (refund_sessions.db)                          | done |
| 35 | `docs/adr/003-refund-agent-memory.md`                              | done |
| 36 | docs updated: spec.md, CLAUDE.md                                   | done |
| 37 | Verify: `/refund` memory across 2 turns (same session_id)          | done |
| 38 | Verify: `/ask` declines refund questions (3/3, deterministic)      | done |
| 39 | Verify: `/refund` declines off-domain questions (3/3)              | done |
| 40 | Verify: `/refund` answers non-literal in-domain questions (3/3)    | done |
| 41 | Verify: `/compare` unaffected                                      | done |
| 42 | Widget in `system/site` (Part 3)                                   | done |
| 43 | Commit this pass's changes (handbook + ksor-worker) — push still waiting on the new GitHub repo (task 24) | done (commit) |
| 44 | progress.md entry for this pass                                   | done |
| 45 | Push `ksor-worker` to `KSOR-WORKERS` GitHub repo, confirm CI green  | done |

## 3 infrastructure agents: eval / policy / router (this pass)

| # | Task                                                              | Status |
|---|---------------------------------------------------------------------|--------|
| 46 | `src/ksor_worker/eval_agent.py` (`run_eval_agent`, groundedness judge, CLI) | done |
| 47 | `src/ksor_worker/policy_agent.py` (`run_policy_agent`, PII detection/anonymization, CLI) | done |
| 48 | `src/ksor_worker/router_agent.py` (`run_router_agent`, complexity-based model routing, CLI) | done |
| 49 | Judged: does KSOR knowledge content need to grow for these agents? Decided no (infrastructure layers, not a new domain) — see ADR-004 | done |
| 50 | Verify: eval_agent GROUNDED on a real answer, matched citations correct | done |
| 51 | **Bug found**: judge marked an honest abstention `HALLUCINATED` — fixed judge prompt to treat a clean abstention as `GROUNDED` | done |
| 52 | **Bug found (pre-existing, not new)**: reusing `common.INSTRUCTIONS` in eval_agent exposed that `/ask` itself declines a *plainly unrelated* question ("cricket world cup") as if it were a refund question, 3/4 times — the keyword gate correctly said no, the model's own prompt-embedded refund clause caused it anyway | done |
| 53 | **Fix**: removed the refund clause from `common.INSTRUCTIONS` entirely; `is_refund_related()` is now the sole enforcement everywhere it's used | done |
| 54 | Regression battery re-run after the fix: 19 cases across `/ask`, `/refund`, unrelated-question — all pass | done |
| 55 | Applied the same `is_refund_related()` gate to eval_agent/policy_agent/router_agent, consistent with `/ask` | done |
| 56 | `docs/adr/003-refund-agent-memory.md` updated with the further finding and fix | done |
| 57 | `docs/adr/004-eval-policy-router-agents.md` (new)                     | done |
| 58 | docs updated: spec.md, CLAUDE.md, tasks.md, progress.md               | done |
| 59 | Verified all 3 new agents end-to-end (eval, policy anonymization, router simple/complex) | done |
| 60 | Commit + push                                                          | done |

## Strict audit → genuine 100/100 (this pass)

| # | Task                                                                   | Status |
|---|----------------------------------------------------------------------|--------|
| 61 | Fresh live re-test of all 19+ regression cases (both repos)           | done |
| 62 | **Bug found**: `refund_agent` fabricated a citation URL (`https://www.amazon.com`) not present in any source, reproducible 3/3 | done |
| 63 | **Fix**: explicit "never invent a URL" instruction added to `refund_agent.py` and shared `common.INSTRUCTIONS`; re-verified clean 3/3 | done |
| 64 | **Bug found**: 1/4 abstention answers phrased as a temporary access problem ("unable to access... at the moment") instead of a clean scope boundary | done |
| 65 | **Fix**: `common.INSTRUCTIONS` now specifies exact abstention wording and forbids "unable to access"/"at the moment" phrasing; re-verified 4/4 consistent | done |
| 66 | **Gap found**: `README.md` never mentioned `refund_agent`/`eval_agent`/`policy_agent`/`router_agent` at all, plus a stray leftover `# KSOR-WORKERS` heading at the end | done |
| 67 | **Fix**: `README.md` fully rewritten — all 6 agents documented, the 3 real bugs section rewritten with evidence, stray heading removed | done |
| 68 | Security audit: `git log -p --all` grepped for secret patterns in both repos — clean; `.env` never committed in either repo's full history | done |
| 69 | CORS audit: confirmed live that an untrusted origin gets no `access-control-allow-origin` header (not a wildcard) | done |
| 70 | Full regression battery + memory + eval/policy/router re-verified live after both fixes — all pass | done |
| 71 | Commit + push this pass                                                | done |

## General assistant (`/chat`) for the widget — no topic split (this pass)

| # | Task                                                                   | Status |
|---|----------------------------------------------------------------------|--------|
| 72 | User asked: widget should answer everything (refunds + all topics), not just refund — clarified via question: one unified assistant, not a selector/multi-pane | done |
| 73 | `src/ksor_worker/general_agent.py` (`run_general_agent`, reuses `common.INSTRUCTIONS`, no `is_refund_related()` gate, own `SQLiteSession` in `general_sessions.db`) | done |
| 74 | `models.py`: `ChatRequest`/`ChatResponse`                              | done |
| 75 | `main.py`: `POST /chat`                                                | done |
| 76 | Verify live: `/chat` answers a refund question directly (no redirect), 3/3 | done |
| 77 | Verify live: `/chat` memory carries across a topic switch (refund → sourcing, same session) | done |
| 78 | Verify live: `/chat` still abstains cleanly on a plainly unrelated question | done |
| 79 | Verify live: `/chat` inherits the anti-hallucination fix (no fabricated link), 3/3 | done |
| 80 | Verify live: existing `/ask`, `/refund`, `/compare` behavior unaffected | done |
| 81 | `handbook`: `refund-widget.tsx` renamed to `assistant-widget.tsx`, `RefundWidget` → `AssistantWidget`, endpoint switched to `/chat`, copy/labels generalized | done |
| 82 | `handbook`: `app/layout.tsx` import updated; `tsc --noEmit` clean; live dev-server render confirmed the renamed widget | done |
| 83 | `handbook`: CORS re-confirmed live for `/chat` specifically             | done |
| 84 | Docs updated: `CLAUDE.md`, `spec.md`, `README.md` (ksor-worker); `AGENTS.md` (handbook) | done |
| 85 | Commit + push both repos                                               | done |

## Triage agent — real SDK handoffs, `/triage`, widget toggle (this pass)

| # | Task                                                                   | Status |
|---|----------------------------------------------------------------------|--------|
| 86 | User asked for a real orchestration layer: one triage agent, SDK `handoffs`, hands off to 5 specialists — not an if/else | done |
| 87 | Confirmed real SDK handoff API against the installed `openai-agents` version before writing code | done |
| 88 | **Architectural mismatch found**: a handoff target must be a single `Agent`; `eval_agent.py`/`policy_agent.py`/`router_agent.py` are 2-step pipelines, not Agents — resolved by building new, simpler single-call specialist Agents for triage specifically, CLI tools untouched (ADR-005) | done |
| 89 | `src/ksor_worker/triage_agent.py`: `KSORWorker`/`RefundSpecialist` (reuse existing `INSTRUCTIONS`) + `PolicySpecialist`/`EvalSpecialist`/`RouterSpecialist` (new) + `TriageAgent`, `run_triage_agent()`, own `triage_sessions.db` | done |
| 90 | `models.py`: `TriageRequest`/`TriageResponse` (incl. `routed_to`)      | done |
| 91 | `main.py`: `POST /triage`, same 502/500 shape as other endpoints      | done |
| 92 | **Bug found live**: default handoff leaks the triage agent's own tool-call/output into the specialist's context — derailed `RefundSpecialist`'s domain check 3/3 for a plain in-domain question | done |
| 93 | **Fix**: every specialist wrapped in `handoff(agent, input_filter=handoff_filters.remove_all_tools)`; re-verified 3/3 | done |
| 94 | **Bug found live**: `EvalSpecialist` invented non-spec verdict words (`ABSTAINED`, `UNVERIFIED`) instead of the 3 fixed tokens | done |
| 95 | **Fix**: prompt now states the 3-token constraint negatively as well as positively; re-verified 3/3 | done |
| 96 | **Bug found live**: `RouterSpecialist` declined a valid model-selection question ~2/3 of the time, reading its own embedded task description as "too vague" | done |
| 97 | **Fix**: prompt clarified that the query itself is the task, however phrased; re-verified 3/3 | done |
| 98 | **Bug found live**: a prior specialist's DECLINE text (not tool-call noise) can prime `KSORWorker`'s next turn to skip searching and self-decline an unrelated, in-scope question — reproduced with plain `Agent`+`Runner.run()`, no triage machinery, confirming it's a `common.INSTRUCTIONS`+history property, not a handoff bug | done |
| 99 | Prompt-only fix attempted first (a note telling `KSORWorker` to disregard unrelated prior declines) — did not work reliably | done |
| 100 | **Fix**: `tool_choice="required"` on `KSORWorker` specifically inside `triage_agent.py` only (not touched in `common.py`/`worker.py`, and not applied to `RefundSpecialist`, whose decline-without-searching is by design) — re-verified 3/3 clean at realistic (paced) turn spacing | done |
| 101 | **Found, documented, not fixed (pre-existing, out of scope)**: `refund_agent.py`'s own domain check is inconsistent on Roman Urdu phrasing, reproduced identically on the unmodified `/refund` endpoint with no triage involved | done |
| 102 | **Found, documented, not fixed (pre-existing, out of scope)**: `common.INSTRUCTIONS`-based agents occasionally answer from general/pretrained knowledge instead of abstaining when the record has no matching content (e.g. order-cancellation steps not in `refund-policy.md`) — a grounding leak predating this session's work, confirmed by grepping the source document | done |
| 103 | `triage_agent.py` given its own `_cli()`/`__main__` (`uv run python -m ksor_worker.triage_agent`), matching the eval/policy/router precedent | done |
| 104 | `docs/adr/005-triage-handoffs.md` (new) — architecture, all bugs above with evidence and fixes | done |
| 105 | Verified live: all 5 routing rules × 3 (user's 4 example queries + a 5th router case), each checked against expected `routed_to` | done |
| 106 | Verified live: session memory carries across a handoff (turn 2, routed to a different specialist than turn 1, correctly recalled turn 1's content) | done |
| 107 | Verified live: `/ask`, `/compare`, `/chat`, `/refund` unaffected (regression) | done |
| 108 | CI smoke test (`tests/test_health.py` via `uv run --group dev python tests/test_health.py`) passes with `/triage` wired in | done |
| 109 | `handbook`: `assistant-widget.tsx` — General/Smart Triage toggle, separate session id + message history per mode (matching the backend's separate session DBs), "Routed to: X" caption under each Smart Triage reply | done |
| 110 | `handbook`: `tsc --noEmit` clean; dev server hot-reloaded with no compile errors; homepage still serves 200 | done |
| 111 | Docs updated: `CLAUDE.md`, `spec.md`, `README.md`, `tasks.md`, `progress.md` (ksor-worker) | in progress |
| 112 | Commit + push both repos                                               | pending |

## Refund human-approval gate — Domain 4 (this pass)

| # | Task | Status |
|---|---|---|
| 113 | `inngest` added (`uv add`, `uv.lock` regenerated); Inngest client defaults to dev mode unless `INNGEST_SIGNING_KEY` is set so the app still boots without new env vars | done |
| 114 | `refund_gate.py` (new): `refund-approval-gate` function (`step.run` notify → `step.wait_for_event` on `request_id`, 24h → 3 branches), `request_refund` tool, `audit_log.db` writer (idempotent) | done |
| 115 | `RefundSpecialist` given the `request_refund` tool + submission instructions; `remove_all_tools` handoff filter kept, no `tool_choice="required"` | done |
| 116 | `main.py` serves `/api/inngest`; `.env.example` gets `REFUND_GATE_THRESHOLD` (+ optional timeout) | done |
| 117 | Verified live (Inngest dev server): 6000 PKR request suspends with "Approval needed…" log; wrong-`request_id` decision does not wake it; `approved:true` → one `refund_issued`; `approved:false` → `refund_blocked`, no `refund_issued`; 10s timeout → `escalated_timeout` | done |
| 118 | `tests/test_refund_gate.py` + CI step; README "Human Gate" section; ADR 006; CLAUDE.md rule 8 / spec.md Non-goals amended | done |
| 119 | Verified live via `/triage` (real LLM + KSOR MCP): 6000 PKR → `RefundSpecialist` calls `request_refund`, replies "pending, not issued", no audit row; 1000 PKR → issued directly; approve/reject decision events then produce `refund_issued` / `refund_blocked`; missing amount → asks for it, no row; KSOR question still → `KSORWorker` | done |
| 120 | Commit + push | pending |

