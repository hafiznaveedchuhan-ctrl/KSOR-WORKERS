# CLAUDE.md — ksor-worker

Read spec.md, plan.md, tasks.md, docs/adr/001-use-openai-agents-sdk.md, and
docs/adr/002-fastapi-harness.md before making any change here. This is its
own repository — separate from `handbook` (Node/npm) on purpose, no shared
repo, no copies. Never import from `handbook` or assume it's on disk.

1. Purpose: `main.py` (FastAPI) exposes `/ask` (grounded, KSOR MCP-connected,
   scoped strictly to the KSOR knowledge base) and `/compare` (no tools, a
   general Amazon affiliate assistant with no scope restriction, answering
   from its own knowledge) — a grounded-and-restricted vs
   ungrounded-and-unrestricted contrast. Both use the same `MODEL` from
   common.py.
2. `common.py` is the single source for `MODEL`, `MCP_URL`,
   `MCP_TIMEOUT_SECONDS`, and worker.py's `INSTRUCTIONS` (its KSOR-scoped
   prompt) — never duplicate any of them. compare.py deliberately keeps its
   own `INSTRUCTIONS` (general, unscoped) defined locally, not in
   common.py — do not merge it back into a shared constant without the user
   asking for that again.
3. `worker.py`/`compare.py` are library functions only
   (`run_grounded`/`run_ungrounded`) — **no `input()`, no `__main__` block,
   no standalone CLI mode.** `main.py` is the only entrypoint; test through
   its HTTP endpoints (`uvicorn` + `curl`/`/docs`), not by running these
   files directly.
4. `run_grounded` must never answer from the model's own memory when the
   KSOR tools return nothing relevant — the abstention text passes through
   `result.final_output` exactly as the tool call returns it, no rewriting.
   In `main.py`, an MCP failure (`MCPError` or `AgentsException`) is a
   `502`, never a fabricated `200` answer.
5. Never commit `.env` — it holds `OPENAI_API_KEY`. `.env.example` stays a
   bare placeholder plus `MCP_URL`'s default.
6. Python 3.12, managed with `uv` only — no pip/poetry/conda commands here.
   Dev-only deps (currently just `httpx`, for the CI smoke test) go in the
   `dev` dependency group, not the main dependency list.
7. No Dockerfile, no Azure/Render config, no database, no auth — all
   explicitly future phases (see spec.md's Non-goals). Don't add them
   speculatively.
8. After any change that completes or alters a task, update tasks.md and
   append a line to progress.md. Don't let either drift from the code.
