# Progress — ksor-worker

## 2026-09-22 (later) — Live end-to-end confirmation with the user, both surfaces

After the build below, confirmed live with the user watching (not just
claimed): `POST /triage {"query": "KSOR kya hai"}` → `TriageAgent` →
handoff → `KSORWorker` → real Neon/pgvector search via `ksor serve` →
correct, grounded answer, `routed_to: "KSORWorker"`. Full pipeline proven
working end-to-end at the moment of testing.

Also surfaced live, again: `{"query": "mera refund kab aayega"}` routes
correctly to `RefundSpecialist` (`routed_to` correct) but the answer text
hit the already-documented pre-existing Roman-Urdu inconsistency in
`refund_agent.py`'s own domain check (declined instead of answering) —
shown to the user as-is, not hidden. Same known gap as ADR-005 records;
still not fixed here, still out of scope, still reproduces identically on
the unmodified `/refund` endpoint with no triage involved.

Gave the user 5 ready-made test queries (one per specialist) for the
standalone CLI (`uv run python -m ksor_worker.triage_agent`):
`"KSOR kya hai"` → KSORWorker; `"If a customer returns a product, what
happens to my commission?"` → RefundSpecialist; `"mera phone number
0300-1234567 hai, help karo"` → PolicySpecialist; `"Can you check if this
is grounded: product hunting means finding trending products"` →
EvalSpecialist; `"Which AI model should I use for a complex multi-step
reasoning task?"` → RouterSpecialist. Confirmed with the user: running
`triage_agent.py` alone is sufficient for testing — no need to separately
invoke `worker.py`/`refund_agent.py`/`eval_agent.py`/`policy_agent.py`/
`router_agent.py`, since `triage_agent.py` hands off to equivalents of all
of them internally (the CLI tools remain useful standalone for their own,
slightly more thorough behavior — e.g. `eval_agent.py`'s separate judge
call vs `EvalSpecialist`'s single-call self-check — but are not required
to exercise the same ground through triage).

Clarified for the record, since it came up repeatedly: `/chat` (General)
and `/triage` (Smart Triage) both answer from the same KSOR record via
Neon — the difference is NOT "general questions vs KSOR questions."
`/chat` is one agent with no handoff and no specialist behavior at all
(no PII redaction, no groundedness self-check, no model advice — it just
answers everything itself). `/triage` is the only path that hands off,
and each specialist it can reach has genuinely different behavior for its
category, not merely a different label.

## 2026-09-22 — Triage agent built: real SDK handoffs, `/triage`, widget toggle

The pending task from the 2026-09-21 handoff (below) is done. Built
`triage_agent.py`: one `TriageAgent` hands off to 5 specialists
(`KSORWorker`, `RefundSpecialist` — reused `INSTRUCTIONS` verbatim;
`PolicySpecialist`/`EvalSpecialist`/`RouterSpecialist` — new, single-call,
built only for this file, since a handoff target must be a single `Agent`
and the CLI tools with those names are 2-step pipelines) via the real
OpenAI Agents SDK `handoffs` mechanism — `routed_to` in the response is
`result.last_agent.name`, never hardcoded. New `POST /triage` in
`main.py`, own `triage_sessions.db` session store, own `_cli()` (`uv run
python -m ksor_worker.triage_agent`). Full architecture and every bug
below: `docs/adr/005-triage-handoffs.md`.

**Three real bugs found and fixed live** (not by inspection — found by
running the actual thing repeatedly and reading what came back):
1. The SDK's default handoff passes a specialist the triage agent's own
   `transfer_to_x` tool-call and its JSON output as prior context — that
   clutter derailed `RefundSpecialist`'s strict "does this match exactly
   these 5 topics" check, reproducibly 3/3 for a plain in-domain question.
   Fixed: every specialist wrapped in `handoff(agent,
   input_filter=handoff_filters.remove_all_tools)` instead of passed bare.
2. `EvalSpecialist`'s self-assessment invented non-spec verdict words
   (`ABSTAINED`, `UNVERIFIED`) instead of the 3 fixed tokens the prompt
   named — fixed by stating the 3-token constraint negatively as well as
   positively ("never any other word, never X, Y, Z").
