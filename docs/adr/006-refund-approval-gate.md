# ADR 006: Human approval gate for large refunds — Inngest `wait_for_event` + SQLite audit log

## Status
Accepted

## Context
A refund at or above a threshold (default 5000 PKR, `REFUND_GATE_THRESHOLD`)
must not be issued until a human approves it, and every outcome must be
auditable. Nothing in this repo issued refunds before this ADR —
`RefundSpecialist` only answered policy questions from the KSOR record — and
there was no Inngest wiring and no audit table. All three are new.

## Decision: durable wait via Inngest, not a polling loop or an open request
`refund_gate.py` defines one Inngest function, `refund-approval-gate`,
triggered by `refund/approval.requested`:

1. `step.run("notify")` — console log `Approval needed for request {id}: …`
2. `step.wait_for_event("await-approval", event="refund/approval.decided",
   if_exp="event.data.request_id == async.data.request_id", timeout=24h)` —
   the run is suspended by the Inngest runtime; this process holds nothing
   open and survives restarts. Matching is on `request_id`, never customer id.
3. Branch, each in its own `step.run`:
   - `approved` is literally `true` → audit row `refund_issued`
   - anything else → audit row `refund_blocked`, plus a customer-facing
     rejection message (in the audit detail and the function's return value)
   - `None` (timeout) → audit row `escalated_timeout`

The approval check is **fail-closed**: only a JSON `true` approves; a
missing key, `"true"` (string) or `1` blocks.

`RefundSpecialist` gets a `request_refund(request_id, amount)` function tool
(`refund_gate.request_refund`). Below the threshold it writes `refund_issued`
directly (`auto-approved below threshold`); at or above it, it sends the
requested-event and tells the customer the refund is **pending and not yet
issued**. If the event cannot be sent (Inngest unreachable) the tool says the
refund was NOT issued rather than pretending — the gate never fails open.

## Decision: SQLite `audit_log.db`, refund issuance simulated
Same convention as the existing `*_sessions.db` files: stdlib `sqlite3`,
gitignored (`*.db`). Table `audit_log(id, request_id, action, amount, detail,
ts)` with `UNIQUE (request_id, action)` and `INSERT OR IGNORE`, so an Inngest
step retry is a no-op rather than a duplicate row. There is no payment
system in this repo, so "issue refund" writes the audit row and logs; wiring
a real payment call would go inside the `issue-refund` step.

This is a deliberate, narrow exception to CLAUDE.md rule 8 / spec.md
Non-goals ("no database"), like the `SQLiteSession` exception before it:
one append-only audit table, nothing else. No user database, no auth.

## Decision: Inngest defaults to dev mode unless `INNGEST_SIGNING_KEY` is set
The SDK refuses to build its `/api/inngest` handler with neither `INNGEST_DEV`
nor a signing key, which would have stopped the entire app (`/health`, `/ask`,
`/chat` included) from booting for anyone without the new env var — and
broken the CI smoke test. `is_production` is therefore derived from
`INNGEST_SIGNING_KEY`. Production sets that and `INNGEST_EVENT_KEY`.

## Consequences / known limits
- The customer's chat turn ends at "pending approval". There is no push
  channel back into that closed turn, so the rejection message lives in the
  audit row and the function output, not in the chat.
- Approval decisions come from a terminal / the Inngest dev UI. A browser
  "Approve" button would need CORS (`allow_methods`/`allow_headers`) changes.
- Nothing authenticates who sent `refund/approval.decided`; in dev anyone who
  can reach the Inngest event API can approve. Production must protect the
  event key and put a real approver identity in the event data.
- `REFUND_GATE_TIMEOUT_SECONDS` (default 86400) exists so the timeout branch
  is testable without waiting 24 hours.
