# The golden dataset — conventions and change protocol

`golden.jsonl` is the load-bearing artifact of the eval suite (Agent Factory book, Course Nine Concept 11):
one JSON `Case` per line, validated by `schema.py` and `validate.py`. **Treat a change here like an API change.**
A beautiful framework on a bad dataset measures the wrong thing with rigor.

## What a case is

`case_id`, `category`, `endpoint`, `language`, `difficulty`, `critical`, `turns[]` (>1 = one shared session),
`source{stable_id, quote}`, `origin`, `expected{...}`, `unacceptable[]`, `status`, `repeats`, `authored_by`,
`reviewed_by`, `added_at`. Field meanings are documented in `schema.py`.

## Rules (each maps to a failure mode the book names)

| Rule | Why |
|---|---|
| Failures first: every `hard` case, every `known_failing` case carries an `origin` pointing at a real event | Imagination Trap — imagined cases are decorative |
| >= 30% `hard` (enforced by `validate.py`) | Easy-Mode Bias — the failure that makes scores look better than production |
| A `grounded_qa` case must quote its source **verbatim** from `fixtures/kb_snapshot.json` | Ground truth must be checkable, not remembered |
| `blocked_until_stable` cases carry a source pointer but **no quote** | Draft text is unpublished by the owner; this repo is public |
| Ground truth is written by one author and **reviewed by the owner** (`reviewed_by`) before a baseline is recorded (`validate_dataset.py --require-reviewed`) | Single-Author Problem |
| Disagreements are written into `notes`, not papered over | Book: judgment-call ground truth needs consensus |
| Never edit `expected` to make a failing case pass. If the agent is right and the case is wrong, fix the case in its own reviewed change and say why in `notes` | The dataset is the contract |

## Statuses

- `active` — graded normally; counts toward the gate.
- `known_failing` — a documented, open bug. Expected to FAIL. Tracked separately; if it starts passing the runner reports
  `UNEXPECTED_PASS` so it gets promoted to `active` (that is the ratchet working).
- `blocked_until_stable` — the fact lives only in an unpublished draft. Correct behavior today is to abstain. When the owner approves the
  draft, `validate.py` warns "promote this case": replace it with a positive `grounded_qa` case that quotes the now-served text.

## Draft -> stable promotion (the three draft docs)

`what-is-amazon-affiliate` (commission table, cookie window, 180-day rule), `product-hunting-guide`, `content-strategy`.
After the owner approves them and `npm run refresh` confirms `FLIPPED active generation -> N`:
`uv run python scripts/build_kb_snapshot.py --knowledge-dir <handbook>/knowledge`, then convert the affected cases.

## Placeholders

`{uid}` in a query, `request_id` or audit `request_id` is replaced per run, so a row written by an earlier run can never
satisfy a check.

## Growing the set

Weekly: review failing/odd widget sessions (`general_sessions.db`, `triage_sessions.db`) and promote eval-worthy ones to cases
(book: the trace-to-eval ritual). Quarterly: re-read the whole set for staleness. The set is expected to grow to hundreds of cases by
promotion, not by a "dataset sprint".