3. `RouterSpecialist` declined a valid model-selection question that
   already named its own complexity inline ("...for a complex multi-step
   reasoning task?") about 2/3 of the time, reading it as "too vague."
   Fixed by clarifying the query itself is the task, however phrased.

**A fourth, subtler bug, found only through heavy live retesting**: in a
multi-turn triage session, a PRIOR specialist's decline (not its tool-call
noise — its plain text, e.g. "please ask the general assistant instead")
could prime `KSORWorker`'s NEXT turn to skip the KSOR search tool entirely
and self-decline a completely unrelated, clearly in-scope question.
Reproduced with a bare `Agent`+`Runner.run()` call given that exact
3-message history and zero triage/handoff machinery involved — so this is
a property of `common.INSTRUCTIONS` + a preceding refusal-flavored turn,
not the handoff code. Only `/triage` can ever produce this shape of
history (`/chat` never generates a decline-flavored turn at all, since it
skips the refund gate by design), so the fix is scoped to `triage_agent.py`
only: `tool_choice="required"` on `KSORWorker` specifically — a prompt-only
attempt (telling the agent to disregard a prior unrelated decline) was
tried first and did not reliably work. Verified 3/3 clean at realistic
(a few seconds apart) turn spacing after the fix.

**Two pre-existing issues found during this testing, NOT fixed here (out
of scope — they predate this session's work and reproduce identically on
the unmodified, already-shipped endpoints with no triage involved)**:
- `refund_agent.py`'s domain check is inconsistent on Roman Urdu phrasing
  ("mera refund kab aayega" sometimes declines as if out-of-domain,
  sometimes answers correctly) — reproduced on the plain `/refund`
  endpoint directly.
- `common.INSTRUCTIONS`-based agents occasionally answer an in-scope-
  sounding question from general/pretrained knowledge instead of
  abstaining when the record genuinely has no matching content — caught
  when `/refund` gave detailed Amazon UI cancellation steps that
  `knowledge/refund-policy.md` (grepped directly) does not contain at all.
  Confirmed as a real grounding leak, not a one-off: a correct, honest
  "I couldn't find specific information" answer for the same query was
  the more common, and more correct, result on retest.

Both are flagged for whoever next touches `common.INSTRUCTIONS`/
`refund_agent.py` — fixing either means editing a shared prompt several
endpoints depend on, which is exactly the kind of change ADR-003 already
warns can make things worse without careful, isolated re-verification, so
it was deliberately left alone rather than patched inside this task.

Also found, separately, and NOT a code bug: rapid, zero-delay back-to-back
test calls (the shape a test script sends, not a real user) surfaced
intermittent `openai.APITimeoutError`s and MCP tool errors in this
sandbox, reproduced even for single-turn, no-history, no-session queries.
Environmental request-layer flakiness under synthetic burst load — already
handled correctly by `main.py`'s existing 502/500 fail-closed behavior.

`handbook`'s `assistant-widget.tsx`: added a General/Smart Triage toggle.
Each mode keeps its own session id (localStorage) and its own message
history, matching the backend's own session separation. Smart Triage mode
shows "Routed to: X" under each reply, sourced directly from the API
response, never inferred client-side. `tsc --noEmit` clean; dev server
hot-reloaded with no compile errors. No real browser automation tool was
available this session to click through it in an actual browser — flagged
honestly rather than claimed as verified; the underlying `/chat` and
`/triage` calls it makes were both extensively live-tested via curl.

## 🔴 SESSION HANDOFF (2026-09-21) — superseded, task above is now done

Context window was filling up mid-task; the user is about to `/clear` and
start a fresh session. **This section is written so a brand-new AI session
with zero conversation memory can pick up exactly where this one stopped —
read this, then `spec.md`/`CLAUDE.md`/`docs/adr/`, before touching code.**

### What exists right now (all pushed, CI green, fully working)

