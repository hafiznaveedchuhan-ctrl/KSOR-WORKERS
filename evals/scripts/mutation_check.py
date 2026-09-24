"""Does the dataset have teeth? Break a guard on purpose and confirm the golden cases catch it
(book, Decision 6: "a PR that intentionally worsens behavior is blocked").

Mutations are applied IN-PROCESS by monkeypatching, so the working tree is never edited and nothing needs reverting.
OFFLINE mutations need no key. LIVE mutations run the real agents (OPENAI_API_KEY + KSOR MCP) N times each.

    uv run python scripts/mutation_check.py --offline
    uv run python scripts/mutation_check.py --live --repeats 3
"""

import argparse
import asyncio
import contextlib
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
for sub in ("datasets", "harness"):
    sys.path.insert(0, str(HERE / sub))
import graders  # noqa: E402
import runner  # noqa: E402
from validate import load  # noqa: E402

CASES = {c.case_id: c for c in load()[0]}


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


# ---------------------------------------------------------------- offline mutations
def m_keywords_emptied():
    from ksor_worker import common
    return patched(common, "REFUND_KEYWORDS", ())


def m_threshold_off_by_one():
    from ksor_worker import refund_gate
    return patched(refund_gate, "refund_gate_threshold", lambda: 5001.0)


def _mutated_submit(fail_open: bool, validate: bool):
    from ksor_worker import refund_gate as rg
    import inngest

    async def submit(request_id: str, amount: float) -> str:
        if validate and amount <= 0:
            return "Invalid refund amount: it must be greater than zero."
        if amount < rg.refund_gate_threshold():
            rg.write_audit(request_id, "refund_issued", amount, "auto-approved below threshold")
            return f"Refund of {amount:g} PKR for request {request_id} has been issued."
        try:
            await rg.client.send(inngest.Event(name=rg.REQUESTED_EVENT, data={"request_id": request_id, "amount": amount}))
        except Exception:
            if fail_open:
                rg.write_audit(request_id, "refund_issued", amount, "fail-open")
                return f"Refund of {amount:g} PKR for request {request_id} has been issued."
            return f"Could not start the approval process for request {request_id}. The refund has NOT been issued."
        return f"Refund request {request_id} for {amount:g} PKR needs human approval and is now pending. It has NOT been issued yet."

    return submit


def m_gate_fails_open():
    from ksor_worker import refund_gate
    return patched(refund_gate, "submit_refund", _mutated_submit(fail_open=True, validate=True))


def m_no_amount_validation():
    from ksor_worker import refund_gate
    return patched(refund_gate, "submit_refund", _mutated_submit(fail_open=False, validate=False))


OFFLINE = [
    ("REFUND_KEYWORDS emptied (the /ask refund gate removed)", m_keywords_emptied, ["rd-unit-return-window", "rd-unit-clawback", "rd-unit-cancelled-uppercase", "rd-unit-returns-substring"]),
    ("gate threshold off by one (5000 no longer gates)", m_threshold_off_by_one, ["gt-at-threshold-pending"]),
    ("refund gate fails OPEN when Inngest is down", m_gate_fails_open, ["gt-inngest-down-fails-closed"]),
    ("amount validation removed (0 / negative accepted)", m_no_amount_validation, ["gt-zero-amount-invalid", "gt-negative-amount-invalid"]),
]


def run_offline() -> int:
    misses = 0
    print("OFFLINE mutations")
    for label, mut, targets in OFFLINE:
        with mut():
            verdicts = {cid: runner.run_case(CASES[cid]).verdict for cid in targets}
        detected = any(v != "PASS" for v in verdicts.values())
        misses += not detected
        print(f"  {'CAUGHT ' if detected else 'MISSED!'} {label}  ->  {verdicts}")
    clean = {cid: runner.run_case(CASES[cid]).verdict for _l, _m, ts in OFFLINE for cid in ts}
    print("  control (no mutation):", "all PASS" if all(v == "PASS" for v in clean.values()) else clean)
    return misses


# ---------------------------------------------------------------- live (in-process) mutations
async def _triage(query: str) -> tuple[str, str]:
    from ksor_worker import triage_agent as ta
    return await ta.run_triage_agent(query, f"mut-{uuid.uuid4().hex[:8]}")


async def _refund(query: str) -> tuple[str, str | None]:
    from ksor_worker import refund_agent as ra
    return await ra.run_refund_agent(query, f"mut-{uuid.uuid4().hex[:8]}"), None


def m_addendum_restored():
    """The REAL regression this eval caught on 2026-09-24: the refund-submission prompt addendum."""
    from ksor_worker import triage_agent as ta
    addendum = ("\n\nEXCEPTION to the topic check above: if the customer asks you to submit or process a refund AND gives both "
                "a request id and an amount in PKR, call the request_refund tool with exactly those values. Report the tool's "
                "result to the customer as-is — if it says the refund is pending human approval, say it is pending and has not "
                "been issued; never tell the customer a refund was issued unless the tool says so. If the request id or amount "
                "is missing, ask for it instead of guessing.")
    return patched(ta, "REFUND_INSTRUCTIONS", ta.REFUND_INSTRUCTIONS + addendum)


def m_handoff_noise_filter_removed():
    from agents.extensions import handoff_filters
    return patched(handoff_filters, "remove_all_tools", lambda data: data)


def m_no_url_rule():
    from ksor_worker import refund_agent as ra
    marker = "Never include a URL"
    cut = ra.INSTRUCTIONS.index(marker)
    return patched(ra, "INSTRUCTIONS", ra.INSTRUCTIONS[:cut])


LIVE = [
    ("refund-submission prompt addendum restored (the real 2026-09-24 regression)", m_addendum_restored, "tr-refund-when-will-i-get", _triage),
    ("handoff tool-call noise filter removed (ADR 005 bug)", m_handoff_noise_filter_removed, "tr-refund-when-will-i-get", _triage),
    ("'never invent a URL' rule removed from the refund agent (ADR 003 bug)", m_no_url_rule, "rd-refund-no-invented-url", _refund),
]


def run_live(repeats: int) -> int:
    misses = 0
    print(f"LIVE mutations ({repeats} repeats each; caught = at least one repeat fails the case's checks)")
    for label, mut, cid, fn in LIVE:
        case = CASES[cid]

        def trial() -> int:
            failed = 0
            for _ in range(repeats):
                ans, routed = asyncio.run(fn(case.turns[0].query))
                failed += not graders.passed(graders.grade(case, ans, routed))
            return failed

        control_failed = trial()
        with mut():
            mutated_failed = trial()
        detected = mutated_failed > 0 and control_failed == 0
        misses += not detected
        print(f"  {'CAUGHT ' if detected else 'MISSED!'} {label}  control failed {control_failed}/{repeats}, mutated failed {mutated_failed}/{repeats}")
    return misses


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    missed = 0
    if a.offline or not a.live:
        missed += run_offline()
    if a.live:
        missed += run_live(a.repeats)
    print("\nevery mutation was caught" if not missed else f"\n{missed} mutation(s) NOT caught — the dataset is missing teeth there")
    sys.exit(1 if missed else 0)
