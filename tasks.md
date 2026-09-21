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
