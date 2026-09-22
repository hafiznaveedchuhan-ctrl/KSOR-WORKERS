# ADR 005: Triage agent — real SDK handoffs, one `/triage` endpoint

## Status
Accepted

## Context
The user wanted a true orchestration layer: one agent that receives every
query first and **hands off** to the right specialist, using the OpenAI
Agents SDK's own `handoffs` mechanism (`Agent(handoffs=[...])`,
`Runner.run()` → `result.final_output` + `result.last_agent.name`) — not a
keyword `if/else` dispatcher pretending to be one.

## Decision: a handoff target must be a real `Agent` instance — three specialists needed new, simpler prompts
Confirmed against the SDK before writing any code: a handoff target must be
a single `Agent` object. Three of the five roles the user named —
`eval_agent.py`, `policy_agent.py`, `router_agent.py` — are Python
**pipelines** (two sequential LLM calls each: detect→answer, answer→judge,
classify→answer), not single `Agent` objects, so the SDK's handoff
mechanism has no way to hand off to them directly. Two honest options: (a)
build new, single-call `Agent` versions of those three roles for the
triage system specifically, accepting a real behavioral simplification
(self-critique instead of a separate judge call, redact-then-answer in one
call instead of two, advice-only instead of actually running the routed
model), or (b) fake the handoff with manual `if/else` dispatch to the
existing async functions — exactly the non-SDK approach the user
explicitly didn't want. **Chose (a)**. The three original CLI tools
(`eval_agent.py`/`policy_agent.py`/`router_agent.py`) are untouched — the
triage system's `PolicySpecialist`/`EvalSpecialist`/`RouterSpecialist` in
`triage_agent.py` are new, separate `Agent` objects with their own
instructions, not calls into those files. `KSORWorker` and
`RefundSpecialist` needed no such adaptation — `worker.py`'s and
`refund_agent.py`'s `INSTRUCTIONS` were already single-agent prompts, reused
verbatim.

## Bug found live: the default handoff leaks the triage agent's own tool-call noise into the specialist's context
`handoffs=[ksor_worker, refund_specialist, ...]` (bare `Agent` objects, the
SDK's default) made `RefundSpecialist` **decline** "When will I get my
refund?" — a plain, unambiguous match for its own first listed topic —
reproducibly 3/3, while the exact same `INSTRUCTIONS` answered it correctly
3/3 when called directly through the existing `/refund` endpoint (no
triage involved). A debug script dumping `result.new_items` showed why:
by default, a handed-off-to agent receives the **entire prior run
history**, including the triage agent's own `transfer_to_refundspecialist`
function-call item and its `{"assistant": "RefundSpecialist"}` JSON output
— clutter that has nothing to do with the user's question, but sits right
in front of it in the specialist's view of the conversation, and derailed
`RefundSpecialist`'s "FIRST, before doing anything else, check if this
matches exactly these 5 topics" instruction.

**Fix**: wrap every specialist in
`handoff(agent, input_filter=agents.extensions.handoff_filters.remove_all_tools)`
instead of passing the bare `Agent`. This strips tool-call/tool-output
items from what the specialist sees, leaving just the clean conversation
(user + prior assistant text). Re-verified live: 3/3 correct after the
fix, same query, same session pattern.

## Bug found live: a prior specialist's DECLINE text (not its tool-call noise) can prime the next specialist to skip searching entirely
Even after the `remove_all_tools` fix above, one scenario remained
inconsistent: a session where turn 1 was handled by `RefundSpecialist` and
declined ("please ask the general assistant instead"), followed by turn 2
on a completely different, clearly in-scope topic routed to `KSORWorker`.
`KSORWorker` would sometimes skip the KSOR search tool entirely and output
`INSTRUCTIONS`'s abstention line directly — reproduced with a bare
`Agent`+`Runner.run()` call given that exact 3-message history and no
triage/handoff machinery involved at all, so this is a property of
`common.INSTRUCTIONS` + a preceding refusal-flavored turn, not of the
handoff mechanism. This can only surface through `/triage` — `/chat`
(the other multi-turn, `common.INSTRUCTIONS`-based endpoint) never
produces a decline-flavored turn in the first place, since it skips the
refund gate entirely — so this is a triage-specific risk, not a reason to
touch the shared `common.INSTRUCTIONS` used by `/ask`/`/chat` (which
CLAUDE.md already gates carefully — see ADR-003).

**Fix, scoped to `KSORWorker` inside `triage_agent.py` only**:
`ModelSettings(temperature=0, tool_choice="required")`. `KSORWorker` is
only ever reached once `TriageAgent` has already decided the query is an
answerable general-knowledge question, so it has no legitimate reason to
answer without searching first — forcing the tool call removes the
opportunity for the model to pattern-match into a decline without ever
consulting the record. A prompt-only attempt at this fix (adding a note to
`INSTRUCTIONS` telling the agent to disregard a prior specialist's
unrelated decline) was tried first and did **not** work reliably;
`tool_choice="required"` did. Not applied to `RefundSpecialist`: its
own "FIRST, before doing anything else — including before searching —
check if this matches exactly 5 topics" decline is a deliberate,
by-design no-search path (see `refund_agent.py`), and forcing a tool call
there would fight that design rather than fix anything.

**Verified live, properly paced** (real user turns are never
millisecond-spaced): 3/3 clean at 4s between turns, both before this fix
(baseline: 0/6 clean rapid-fire) and after (3/3 clean paced,
`tool_choice="required"` in place). Rapid, zero-delay back-to-back calls
(as a test script, not a real user, would send) surfaced a **separate**,
unrelated issue — intermittent `openai.APITimeoutError`s and MCP tool
errors under that load in this sandbox, reproduced even for single-turn,
no-history queries with no session involved at all. That is environmental
request-layer flakiness under synthetic burst load, not a defect in this
feature; `main.py` already fails closed on it (502/500, never a fabricated
answer), consistent with the rest of this project's design (see CLAUDE.md
rule 5).

