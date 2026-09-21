# Progress — ksor-worker

## 2026-09-16 — Initial build

Built per plan.md: uv project init, deps (`openai-agents`, `python-dotenv`),
governance docs (CLAUDE.md, spec.md, plan.md, tasks.md,
docs/adr/001-use-openai-agents-sdk.md), and the three source files
(`common.py`, `worker.py`, `compare.py`).

**Verified:**
- `uv run python -c "import ksor_worker.worker, ksor_worker.compare"` —
  both modules import cleanly (correct absolute-import shape, matches
  `uv run python src/ksor_worker/worker.py` invocation).
- `worker.py`'s MCP connection path, run directly against the live
  `ksor serve` at `http://127.0.0.1:8080/mcp`: connected successfully and
  listed its tools — `['search', 'outline', 'read']`, matching what
  handbook's AGENTS.md documents as the KSOR gateway's default tool surface.

**Not yet verified (needs a real `OPENAI_API_KEY`, which no agent can
provide):**
- An actual grounded vs. ungrounded model answer. `.env` has not been
  created — only `.env.example` exists. Once a real key is in `.env`,
  run both scripts interactively:
  ```sh
  uv run python src/ksor_worker/worker.py
  uv run python src/ksor_worker/compare.py
  ```
  Ask the same in-scope question (e.g. "What is the Amazon affiliate
  program?") to both, then the same out-of-scope question, and compare the
  four answers as described in spec.md's verification section.

## 2026-09-16 — Live verification, bug found and fixed

Real `OPENAI_API_KEY` supplied and moved into `ksor-worker/.env`.

**Bug found:** `worker.py`'s first `search` call failed with
`MCPError: Request 'tools/call' timed out`. Root cause: the SDK's
`MCPServerStreamableHttp` defaults `client_session_timeout_seconds=5`, too
short for a real embedding-backed search (Gemini embed + pgvector query).
The SDK swallowed the timeout as a generic "MCP tool returned an error" tool
result, and the model answered from its own memory instead — silently
breaking the "KSOR-only" guarantee.

**Fix:** added `MCP_TIMEOUT_SECONDS = 30` to `common.py` and passed
`client_session_timeout_seconds=MCP_TIMEOUT_SECONDS` in `worker.py`.

**Re-verified after the fix:**
- `worker.py` on "What is the Amazon affiliate program?" — no error,
  answered with FTC-disclosure specifics matching a real indexed document
  (`how-to-write-product-reviews`), confirmed by calling the `search` tool
  directly and inspecting the raw hit.
- `worker.py` on "Who won the cricket world cup?" — correctly abstained:
  "outside the knowledge base's scope."
- `compare.py` on the same two questions (no MCP tools) — answered the
  affiliate question from generic pretrained knowledge (no document-specific
  detail), and merely *mimicked* a scope refusal on the cricket question
  without any real grounding check — the exact contrast the demo exists to
  show.

Both workers are verified working as specified.

## 2026-09-16 — compare.py prompt changed: general, unrestricted assistant

User asked to remove the KSOR restriction from `compare.py`'s system prompt —
it should be a general Amazon affiliate assistant, answering freely, no
scope limit, still no MCP tools.

**Change:** `compare.py` no longer imports `INSTRUCTIONS` from `common.py`.
It now defines its own local, unrestricted prompt. `worker.py` and
`common.py` are unchanged — `common.INSTRUCTIONS` is now understood as
worker.py's prompt specifically, not a shared one. `MODEL` stays shared from
`common.py` for both.

Updated `CLAUDE.md` (rules 1–2) and `spec.md` (Components, System prompts,
compare.py behavior) to match — the old "same prompt, tools are the only
variable" framing no longer describes the code.

**Re-verified:** `compare.py` on "What is the Amazon affiliate program?" —
answered freely with no scope disclaimer and no reference to any knowledge
base, as intended.

## 2026-09-16 — User re-test: false alarm, stale process

User tested `compare.py` with two questions ("Pakistan ka current prime
minister kaun hai" and the cookie-window question) and got a KSOR-style
refusal on the first one ("...Ibrahim Digital Solutions ki Amazon affiliate
knowledge base ke daira-e-kam se bahar hai") — looked like the unrestricted
prompt change hadn't taken effect.

**Investigated:** re-ran `compare.py` fresh with the exact same two
questions — answered both freely (Pakistan PM from pretrained knowledge with
a knowledge-cutoff caveat; cookie window generically), no refusal, no
knowledge-base reference. The current file is correct.

**Root cause:** not a code bug — the user's terminal was almost certainly
still running an interactive `compare.py` session started *before* the
prompt change. A running Python process doesn't reload edited source; only a
fresh `uv run` picks up the new `INSTRUCTIONS`.

**Resolution:** user restarted the script fresh and confirmed it now answers
correctly ("hogyaha bhai"). No code change needed — closing this out.

## 2026-09-16/17 — Briefly lived inside handbook's repo; Vercel auto-deploy failed there

This project was temporarily copied into `handbook/ksor-worker/` and pushed
to the `KSOR-HANDBOOK` GitHub repo (a now-reverted decision — see the next
entry). While there, a Vercel project auto-detected the folder and tried to
deploy it as a Python web app, failing with "No python entrypoint found" —
correct, since `worker.py`/`compare.py` were still CLI scripts (`input()`
loops) at that point, with no HTTP entrypoint at all. The Vercel project was
deleted from the dashboard once diagnosed. Lesson carried forward: this is
exactly the gap `main.py` (below) exists to close — the FastAPI harness is
this project's actual Vercel/Render/ACA-deployable entrypoint, whenever
that phase starts for real.

## 2026-09-17 — Repo split: ksor-worker gets its own GitHub repo

User's stated production plan (Vercel+Render or Azure Container Apps later)
requires `handbook` (Node/npm) and `ksor-worker` (Python/uv) to be genuinely
separate repositories — no shared repo, no copies drifting apart. Removed
`handbook/ksor-worker/` and its orphaned CI workflow from the `handbook`
repo (commit `b790e24`); `handbook`'s actual KSOR content
(`knowledge/`, `system/`) untouched. `~/ksor-worker`'s own git repo (local
only until now) had its branch renamed `master` → `main` to match.

Repo creation itself needs a manual step: no `gh` CLI is installed, and the
harness's credential-leakage guard refuses any of my tool calls containing
a raw GitHub token (hit directly this session) — same category as
`OPENAI_API_KEY`/`GEMINI_API_KEY`. The user creates the empty repo; I push
to it once given the URL.

## 2026-09-17 — FastAPI harness built

Per the user's detailed spec: `worker.py`/`compare.py` refactored from CLI
scripts into plain library functions (`run_grounded`/`run_ungrounded`), all
`input()` removed; `models.py` added (`AskRequest`/`AskResponse`); `main.py`
added at the project root with `GET /health`, `POST /ask`, `POST /compare`;
`common.py`'s `KSOR_MCP_URL` renamed to `MCP_URL` to match the new
`.env.example`. `fastapi`, `uvicorn[standard]`, `pydantic` added as real
dependencies (versions checked against PyPI at build time, not guessed);
`httpx` added as a `dev`-group-only dependency for CI's smoke test. The
stale `[project.scripts]` entry from the original `uv init` scaffold
(pointed at an unrelated `Hello from ksor-worker!` stub) was removed as dead
weight. `docs/adr/002-fastapi-harness.md` records why FastAPI over
Flask/Django. A new `.github/workflows/ci.yml` (this repo's own now, no path
filter needed) runs `uv sync --locked --group dev` then a real smoke test —
`tests/test_health.py`, using FastAPI's `TestClient` against `GET /health` —
rather than a bare import check, with zero secrets required.

**Bug found during verification:** the plan's error-handling design only
caught `mcp.shared.exceptions.MCPError` (the exception class behind the
5-second-timeout bug from the CLI-era build) and mapped it to `502`.
Testing `/ask` with `ksor serve` stopped surfaced a *different* exception —
`agents.AgentsException` (specifically `UserError`), raised by the OpenAI
Agents SDK itself when the MCP connection can't be established at all
(server unreachable, not just a slow tool call) — which fell through to the
generic `except Exception` branch and returned a misleading `500` instead of
`502`. **Fixed** by catching `(MCPError, AgentsException)` together in
`main.py`'s `/ask` handler, both mapped to `502` with the real cause in the
message; verified traced back to `agents/mcp/server.py`'s
`_user_error_for_http_error` before writing the fix, not guessed.

**Verified live, in order:**
- `grep -rn "input(" src/ main.py` — no matches.
- `uv run --group dev python tests/test_health.py` — passes.
- `GET /health` → `200 {"status":"ok"}`.
- `POST /ask` with `ksor serve` **stopped** → clean `502`, real cause named,
  no crash, no fabricated answer (confirms the fix above).
- `POST /compare` → `200`, free/ungrounded answer, no MCP dependency.
- `ksor serve` started (`npm run serve` in `handbook`) → `POST /ask` again →
  `200`, grounded answer, `worker_type: "grounded"`.

All of `main.py`'s error paths and both happy paths are now confirmed
working against the real KSOR MCP server, not just against mocks.

**Remaining:** push to the new standalone `ksor-worker` GitHub repo once the
user creates it and shares the URL, then confirm its CI goes green there.

## 2026-09-21 — 3 knowledge docs + refund agent + a real prompt-reliability bug

### Knowledge docs (in `handbook`, a separate repo)
Added `knowledge/product-sourcing.md`, `knowledge/product-listing.md`, and
`knowledge/refund-policy.md` — all `status: stable` (a `draft` is admitted
to no machine surface at all, so an agent's MCP `search` would never find
one). `npm run check` passed clean; `npx ksor build` admitted all three.

**Bug found and fixed (ingest, not code):** the first `ksor ingest --flip`
built generation 6 with the new docs embedded, but its own output was
missing the "pre-flip delta"/"FLIPPED active generation" confirmation lines
that a second, identical-looking ingest run *did* print — meaning the first
flip silently did not activate generation 6; the live server kept serving
generation 5 with no error at all. Confirmed by direct MCP `read`/`search`
calls returning "no document with slug" for all three new docs even after
a full `ksor serve` restart (ruled out an in-memory cache — the server's
own source resolves `active_generation` from the `corpora` table fresh per
query, not once at boot). A second `ksor ingest --flip` (generation 7)
printed the expected `FLIPPED active generation -> 7` and the added-slugs
list, and every document became readable/searchable immediately after.
Root cause of the first run's silent non-flip not fully identified: worth
watching for on future ingests — if a flip doesn't print a delta line, it
probably didn't activate.

### Refund agent
Added `src/ksor_worker/refund_agent.py` (`run_refund_agent`, `SQLiteSession`
memory), `RefundRequest`/`RefundResponse` in `models.py`, `POST /refund` in
`main.py`, `CORSMiddleware` (needed because `system/site` is a static
export with no live server to proxy through — the widget must call this
API directly from the browser), and a refund carve-out added to worker.py's
`INSTRUCTIONS`.

**Real bug found through testing, not assumed — the domain split's first
design didn't work:**

1. First attempt: prompt-only enforcement on both agents. Tested
   worker.py against "If a customer returns a product, what happens to my
   commission?" — it answered directly, using `refund-policy.md`'s own
   content, **despite an explicit instruction not to**. Not a fluke:
   confirmed by hand, and the transcript is unambiguous.
2. Second attempt: reworded to a front-loaded, exact-reply instruction
   ("check this FIRST, before searching"). This fixed worker.py's
   exclusion and refund_agent.py's off-domain decline — but broke
   refund_agent.py the OTHER way: it now declined an actual in-domain
   question ("How long is the commission holding period?") because the
   query didn't literally contain "refund" or "return."
3. Third attempt: broadened refund_agent.py's definition to explicitly
   include "downstream" effects (commission reversal, holding period,
   return windows) without requiring the literal words. Retested worker.py
   and refund_agent.py 3x each on 4 questions: worker.py's refund-decline
   held (3/3), but a NEW, unrelated false positive appeared — worker.py
   declined a plain sourcing question ("How do I source product images
   correctly?") 1 out of 3 times, with identical wording each time. This
   confirmed genuine non-determinism, not a deterministic misclassification.
4. Fourth attempt: reworded both prompts to a closed, enumerated 5-topic
   list (concrete, not the abstract "downstream" framing) and added
   `ModelSettings(temperature=0)` to both agents for lower-variance
   classification. Retested the same battery: worker.py's sourcing
   question now passed 3/3 — but its refund-decline **regressed to 0/3**,
   answering the same plainly-worded refund question directly every time,
   deterministically (temperature=0 made it consistently wrong instead of
   occasionally wrong).

**Conclusion drawn from this sequence, not guessed in advance:** prompt-only
enforcement of a hard "never answer X" rule is not reliable enough for
worker.py's direction on this model, even with several different phrasings
and temperature=0 — the model's learned pull toward using a strong,
directly-relevant search result outweighs an instruction not to use it. A
model-based fix was abandoned in favor of a deterministic one for that
specific direction.

**Final fix**: `is_refund_related()` — a plain keyword match ("refund",
"return", "cancel", "reversed", etc.) — added to `common.py`, checked in
`main.py`'s `/ask` handler **before `run_grounded` is ever called**. A
match short-circuits straight to the fixed `REFUND_DECLINE_MESSAGE`, so the
model is never given the chance to be talked out of it. Notably,
refund_agent.py's *reverse* direction (recognizing an in-domain question
that doesn't say "refund," like "how long until my commission is final?")
was retested under the same conditions and held reliably through the
prompt alone (3/3) — so no code-level backstop was added there; the two
directions ended up enforced differently on purpose, recorded in
`docs/adr/003-refund-agent-memory.md`.

**Final verification, 3x each, all passing:**
- `/ask` on a plain refund question → declines (keyword backstop).
- `/ask` on a plain sourcing question → answers normally.
- `/refund` on an off-domain question → declines (prompt).
- `/refund` on a non-literal in-domain question ("how long until my
  commission is final?") → answers correctly (prompt).
- `/refund` on a plain refund question → answers correctly.
- `/refund` memory: a follow-up ("And for electronics specifically?")
  correctly used context from the prior turn without it being restated.
- `/compare` unaffected by any of the above changes.

**Remaining for this pass:** the site widget (Part 3 of the plan) and
committing/pushing both repos.

## 2026-09-21 (continued) — Widget built in `handbook`, both repos committed

The widget itself lives in `handbook` (`system/site/components/refund-widget.tsx`),
not here — full detail in that project's own `progress.md`. This entry
covers what matters from `ksor-worker`'s side: `/refund`'s CORS setup
(`ALLOWED_ORIGINS`, added earlier this pass) was verified against the
*actual* cross-origin call the widget makes, not assumed —
`curl -X OPTIONS /refund` with `Origin: http://localhost:3000` and the
real preflight headers a browser sends returned `access-control-allow-origin:
http://localhost:3000` and the right allowed method/headers, confirming the
browser-based widget can actually reach this API before any UI code was
trusted to work.

**This pass, in full, end to end:**
1. 3 new `handbook` knowledge documents (product-sourcing, product-listing,
   refund-policy) — stable, approved, confirmed live and correctly ranked
   in search after catching and fixing a silent ingest-flip bug.
2. `refund_agent.py` with real `SQLiteSession` memory, verified across two
   turns of one conversation.
3. A worker.py/refund_agent.py domain split that went through 4 iterations
   before landing on a reliable design (prompt-only enforcement failed in
   both directions at different points; the final design is a deterministic
   keyword check for worker.py's exclusion plus a tested-reliable prompt for
   refund_agent.py's inclusion) — full sequence above and in
   `docs/adr/003-refund-agent-memory.md`.
4. The floating chat widget in `handbook`, CORS-verified end to end.
5. Both repos' `CLAUDE.md`/`AGENTS.md` and `progress.md` updated to match —
   `handbook`'s `AGENTS.md` now notes the ingest flip-confirmation check and
   the widget's dependency on this service as a third local-dev process.

**Push status, checked, not assumed:**
- This repo (`ksor-worker`): `9c1eaeb` (refund agent + domain-split fix) is
  committed but **not pushed** — this repo still has no GitHub remote (task
  24 on `tasks.md`, waiting on the user to create one).
- `handbook`: `c578f59`, `6fbb461`, and `c9a815e` were committed but had
  NOT actually been pushed either — `git fetch` + comparing `HEAD` against
  `origin/main` showed 3 unpushed commits, not zero. Pushed just now
  (`b790e24..c9a815e`), confirmed against `origin/main` afterward rather
  than assumed from the earlier push having worked.
