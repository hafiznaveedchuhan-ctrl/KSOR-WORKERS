# Plan — ksor-worker (FastAPI harness)

1. **Project setup** — `fastapi`, `uvicorn[standard]`, `pydantic` added to
   `pyproject.toml` via `uv add` (versions checked against PyPI, not
   guessed); `httpx` added as a `dev` group dependency for the CI smoke
   test; stale `[project.scripts]` scaffold entry removed.
2. **`models.py`** — `AskRequest`, `AskResponse` Pydantic schemas.
3. **`worker.py` refactor** — `input()` loop removed; exports
   `async def run_grounded(query: str) -> str`, opening its own MCP
   connection per call.
4. **`compare.py` refactor** — same shape, `async def run_ungrounded`,
   keeps its own unrestricted `INSTRUCTIONS` (unchanged from the prior
   session's explicit request).
5. **`common.py` update** — `KSOR_MCP_URL` renamed to `MCP_URL`, everywhere.
6. **`main.py`** — FastAPI app: `/health`, `/ask`, `/compare`; distinct
   `502` (MCP unavailable) vs `500` (anything else) error handling.
7. **Docs** — `spec.md`, `README.md`, `CLAUDE.md`, `tasks.md`,
   `docs/adr/002-fastapi-harness.md` updated to match the new shape;
   `progress.md` gets a new dated entry, not a rewrite.
8. **Local verification** — all 3 endpoints hit for real, including the
   MCP-down `502` path and the MCP-up grounded happy path; then push to the
   project's own new GitHub repo once created.
