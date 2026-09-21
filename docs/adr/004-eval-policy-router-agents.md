# ADR 004: Three infrastructure agents — eval, policy, router

## Status
Accepted

## Context
Three new agents were requested, each a cross-cutting layer over the
existing grounded-answer pattern rather than a new business domain (unlike
the refund agent, which needed new knowledge content — see ADR-003):

- `eval_agent.py` — judges whether an answer is actually supported by what
  was retrieved for it.
- `policy_agent.py` — detects and anonymizes sensitive data before it
  reaches KSOR or gets logged.
- `router_agent.py` — picks a cheaper or stronger model by query
  complexity.

## Decision: standalone CLI modules, not new FastAPI endpoints
Each is runnable directly — `uv run python -m ksor_worker.eval_agent`, etc.
— with an interactive `input()` loop, matching the exact run command
specified for each. This is a deliberate, explicit exception to
`CLAUDE.md`'s "no CLI mode" rule for `worker.py`/`compare.py`/
`refund_agent.py`: those are FastAPI-only library functions with no
`__main__` block, but these three were asked for as directly runnable
demo/testing tools, not as HTTP endpoints. No `/eval`, `/policy`, or
`/route` route was added to `main.py` — not asked for, and adding one
speculatively would be scope beyond the request.

## Decision: no new knowledge-base content
Asked whether the KSOR record's content should grow alongside these
agents. Judged **no** — all three are infrastructure/governance layers
operating on top of the *existing* record (whatever `worker.py` would
retrieve), not a new business domain needing its own documents the way
refunds did. Content about "how our eval/policy/router agent works" would
also sit outside `instance.md`'s declared Amazon-affiliate scope. Stated
plainly rather than padding the record with unnecessary documents just
because doing so was offered as an option.

## Decision: `eval_agent` reads the run's own tool-call trace, not a second search
`_extract_search_hits()` pulls `ToolCallOutputItem`s from the answering
run's `result.new_items` (the OpenAI Agents SDK's own documented mechanism
for inspecting what happened during a run — verified against the SDK's
docs before writing this) rather than calling KSOR's `search` tool a
second time with the same query. A second search could rank differently or
return different results than what the answering agent actually saw,
which would make the judge fact-check against the wrong evidence.

## Decision: all three reuse `common.INSTRUCTIONS`, and all three gate on `is_refund_related()` first
Each agent's underlying "answer from KSOR" step uses the exact same
`INSTRUCTIONS` as `worker.py`'s `/ask` (so their base grounded-answering
behavior is identical, not reinvented three more times), and each checks
`is_refund_related()` before building that agent at all — the same
deterministic gate `main.py`'s `/ask` uses (see ADR-003). This was not
optional: building `eval_agent.py` first exposed that reusing
`INSTRUCTIONS` without also reusing the gate reintroduces exactly the
unreliability ADR-003 already fixed for `/ask` — and, in the same
investigation, surfaced a **worse**, previously-undiscovered version of it
(a totally unrelated question triggering the refund decline), which led
to removing the refund clause from `INSTRUCTIONS` entirely rather than
just adding more backstops. See ADR-003's 2026-09-21 update for the full
account — it belongs there, not duplicated here, since it changed a
shared file all three of these agents (and `/ask`) depend on.

## Consequences
- A future fourth agent that reuses `common.INSTRUCTIONS` must also gate
  on `is_refund_related()` before running it, or it inherits an unhandled
  refund case with no redirect at all (not a false positive anymore, but a
  missed one).
- `eval_agent`'s judge call is a second, separate model call per query —
  roughly double the latency and cost of a plain `/ask`. Acceptable for a
  diagnostic/evaluation tool used to spot-check answers, not meant to sit
  behind a high-volume endpoint.
- `router_agent`'s classifier call also adds one extra round-trip before
  the real answer — the classification always runs on the cheap model
  regardless of what it decides for the answer itself, so this overhead is
  small and constant.
