# CLAUDE.md — ksor-worker

Read spec.md, plan.md, tasks.md, docs/adr/001-use-openai-agents-sdk.md,
docs/adr/002-fastapi-harness.md, and docs/adr/003-refund-agent-memory.md
before making any change here. This is its own repository — separate from
`handbook` (Node/npm) on purpose, no shared repo, no copies. Never import
from `handbook` or assume it's on disk.

1. Purpose: `main.py` (FastAPI) exposes three domain-scoped agents —
   `/ask` (grounded, KSOR MCP-connected, general Amazon-affiliate scope,
   **excluding** refunds/returns), `/compare` (no tools, a general
   assistant with no scope restriction, for contrast), and `/refund`
   (grounded, KSOR MCP-connected, scoped **only** to refunds/returns/
   cancellations, with real multi-turn memory). All three use the same
   `MODEL` from common.py.
2. `common.py` is the single source for `MODEL`, `MCP_URL`,
   `MCP_TIMEOUT_SECONDS`, `ALLOWED_ORIGINS`, worker.py's `INSTRUCTIONS`
   (its KSOR-scoped prompt, refund carve-out included), and the
   `is_refund_related()`/`REFUND_DECLINE_MESSAGE` pair that backstops that
   carve-out in code — never duplicate any of them. compare.py and
   refund_agent.py each keep their own `INSTRUCTIONS` defined locally, not
   in common.py — do not merge either back into a shared constant without
   the user asking for that again.
3. **The worker.py/refund_agent.py domain split is enforced two ways, on
   purpose — keep both.** `main.py`'s `/ask` handler checks
   `is_refund_related()` in code, before the agent ever runs, and
   short-circuits to `REFUND_DECLINE_MESSAGE` on a match — prompt-only
   enforcement of this direction was tested and found unreliable (see
   `progress.md`). refund_agent.py's reverse direction (recognizing an
   in-domain question that doesn't literally say "refund," like "how long
   until my commission is final?") was tested and found to work through
   its prompt alone, so it has no code-level backstop — don't add one
   speculatively, and don't remove `/ask`'s keyword check to "simplify" it.
4. `worker.py`/`compare.py`/`refund_agent.py` are library functions only
   (`run_grounded`/`run_ungrounded`/`run_refund_agent`) — **no `input()`,
   no `__main__` block, no standalone CLI mode.** `main.py` is the only
   entrypoint; test through its HTTP endpoints (`uvicorn` +
   `curl`/`/docs`), not by running these files directly.
5. `run_grounded`/`run_refund_agent` must never answer from the model's own
   memory when the KSOR tools return nothing relevant — the abstention text
   passes through `result.final_output` exactly as the tool call returns
   it, no rewriting. In `main.py`, an MCP failure (`MCPError` or
   `AgentsException`) is a `502`, never a fabricated `200` answer.
6. Never commit `.env` — it holds `OPENAI_API_KEY`. `.env.example` stays a
   bare placeholder plus `MCP_URL`'s default. `refund_sessions.db` (the
   refund agent's `SQLiteSession` store) is runtime state, not source —
   gitignored, never committed.
7. Python 3.12, managed with `uv` only — no pip/poetry/conda commands here.
   Dev-only deps (currently just `httpx`, for the CI smoke test) go in the
   `dev` dependency group, not the main dependency list.
8. **Session/conversation memory is deliberately in scope for
   refund_agent.py specifically** (the SDK's own `SQLiteSession`) — this is
   an intentional exception to "no database," not a reversal of it. No
   Dockerfile, no Azure/Render config, no user database, no auth — all
   still explicitly future phases (see spec.md's Non-goals). Don't add
   those speculatively.
9. After any change that completes or alters a task, update tasks.md and
   append a line to progress.md. Don't let either drift from the code.
