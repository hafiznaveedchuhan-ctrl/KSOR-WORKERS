# ADR 003: Refund agent memory, and how the domain split is actually enforced

## Status
Accepted

## Context
The refund agent needed two things worker.py/compare.py didn't: real
multi-turn conversation memory, and a hard boundary keeping it from
answering anything outside refunds/returns/cancellations (and the mirror
requirement on worker.py, excluding those topics).

## Decision: memory via the SDK's own `SQLiteSession`
Use `agents.SQLiteSession(session_id, "refund_sessions.db")`, passed as
`session=` to `Runner.run`, constructed fresh per request rather than held
open across requests.

### Reasons
- **It's the documented, first-party mechanism** (verified against the
  OpenAI Agents SDK's own docs before writing this ADR, not assumed). The
  runner automatically prepends prior turns before a run and stores new
  ones after — no hand-rolled history list to keep in sync.
- **Per-request construction, not a shared session pool**, for the same
  reason `worker.py` opens its own MCP connection per call rather than
  sharing one across requests (see ADR-002): it's cheap, and it sidesteps
  concurrency questions about one session object serving overlapping
  requests. `SQLiteSession` reads/writes the same on-disk rows for a given
  `session_id` regardless of which request object touches it, so this
  costs nothing in correctness.
- **SQLite, not in-memory**: survives a server restart, unlike a plain
  dict keyed by session_id would. Still explicitly not a "real" database —
  runtime state, gitignored, not source.

## Decision: the domain split is enforced two different ways, not one
This is the part worth recording, because it wasn't the first design and
the first one didn't work.

### What was tried first, and failed
Both `worker.py` (exclude refunds) and `refund_agent.py` (include only
refunds) were given prompt instructions alone. Tested against a plainly
refund-worded question ("If a customer returns a product, what happens to
my commission?"), `worker.py` answered it directly — using the
newly-indexed `refund-policy.md` content — on 3 out of 3 repeated calls,
despite an explicit, front-loaded "check this first" instruction. A
follow-up attempt with a more specific, enumerated instruction plus
`temperature=0` improved but did not fix this, and introduced a new
failure: it started declining an unrelated sourcing question 1 out of 3
times. Full sequence in `progress.md` — this is not a hypothetical risk,
it's what was actually observed.

### The fix
`worker.py`'s exclusion is enforced **in code**: `is_refund_related()` in
`common.py` (a keyword match — "refund," "return," "cancel," "reversed,"
etc.) runs in `main.py`'s `/ask` handler *before the agent is invoked at
all*. A match short-circuits straight to a fixed decline message — no
model call, so it can't be talked out of it.

`refund_agent.py`'s *reverse* direction — recognizing an in-domain
question that doesn't literally say "refund" (e.g. "how long until my
commission is final?") — was tested the same way and found to work
reliably through the prompt alone (3/3 correct on both a keyword-bearing
and a non-keyword-bearing in-domain question, and 3/3 correct declining an
off-domain one). No code-level backstop was added there, since one wasn't
needed and adding one speculatively would just be more surface to keep in
sync with the prompt for no measured benefit.

## Consequences
- The two agents' domain boundary is asymmetric in *how* it's enforced
  (code alone for worker.py's exclusion — see the update below — prompt
  alone for refund_agent.py's inclusion) even though the *boundary itself*
  is meant to be symmetric. This is intentional and should not be "cleaned
  up" into one uniform mechanism without re-testing both directions the
  way this ADR did — the asymmetry exists because the two directions were
  tested and behaved differently, not by accident.
- A keyword list is not a semantic classifier — a refund-adjacent question
  phrased without any of the listed words is not redirected to the refund
  agent; it gets answered normally by worker.py from KSOR content instead
  (which, for `refund-policy.md` specifically, is not itself a wrong
  answer — just not the dedicated, memory-carrying refund agent). This is
  an accepted, documented residual gap, not a claim of perfect
  enforcement.
- `temperature=0` was kept on both `worker.py` and `refund_agent.py` after
  this investigation — a lower-variance classifier is a reasonable default
  regardless of what backstops exist around it.

## Update (2026-09-21): the prompt-level clause was removed entirely, not just backstopped

Building `eval_agent.py` (a groundedness-evaluation agent reusing
`worker.py`'s exact `INSTRUCTIONS`) surfaced a worse failure the keyword
backstop alone hadn't caught: asked a **plainly unrelated** question with
zero refund keywords ("Who won the cricket world cup?"), `worker.py`
answered with the refund decline message **3 times out of 4** — not the
correct general "outside this knowledge base's scope" abstention.
Confirmed the same failure existed in `/ask` directly (not just
`eval_agent`), independent of `is_refund_related()`, which correctly
returned `False` for that query both times — the keyword gate was working
exactly as designed; the *agent itself*, given the pass-through query, was
choosing the refund-shaped reply anyway.

**Root cause**: the prompt held two separate "if X, reply with escape-hatch
Y" instructions back to back (the refund carve-out, then the general
out-of-scope abstention) — the model was conflating the two, reaching for
whichever escape-hatch template it read first regardless of which one
actually matched.

**Fix**: removed the refund-carve-out clause from `INSTRUCTIONS` entirely.
It now says only "answer from KSOR, abstain honestly if not covered" — no
mention of refunds at all. `is_refund_related()` (checked in `main.py`'s
`/ask`, and in `eval_agent.py`/`policy_agent.py`/`router_agent.py` before
they build an agent with these same `INSTRUCTIONS`) is now the **sole**
mechanism enforcing worker.py's refund exclusion, not a backstop alongside
a prompt instruction. Retested the full battery — the unrelated question
now abstains correctly 4/4, and every previously-passing case (refund
decline, sourcing answer, refund_agent's own fuzzy in-domain detection)
still passes.

This sharpens the residual-gap note above: it is no longer "the prompt
sometimes fails to catch a refund-adjacent phrasing" — there is no prompt
mechanism for that direction anymore, on purpose, because it was actively
harmful (a false positive on unrelated content) rather than merely
imperfect (a false negative on edge-case phrasing). A false negative here
is an acceptable trade against a false positive that breaks the agent for
arbitrary unrelated questions.