## Bug found live: a self-assessing specialist invents its own vocabulary unless the prompt forbids it explicitly
`EvalSpecialist`'s first prompt draft named the three valid verdict tokens
(GROUNDED / PARTIALLY_GROUNDED / HALLUCINATED) but only *described* the
abstention case as falling under GROUNDED, rather than forbidding other
words outright. Live testing surfaced the model inventing `ABSTAINED` and
`UNVERIFIED` as verdicts on different runs of the same clean-abstention
case — never wrong in substance, but breaking the fixed three-token
contract a caller (or the widget) might match against. **Fix**: the prompt
now states the constraint negatively as well as positively — "MUST be
exactly one of these three tokens... and never any other word (never
ABSTAINED, UNVERIFIED, UNKNOWN, N/A...)" — re-verified 3/3 consistent
after the change, across both an abstention case and a genuine
hallucination case.

## Bug found live: `RouterSpecialist` treated an embedded task description as "too vague" ~2/3 of the time
The query "Which AI model should I use for a complex multi-step reasoning
task?" already names its own complexity inline, but the first prompt draft
(closely following `router_agent.py`'s "given a description of a task,
classify it") led the specialist to read that as a request for a
*separate* task description it hadn't been given, and decline 2 times out
of 3. **Fix**: the prompt now states explicitly that the query itself is
the task, whether phrased as a bare description or as a question that
already describes the task inline, and that a query naming its own
complexity in words ("complex", "multi-step", etc.) is not too vague to
classify. Re-verified 3/3 consistent after the change.

## Known, pre-existing gap found during verification — not fixed here, out of scope
`RefundSpecialist` (via `refund_agent.py`'s own `INSTRUCTIONS`, reused
verbatim) declines a plain Roman Urdu refund-timing question — "mera
refund kab aayega" — reproducibly 3/3, both through the new `/triage`
route and through the pre-existing, already-shipped `/refund` endpoint
directly. This is **not** a regression from this change: it is identical,
unmodified behavior in code that already existed before this session's
task, confirmed by testing `/refund` directly with no triage layer
involved at all. The English phrasing of the same question ("When will I
get my refund?") answers correctly. `routed_to` is correct either way
(`RefundSpecialist`), which is what this feature's own routing contract
promises — the answer-content gap is `refund_agent.py`'s prompt, a
separate concern for whoever owns that file next.

## Consequences
- Every future specialist added to `TriageAgent.handoffs` must be wrapped
  in `handoff(agent, input_filter=handoff_filters.remove_all_tools)`, not
  passed bare — passing a bare `Agent` silently reintroduces the
  tool-call-leakage bug above.
- `PolicySpecialist`/`EvalSpecialist`/`RouterSpecialist` are a **narrower**
  reimplementation of their CLI namesakes (no separate judge call, no
  detect-then-anonymize two-step, no actual model switch) — a deliberate,
  accepted trade-off for being real single-Agent handoff targets. Don't
  "simplify" by trying to reuse `run_eval_agent`/`run_policy_agent`/
  `run_router_agent` as handoff targets directly; they cannot be (see
  above).
- `triage_sessions.db` is a third, separate `SQLiteSession` store — a
  `/triage` conversation and a `/chat` or `/refund` conversation for the
  same `session_id` never share history, same reasoning as the existing
  two.
