# ADR 007: Golden dataset and eval-driven development for the AI workers

## Status
Accepted

## Context
The agents (`/ask`, `/refund`, `/chat`, `/triage` and its 5 specialists) and the refund approval gate (ADR 006) were verified
by hand: a handful of queries, three repeats, by eye. That does not scale, and it cannot protect a change from silently undoing an
old fix. The Agent Factory book (Course Nine "Eval-Driven Development"; "Trusting the Checker") is explicit that the **golden
dataset** is the load-bearing artifact — frameworks are tooling — and that its cases must come from real failures, not imagination.

## Decision: `evals/`, its own uv project
`evals/` holds `datasets/golden.jsonl` (the artifact), a validator/schema, a paced live runner, deterministic graders, an LLM-judge
layer (DeepEval + Ragas), a baseline + regression gate, a judge-calibration protocol and a mutation check.

**A separate uv project (`evals/pyproject.toml`, own `uv.lock`) instead of a dev group.** Adding `deepeval` + `ragas` to the app's
lock re-resolved `openai` 3.14.1 -> 3.3.0 for *production* (measured; a transitive cap via the langchain packages). Isolating the eval
dependencies keeps the app's pins untouched; `evals` installs `ksor-worker` as an editable path dependency. CLAUDE.md rule 7 ("uv only,
dev deps in a group") is followed in spirit: uv is the only tool, and eval-only dependencies stay out of the app.
`langchain-community<0.4` is pinned there because `ragas 0.4.3` imports a module (`chat_models.vertexai`) that 0.4 removed.

## Decision: the dataset follows the book's rules
- **Failures first.** All documented real bugs (ADRs 003/005/006, progress.md) are seeded; open ones are `known_failing`
  and alert (`UNEXPECTED_PASS`) when they start passing. 14 further cases were mined from the owner's real widget sessions
  (typos, ALL-CAPS, code-mixing and "PLZ REPLY IN TWO LINE" are kept: that is the true input distribution).
- **>= 30% hard cases** (enforced), every hard case carries an `origin`, difficulty-stratified reporting.
- **Grounded answers quote the served corpus verbatim**, validated against `fixtures/kb_snapshot.json` (so CI needs no `../handbook`).
- **Draft-only facts are not copied here.** This repo is public and the owner has not approved those drafts. They are
  `blocked_until_stable` cases: source pointer only, no quote, expected behavior = abstain (the record cannot ground them, so the model must
  not answer from general knowledge). When the owner approves a draft, the validator warns and the case is converted to a positive one.
- **Critical categories require every repeat** (gate, safety, exact strings, routing); language-quality categories use a per-case
  majority and a category pass-rate bar. Infra errors (5xx, timeouts) are `ERROR`, never `FAIL` or `PASS`. See `evals/docs/critical-metrics.md`.
- **Serial, paced, repeated.** Rapid back-to-back calls were already known to time out and to trigger the prime-decline bug (ADR 005).

## Decision: deterministic graders are the gate; the LLM judge is advisory until calibrated
Exact strings, routing, URL allowlist, verdict tokens, audit-log rows, length limits and latency are checked without an LLM.
DeepEval (relevancy, faithfulness, a custom scope/honesty GEval) and Ragas (context relevance/recall, faithfulness, answer
correctness on chunks fetched straight from the MCP `search` tool) sit on top, with a judge model (`gpt-4o`) that differs from the agents'
(`gpt-4o-mini`). Their bars start advisory: `scripts/calibrate_judge.py` implements the book's "grade the grader" protocol (20 deliberately
mixed items, owner grades blind, four-cell table, false-pass count) and gating starts only after the owner has done it.

## What the first runs found (why this exists)
1. **A real regression in ADR 006's own change**, caught by `tr-refund-when-will-i-get`: the extra `REFUND_SUBMISSION_INSTRUCTIONS`
   text made `RefundSpecialist` decline "When will I get my refund?" 6/6 (baseline before the gate: 6/6 answered). A/B by variant:
   the addendum was the cause, not the `request_refund` tool (addendum removed, tool kept: 6/6; addendum kept, tool removed: 0/6). A
   shorter neutral addendum still broke it (1/4). Fix: no addendum; the tool's docstring alone gives 4/4 on status, large-pending,
   small-issued and missing-amount behaviors. The hand verification in ADR 006 had checked routing, not the answer.
2. **The record and the worker disagree on the out-of-scope wording.** `instance.md` prescribes an exact sentence; the worker's prompt says
   "wording close to" a different one. Abstention is therefore graded by rubric, not exact match. Flagged for the owner.
3. **The retrieval abstention gate is off** (`instance.md` has no calibrated `retrieval:` block), so today abstention rests on prompts only.
4. **`ragas 0.4.3` does not import** with the latest `langchain-community` (pinned in `evals/`).

5. **Two real grounding leaks, reproduced on the owner's own queries:** "How do I cancel an order?" recites Amazon's "Your Orders -> Cancel
   Items" steps 2 of 5 times; after a refund turn, "what's a good way to find trending products?" gets generic advice 3/3 although the served
   record has none (the guidance is only in an unpublished draft). Both are tracked `known_failing`.
6. **The deterministic layer alone is not enough:** in the calibration sample the agent answered "What is the 180-day rule?" by calling it the
   commission holding period, and the keyword check passed it. Hence the judge layer and the owner's blind grading.
7. **Judge bring-up findings:** `HallucinationMetric` (DeepEval 4.x, higher = better) gave a correct answer 0.2 and an invented one 0.0 with
   multi-chunk retrieval context, so it is not used; `FaithfulnessMetric`, a scope/honesty `GEval`, and Ragas faithfulness / answer correctness
   (which separated retrieval from grounding correctly) are. A `known_failing` case only counts as fixed when every repeat passes.

## Results (first baseline, PROVISIONAL)
82 cases x 3 repeats: 77 PASS, 0 FAIL, 0 ERROR; +13 real-traffic cases (2 real leaks found, 1 of my own cases corrected). Baseline: every category
100% of graded active cases; 5 known_failing and 3 blocked_until_stable tracked apart. Mutation check: 4/4 offline and 3/3 live breakages caught,
with clean controls. GitHub CI (offline evals included) green.

## Consequences / limits
- Evals catch the failure modes we thought to test; novel questions, tone and long-conversation drift are outside them. Coverage grows by the
  weekly failure-promotion ritual (`datasets/README.md`), not by a dataset sprint.
- Live suites cannot run in GitHub Actions (they need the key and the local MCP server); CI runs the offline part only.
- Every case starts `reviewed_by: null`; a baseline recorded before the owner reviews the set is marked PROVISIONAL.
- `known_failing` and `blocked_until_stable` cases never count toward a gate.