**Two repos, deliberately separate** (npm vs uv, no shared repo):
- `handbook` — the KSOR knowledge record (Next.js/Fumadocs site + `ksor
serve` MCP server). GitHub: `hafiznaveedchuhan-ctrl/KSOR-HANDBOOK`.
- `ksor-worker` (this repo) — Python/uv, OpenAI Agents SDK. GitHub:
  `hafiznaveedchuhan-ctrl/KSOR-WORKERS`.

**`ksor-worker` currently has 4 live HTTP endpoints** (`main.py`,
`uv run uvicorn main:app --port 8000`):
- `POST /ask` — grounded, KSOR-scoped, **excludes** refund questions
  (redirects) — `worker.py`.
- `POST /compare` — no tools, answers anything, ungrounded — `compare.py`.
- `POST /refund` — grounded, refund/returns **only**, has memory
  (`SQLiteSession`, `refund_sessions.db`) — `refund_agent.py`.
- `POST /chat` — grounded, **no topic split at all** (refunds included),
  has memory (`general_sessions.db`) — `general_agent.py`. **This is what
  the `handbook` site's widget (`assistant-widget.tsx`) actually calls.**

**Plus 3 standalone CLI-only tools** (not HTTP, `uv run python -m
ksor_worker.<name>`): `eval_agent.py` (answer + groundedness judge),
`policy_agent.py` (PII detection/anonymization), `router_agent.py`
(gpt-4o-mini vs gpt-4o routing).

**`common.py`'s `INSTRUCTIONS`** (the base KSOR-scoped prompt several
agents reuse) has **NO refund-related clause** — that was tried, caused a
real bug (declined unrelated questions), removed. `is_refund_related()` +
`REFUND_DECLINE_MESSAGE` in `common.py` are the *sole*, code-level
enforcement of `/ask`'s refund exclusion. Full story:
`docs/adr/003-refund-agent-memory.md`. **Never re-add a refund clause to
`common.INSTRUCTIONS`.**

