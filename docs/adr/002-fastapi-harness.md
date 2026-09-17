# ADR 002: FastAPI as the web harness

## Status
Accepted

## Context
`worker.py`/`compare.py` were CLI scripts (`input()` loops). The project
now needs an HTTP surface — `/ask` and `/compare` — as the base for a later
deploy to Vercel+Render or Azure Container Apps.

## Decision
Use FastAPI, run by `uvicorn`, with `run_grounded`/`run_ungrounded` as plain
`async def` functions the two endpoints call directly.

## Reasons
- **Async-native, matching what's already here.** `Runner.run(agent, query)`
  from the OpenAI Agents SDK is itself `async`. FastAPI's handlers are
  `async def` and `await` it directly — no sync-to-async bridge, no thread
  pool workaround.
- **Validation built in.** `AskRequest`/`AskResponse` are Pydantic models;
  FastAPI validates the request body and serializes the response from them
  with no extra code.
- **OpenAPI for free.** `/docs` and `/openapi.json` are generated from the
  same type hints — useful immediately for manual testing, and later for
  any client generation against a deployed instance.

## Alternatives rejected
- **Flask** — sync-first. Calling an `async def` agent function from a sync
  Flask view means either blocking the request thread on `asyncio.run()` per
  request (wasteful, and breaks under Flask's default WSGI worker model) or
  adopting Flask's separate async extension — extra complexity for no
  benefit over a framework that's async from the start.
- **Django** — full ORM, admin, templating, sessions — none of which this
  two-endpoint service uses. Rule 7/8 in `CLAUDE.md` explicitly defers
  database and auth to a future phase; Django's weight buys nothing here.

## Consequences
- `uvicorn` is the server process — this is what a container image (for
  ACA) or a Render web service would run directly (`uv run uvicorn
main:app --host 0.0.0.0 --port $PORT`), with no framework migration needed
  between "runs locally" and "runs in production."
- The MCP connection is opened per-request inside `run_grounded()`, not
  shared across requests via FastAPI's lifespan. That's simpler and avoids
  concurrency edge cases for a first version. A shared, lifespan-scoped
  connection (opened once at app startup, reused across requests) is a
  legitimate later optimization if per-request connection overhead ever
  matters in practice — not built now, consistent with this project's
  "future phase" framing for anything not needed yet.
