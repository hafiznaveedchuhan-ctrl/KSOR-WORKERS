"""Human-approval gate for refunds — see docs/adr/006-refund-approval-gate.md.

`request_refund` is the tool RefundSpecialist calls. Below the threshold it
issues (simulated) directly; at or above it, it fires an Inngest event and
returns immediately with "pending". The durable part lives in
`refund_approval_gate`: it suspends on `step.wait_for_event` (no polling, no
open HTTP request) until a human sends `refund/approval.decided`, or 24h pass.
Every outcome is one row in audit_log.db.
"""

import datetime
import os
import sqlite3

import inngest
from agents import function_tool

# Imported for its side effect: common.py calls load_dotenv(), which the env
# reads below (REFUND_GATE_*, INNGEST_SIGNING_KEY) depend on.
from ksor_worker import common  # noqa: F401

# Runtime state, not source — see .gitignore (*.db).
AUDIT_DB = "audit_log.db"

REQUESTED_EVENT = "refund/approval.requested"
DECIDED_EVENT = "refund/approval.decided"

DEFAULT_THRESHOLD_PKR = 5000.0
DEFAULT_TIMEOUT_SECONDS = 24 * 60 * 60

REJECTION_MESSAGE = (
    "Your refund request was reviewed and could not be approved. "
    "Please contact support if you believe this is a mistake."
)

# Dev mode (local Inngest dev server) unless a signing key is configured.
# Without this default the SDK refuses to build the /api/inngest handler when
# no INNGEST_DEV/INNGEST_SIGNING_KEY is set, which would stop the whole app —
# /health, /ask, /chat — from booting. Production sets INNGEST_SIGNING_KEY
# and INNGEST_EVENT_KEY and gets cloud mode.
client = inngest.Inngest(
    app_id="ksor-worker",
    is_production=bool(os.environ.get("INNGEST_SIGNING_KEY")),
)


def refund_gate_threshold() -> float:
    # Read at call time, not import time, so a changed .env value or a test
    # override takes effect without re-importing the module.
    return float(os.environ.get("REFUND_GATE_THRESHOLD", DEFAULT_THRESHOLD_PKR))


def gate_timeout() -> datetime.timedelta:
    seconds = float(
        os.environ.get("REFUND_GATE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    )
    return datetime.timedelta(seconds=seconds)


def write_audit(request_id: str, action: str, amount: float, detail: str) -> bool:
    """Append one audit row. UNIQUE(request_id, action) + INSERT OR IGNORE
    makes a retried Inngest step a no-op instead of a duplicate row. Returns
    True if a row was written."""
    with sqlite3.connect(AUDIT_DB) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS audit_log ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " request_id TEXT NOT NULL,"
            " action TEXT NOT NULL,"
            " amount REAL NOT NULL,"
            " detail TEXT NOT NULL,"
            " ts TEXT NOT NULL,"
            " UNIQUE (request_id, action))"
        )
        cursor = conn.execute(
            "INSERT OR IGNORE INTO audit_log (request_id, action, amount, detail, ts)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                request_id,
                action,
                amount,
                detail,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )
        return cursor.rowcount == 1


@client.create_function(
    fn_id="refund-approval-gate",
    trigger=inngest.TriggerEvent(event=REQUESTED_EVENT),
    # A duplicate requested-event for the same request_id must not start a
    # second run waiting on the same decision.
    idempotency="event.data.request_id",
)
async def refund_approval_gate(ctx: inngest.Context) -> dict[str, object]:
    request_id = str(ctx.event.data["request_id"])
    amount = float(ctx.event.data["amount"])

    async def notify() -> None:
        print(
            f"Approval needed for request {request_id}: amount {amount:g} PKR "
            f"— waiting for a {DECIDED_EVENT} event",
            flush=True,
        )

    await ctx.step.run("notify", notify)

    decision = await ctx.step.wait_for_event(
        "await-approval",
        event=DECIDED_EVENT,
        # `event` is the requested-event that started this run, `async` is the
        # decided-event being matched. Keyed on request_id, never customer_id.
        if_exp="event.data.request_id == async.data.request_id",
        timeout=gate_timeout(),
    )

    if decision is None:

        async def escalate() -> None:
            write_audit(
                request_id, "escalated_timeout", amount, "no decision before timeout"
            )
            print(
                f"ESCALATED request {request_id}: no approval decision "
                f"within {gate_timeout()}",
                flush=True,
            )

        await ctx.step.run("escalate-timeout", escalate)
        return {"request_id": request_id, "outcome": "escalated_timeout"}

    # Fail closed: only a literal JSON `true` approves.
    if decision.data.get("approved") is True:

        async def issue() -> None:
            write_audit(request_id, "refund_issued", amount, "approved by human")
            print(f"Refund ISSUED for request {request_id}: {amount:g} PKR", flush=True)

        await ctx.step.run("issue-refund", issue)
        return {"request_id": request_id, "outcome": "refund_issued"}

    async def block() -> None:
        write_audit(request_id, "refund_blocked", amount, REJECTION_MESSAGE)
        print(f"Refund BLOCKED for request {request_id}", flush=True)

    await ctx.step.run("block-refund", block)
    return {
        "request_id": request_id,
        "outcome": "refund_blocked",
        "customer_message": REJECTION_MESSAGE,
    }


async def submit_refund(request_id: str, amount: float) -> str:
    if amount <= 0:
        return "Invalid refund amount: it must be greater than zero."

    if amount < refund_gate_threshold():
        write_audit(request_id, "refund_issued", amount, "auto-approved below threshold")
        return f"Refund of {amount:g} PKR for request {request_id} has been issued."

    try:
        await client.send(
            inngest.Event(
                name=REQUESTED_EVENT,
                data={"request_id": request_id, "amount": amount, "currency": "PKR"},
            )
        )
    except Exception as exc:
        return (
            f"Could not start the approval process for request {request_id} "
            f"({exc}). The refund has NOT been issued."
        )
    return (
        f"Refund request {request_id} for {amount:g} PKR needs human approval and is "
        "now pending. It has NOT been issued yet."
    )


@function_tool
async def request_refund(request_id: str, amount: float) -> str:
    """Submit a refund for processing. Call only when the customer has given
    both a request id and a refund amount in PKR.

    Args:
        request_id: The customer's refund request id, exactly as they gave it.
        amount: The refund amount in PKR.
    """
    return await submit_refund(request_id, amount)