**Real bugs found and fixed this session** (don't reintroduce them):
1. SDK's MCP tool-call timeout defaults to 5s, too short — fixed with
   `MCP_TIMEOUT_SECONDS = 30` in `common.py`.
2. Prompt-only refund-exclusion was unreliable in *both* directions
   (answered refund questions directly; separately, declined totally
   unrelated questions) — fixed by removing the prompt clause entirely and
   using `is_refund_related()` as the sole gate.
3. `refund_agent` fabricated a citation URL not in any source, 3/3
   reproducible — fixed with an explicit "never invent a URL" instruction
   in the shared prompt.
4. Abstention wording was inconsistent (sometimes read as a temporary
   outage) — fixed with an exact-wording instruction.
5. `ksor build`/`ingest --flip` can silently NOT activate a new generation
   (no error, just no delta/confirmation line printed) — if a flip doesn't
   print `FLIPPED active generation -> N`, assume it didn't take and
   re-run.

### 🎯 THE PENDING TASK — not started yet, full plan already written

**User wants a triage/orchestration agent** — one entry point that
receives every query and hands it off to the right specialist, using the
**real OpenAI Agents SDK `handoffs` mechanism** (`Agent(handoffs=[...])`,
`Runner.run()` → `result.final_output` + `result.last_agent.name`), not a
fake if/else pretending to be one.

**The full, approved implementation plan is written at**
`/home/naveed/.claude/plans/create-a-new-knowledge-parsed-pearl.md` — a
fresh session should read that file in full before starting. Summary:

- New `src/ksor_worker/triage_agent.py`: 5 specialist `Agent` objects
  (`KSORWorker`, `RefundSpecialist`, `PolicySpecialist`, `EvalSpecialist`,
  `RouterSpecialist`) wired into one `TriageAgent` via `handoffs=[...]`.
  `run_triage_agent(query, session_id) -> (answer, routed_to)`, own
  `SQLiteSession` (`triage_sessions.db`).
- **Key finding already made, don't re-derive it**: a handoff target must
  be a single `Agent` instance. `eval_agent.py`/`policy_agent.py`/
  `router_agent.py` are 2-step Python pipelines, not single agents, so
  they **cannot** be handed off to as-is. Resolved by building NEW,
  single-call versions of those three roles *inside* `triage_agent.py`
  (self-critique instead of a separate judge; redact-then-answer in one
  call; advice-only for model routing) — the original 3 standalone CLI
  tools stay **completely untouched**. This is recorded as
  `docs/adr/005-triage-handoffs.md` (not yet written — part of the plan).
- New `POST /triage` in `main.py`, `TriageRequest`/`TriageResponse` in
  `models.py` (includes `routed_to`).
- `handbook` widget gets a small General/Smart-Triage toggle, showing
  "Routed to: X" under each reply in triage mode.
- A judge-style verification pass is required before calling this done:
  the user's 4 example queries (refund/general/PII/hallucination-check)
  each checked against their expected `routed_to`, repeated 2-3× each for
  consistency (temperature=0 alone hasn't been a full guarantee this
  session — verify, don't assume), plus memory across a handoff, plus
  regression-checking `/ask`/`/refund`/`/chat`/`/compare` still work.

**Nothing from this plan has been built yet** — no `triage_agent.py`
exists, no `/triage` route, no widget toggle. A fresh session's first real
action should be: re-enter Plan Mode is not required (the plan is already
approved — `ExitPlanMode` was accepted), just start Phase 1 of that
plan's file list, testing live as you go, the same rigor as every fix
above (curl-tested before claiming anything works, not assumed).

### Local dev — 3 processes, likely all stopped if this is a fresh session

```sh
# in handbook/
npm run dev      # site :3000
npm run serve    # ksor serve MCP :8080  (needs .env: KSOR_AUTH=disabled-local etc.)
# in ksor-worker/
uv run uvicorn main:app --port 8000
```

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

## 2026-09-21 (continued) — `ksor-worker` gets its own GitHub repo, pushed

User created an empty-with-README repo,
`github.com/hafiznaveedchuhan-ctrl/KSOR-WORKERS`, and had already set it
as this repo's `origin` and merged its initial README commit (`8824144`)
into local history before this session touched it again. `git push`
was a clean fast-forward (`8824144..71d8972`) — no conflict, nothing for
me to resolve. Confirmed via the GitHub API afterward, not assumed: both
`CI` runs (`8824144`, `71d8972`) show `completed`/`success`.

## 2026-09-21 (continued) — 3 more agents: eval, policy, router

Built exactly as specified: `eval_agent.py` (`run_eval_agent`) answers via
KSOR then judges the answer's groundedness against the exact source chunks
its own run retrieved; `policy_agent.py` (`run_policy_agent`) detects and
anonymizes PII before the query reaches KSOR; `router_agent.py`
(`run_router_agent`) classifies a query as simple/complex and answers with
`gpt-4o-mini`/`gpt-4o` accordingly. All three are standalone CLI tools
(`uv run python -m ksor_worker.<name>`, `input()` loop, `exit`/`quit`) —
a deliberate, explicit exception to the "no CLI mode" rule that applies to
`worker.py`/`compare.py`/`refund_agent.py` (see `CLAUDE.md` rule 4a),
since these three were asked for as directly runnable tools, not HTTP
endpoints.

**Judged, not assumed: does the KSOR knowledge base need new content for
these agents?** No. All three are infrastructure/governance layers over
the *existing* record (whatever `worker.py` would retrieve) — not a new
business domain the way refunds were. Adding "how our eval/policy/router
agent works" documents would also sit outside `instance.md`'s declared
Amazon-affiliate scope. Recorded plainly rather than padding the record
with documents nothing needs, per `CLAUDE.md`'s new rule 9.

**Two real bugs found through testing — one in the new judge, one
pre-existing in `/ask` itself, exposed by reusing `common.INSTRUCTIONS`:**

1. **Judge bug (new code):** asked `eval_agent` an out-of-scope question
   ("Who won the cricket world cup?"), the answering agent correctly
   abstained ("outside the knowledge base's scope"), but the judge marked
   this honest abstention `HALLUCINATED` — backwards: declining without
   evidence is the *correct* outcome, not a fabrication. **Fixed** by
   telling the judge explicitly that a clean abstention (no other claims
   asserted) is `GROUNDED`, never `HALLUCINATED`. Retested: correct.

2. **Pre-existing `/ask` bug, not previously caught:** building
   `eval_agent.py`'s answering step by reusing `common.INSTRUCTIONS`
   (exactly as `worker.py`'s `run_grounded` does) surfaced that the SAME
   unrelated cricket question got answered with the *refund* decline
   message — "That's a refund/return question — please ask the refund
   assistant instead." Confirmed this was not new-code-specific: hitting
   `/ask` directly with the identical query reproduced it, **3–4 times out
   of 4** on repeated calls, even though `is_refund_related()` (checked
   separately) correctly returned `False` both times. So the deterministic
   keyword gate was working exactly as designed — the *model itself*,
   given a query that passed the gate, was independently choosing the
   refund-shaped reply for a totally unrelated question. Root cause:
   `common.INSTRUCTIONS` held two similar-looking "if X, reply with
   escape-hatch Y" instructions (the refund carve-out, then the general
   out-of-scope abstention) back to back, and the model was conflating
   "I shouldn't answer this" in general with "this specifically matches
   the refund carve-out."

   **Fix, more drastic than a second backstop:** removed the refund
   carve-out clause from `common.INSTRUCTIONS` **entirely**. It now says
   only "answer strictly from KSOR, abstain honestly if not covered" — no
   mention of refunds at all. `is_refund_related()` is now the *sole*
   mechanism enforcing the refund exclusion wherever `common.INSTRUCTIONS`
   is used: `main.py`'s `/ask`, and — applied consistently as part of this
   same fix — `eval_agent.py`, `policy_agent.py` (checked on the
   *anonymized* query), and `router_agent.py` (checked before routing, so
   a decline needs no model selection). `refund_agent.py`'s own reverse
   direction (recognizing an in-domain question that doesn't say "refund")
   was re-verified separately and still holds through its own prompt
   alone — untouched by this fix, since it's a different prompt with no
   shared clause to remove.

**Full regression battery re-run after the fix (all passing, 3–4 repeats
each): `/ask` on the unrelated question (4/4 correct general abstention,
was 0–1/4 before), `/ask` on a refund question (3/3 decline),
`/ask` on a sourcing question (3/3 answer), `/refund` on a sourcing
question (3/3 decline), `/refund` on a non-literal in-domain question
(3/3 answer), `/refund` on a refund question (3/3 answer), `/compare`
and `/refund` memory both re-confirmed unaffected.**

`docs/adr/003-refund-agent-memory.md` updated with this further finding
(it's a continuation of that ADR's own subject, not a new one);
`docs/adr/004-eval-policy-router-agents.md` added for these three agents'
own design decisions. `CLAUDE.md` and `spec.md` updated to match —
`common.INSTRUCTIONS`'s file-level comment now records why it must never
regain a refund clause.

**Verified end-to-end, once the fix landed:** `eval_agent` on a real
in-scope question — `GROUNDED`, correct matched citations; `policy_agent`
on a query containing an email — detected, anonymized to `[EMAIL]`,
answered correctly; `router_agent` on a simple question — `gpt-4o-mini`
selected; on a deliberately multi-step comparative question —
`gpt-4o` selected.

## 2026-09-21 (continued) — Strict audit, ruthless not a self-report

User asked for a strict, evidence-driven audit against everything built
this session, across both repos, including the widget/UI, scored out of
100 and driven to a genuine 100 — not inflated, not assumed from memory of
earlier runs in this same conversation. All 3 local services (site,
`ksor serve`, this API) had been stopped since the last session ended, so
every live claim below was re-proven fresh.

**Honest limitation stated up front, not hidden:** no real browser
automation tool is actually connected this session (checked via tool
search — only `WebFetch` exists, and it explicitly cannot reach
`localhost`). The widget was verified as rigorously as possible without
one: the *actual rendered SSR HTML* from a live `curl` of the homepage
(not just the component source), a live `OPTIONS` *and* `POST` CORS
round-trip matching exactly what the browser would send, and a
line-by-line check that the rendered button carries this codebase's own
real tokens (`bg-primary text-primary-foreground`, `--radius`-driven
`rounded-full`, `motion-safe:` animations) rather than invented ones. That
is strong wiring-and-rendering evidence; it is not the same as watching it
render and clicking it, and the audit says so rather than claiming full
marks it can't back up.

**Two real, reproducible bugs found via fresh live testing (not present
in — or not caught by — the earlier verification passes):**

1. **`refund_agent` fabricated a citation URL.** Asked "What happens to
   my commission if a customer returns a product?", it appended "For more
   details, you can refer to the [refund policy](https://www.amazon.com)"
   — **3 times out of 3**, deterministically. Checked `refund-policy.md`
   directly: no such URL appears anywhere in it; the document's only
   citation is the Associates Operating Agreement URL. This is a genuine
   grounding violation the project's whole design exists to prevent, and
   it slipped past every earlier test because none of them happened to
   trigger this specific closing-sentence pattern. **Fixed**: added
   "never include a URL unless it appears verbatim in the retrieved
   content" to `refund_agent.py`'s instructions and to the shared
   `common.INSTRUCTIONS` (so `/ask` and the other agents reusing it are
   covered too). Re-verified clean, 3/3, after a restart.
2. **Abstention wording inconsistency.** Of 4 fresh repeats of the
   previously-fixed "cricket world cup" case, 3 gave the clean scope
   abstention, but 1 said "I'm unable to access the information... at the
   moment" — technically still a correct non-answer (no fabricated fact,
   no refund misfire), but phrased like a temporary outage rather than a
   permanent scope boundary, which is a materially different signal to a
   real user. **Fixed**: `common.INSTRUCTIONS` now names the exact
   wording to use and explicitly forbids "unable to access"/"at the
   moment" phrasing. Re-verified 4/4 identical and correct after the fix.

**One real documentation gap found:** `README.md` — the first thing
anyone reads — still described only the original 2-worker CLI demo. No
mention of `/refund`, `refund_agent.py`, `eval_agent.py`,
`policy_agent.py`, or `router_agent.py` anywhere, despite all five being
fully built, tested, and previously documented in `spec.md`/`CLAUDE.md`/
ADRs. Also had a stray leftover `# KSOR-WORKERS` heading dangling at the
very end (a merge artifact from the GitHub-initialized README). **Fixed**:
`README.md` fully rewritten — all three endpoints and all three CLI
agents documented with real examples, the "real bugs" section rewritten
to include this pass's two findings with evidence, stray heading removed.

**Everything else the audit checked came back clean, with fresh evidence,
no fix needed:**
- Full 19-case regression battery + the 2 new adversarial cases, re-run
  live after the fixes — all pass.
- `refund_agent` memory re-confirmed across turns, post-fix.
- `eval_agent`, `policy_agent`, `router_agent` each re-tested live —
  correct groundedness verdicts (including the earlier abstention-is-
  GROUNDED fix holding), correct PII detection/anonymization, correct
  model routing.
- `git log -p --all` grepped for secret patterns across this repo's
  *entire* history (not just the working tree) — clean. `.env` confirmed
  never committed at any point in history, in either repo.
- CORS confirmed live to genuinely reject an untrusted origin (no
  `access-control-allow-origin` header at all) — not a disguised
  wildcard.
- Both repos' CI green on current `HEAD`, checked live via the GitHub
  API; both working trees clean; `handbook` confirmed free of the old
  `ksor-worker` copy.
- All 3 new `handbook` knowledge documents re-confirmed live-readable and
  correctly top-ranked in a fresh MCP search — not assumed from the
  earlier ingest-bug fix.

**Final score: 98/100** — category breakdown, each with the evidence
above: Knowledge content 15/15, Agent correctness & domain split 20/20
(after the 2 fixes), Widget & UI 18/20, API/backend correctness 10/10,
Documentation & governance 15/15 (after the README fix), Security &
hygiene 10/10, CI/CD & repo hygiene 10/10.

**The only deduction (Widget & UI, −2) is an environment constraint, not
a code defect**: no browser-automation tool is connected in this session
(confirmed by tool search, not assumed) and none is installable without
adding new tooling to the sandbox (checked directly — no `chromium`,
`playwright`, or `puppeteer` present or fetchable). The widget is proven
correct at the wiring/rendering level — actual server-rendered HTML from
a live `curl` of the homepage showing the real `bg-primary`/`--radius`/
`motion-safe:` tokens, plus a live CORS `OPTIONS` and `POST` round-trip
matching exactly what a browser sends — but never watched actually render
and get clicked.

**Offered the user the option to attempt installing Playwright to close
this gap; they explicitly chose to keep the score at 98/100** rather than
add a new, network-dependent dependency to the sandbox for a 2-point
gain, since the underlying evidence is already strong and they can
confirm visually themselves in under a minute.

**Commits this pass**: `cc8c681` (the 2 bug fixes + README rewrite),
`9dff20e` (tasks.md), both pushed and CI-green on `KSOR-WORKERS`.
Corresponding `handbook` commit: `442ee92`.

## 2026-09-21 (continued) — `/chat`: one general assistant for the widget

User asked for the widget to answer "har agent ki taraf se" (from every
agent) — clarified via a direct question, since that phrase could mean a
selector, a side-by-side multi-agent comparison, or one unified assistant.
**User chose: one general assistant, not limited to refunds, no
selector/comparison UI.**

**Built `general_agent.py`** (`run_general_agent`): reuses
`common.INSTRUCTIONS` exactly as `/ask` does — which, since the refund
clause was already removed from that prompt earlier this session, means
this agent has no topic restriction at all without needing a new prompt
written from scratch. The one deliberate difference from `/ask`: its
`main.py` handler does **not** apply `is_refund_related()` — that gate
exists specifically to enforce `/ask`'s exclusion, and applying it here
would just recreate the split this endpoint exists to not have. Own
`SQLiteSession` (`general_sessions.db`), kept separate from
`refund_sessions.db` so the two endpoints never share a conversation's
history even if a caller reuses the same `session_id` against both.

**Verified live, all fresh:**
- `/chat` on a plainly refund-worded question — answers directly, no
  redirect (`worker_type: "general"`).
- `/chat` memory carries across a **topic switch** within one session — a
  refund question, then (same `session_id`) a sourcing question,
  understood in context both times.
- `/chat` on a plainly unrelated question — still abstains cleanly
  ("outside the Ibrahim Digital Solutions knowledge base's scope"), no
  refund misfire, no fabrication.
- `/chat` inherits the anti-hallucination fix from earlier this pass — no
  fabricated citation link, 3/3.
- `/ask`, `/refund`, `/compare` re-tested — all unaffected by the new
  endpoint.

**`handbook` side**: `refund-widget.tsx` renamed to `assistant-widget.tsx`
(component `RefundWidget` → `AssistantWidget`) — a genuine accuracy fix,
not just a preference, since the file name would otherwise actively
mislead about what the component now does. Fetch target switched from
`/refund` to `/chat`; header copy from "Refund Assistant" to "KSOR
Assistant"; placeholder and aria-labels generalized. `tsc --noEmit` clean;
the live dev server's rendered HTML confirmed the new `aria-label="Open
assistant"` on the launcher button; a fresh CORS preflight against `/chat`
specifically (not just `/refund`) returned the correct
`access-control-allow-origin`.

Docs updated to match: `CLAUDE.md` (new rule 3a: `/chat` deliberately
skips the gate; rule 4/6/8 extended to cover `general_agent.py`/
`general_sessions.db`), `spec.md` (`/chat` section, `ChatRequest`/
`ChatResponse`, updated Goal/Components), `README.md` (four-endpoint
table, `/chat` examples, project layout), and `handbook/AGENTS.md` (the
widget note now names `/chat` specifically, not `/ask`+`/refund`).
