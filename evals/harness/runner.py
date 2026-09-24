"""Execute golden cases and grade them deterministically.

Verdict vocabulary (kept apart on purpose, per the book's "errors and fails are
different problems"):
  PASS   every check passed          FAIL   a check failed (a behavior finding)
  ERROR  the case could not run (worker/MCP/Inngest down, 5xx, timeout)  — infra, not behavior
  SKIP   a precondition of the case is not met (e.g. timeout flow needs a short-timeout worker)
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "datasets"))
sys.path.insert(0, str(HERE))
from graders import Check, grade, passed  # noqa: E402
from schema import Case, Turn  # noqa: E402

import client  # noqa: E402

INNGEST_EVENT_URL = os.environ.get("INNGEST_EVENT_URL", "http://127.0.0.1:8288/e/eval")
WORKER_AUDIT_DB = Path(os.environ.get("WORKER_AUDIT_DB", HERE.parent.parent / "audit_log.db"))
EXPECT_TIMEOUT_SECONDS = os.environ.get("EVAL_EXPECT_TIMEOUT_SECONDS")  # set when the worker runs with REFUND_GATE_TIMEOUT_SECONDS


@dataclass
class RepeatResult:
    repeat: int
    verdict: str  # PASS | FAIL | ERROR | SKIP
    checks: list[Check] = field(default_factory=list)
    answer: str = ""
    routed_to: str | None = None
    latency_ms: float = 0.0
    detail: str = ""


@dataclass
class CaseResult:
    case: Case
    repeats: list[RepeatResult]

    @property
    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
        for r in self.repeats:
            out[r.verdict] += 1
        return out

    @property
    def verdict(self) -> str:
        """Case-level. critical -> every repeat must pass; else a strict majority."""
        c = self.counts
        n = len(self.repeats)
        if c["SKIP"] == n:
            return "SKIP"
        if c["ERROR"] and not c["PASS"] and not c["FAIL"]:
            return "ERROR"
        need = n if self.case.critical else n // 2 + 1
        ok = c["PASS"] >= need
        if self.case.status == "known_failing":
            # "fixed" means stably fixed: every repeat passes. An intermittent bug that passes 2 of 3 is still open.
            return "UNEXPECTED_PASS" if c["PASS"] == n else "KNOWN_FAIL"
        return "PASS" if ok else ("ERROR" if c["ERROR"] else "FAIL")


def _fill(text: str, uid: str) -> str:
    return text.replace("{uid}", uid)


def _audit_rows(db: Path) -> set[tuple[str, str]]:
    if not db.exists():
        return set()
    with sqlite3.connect(db) as conn:
        try:
            return set(conn.execute("SELECT request_id, action FROM audit_log").fetchall())
        except sqlite3.OperationalError:
            return set()  # table not created yet == no rows


def _check_audit(case: Case, uid: str, db: Path) -> list[Check]:
    rows = _audit_rows(db)
    out = []
    for a in case.expected.audit:
        key = (_fill(a.request_id, uid), a.action)
        out.append(Check(f"audit:{a.action}:{'present' if a.present else 'absent'}", (key in rows) == a.present,
                         f"{key} {'found' if key in rows else 'not found'}"))
    return out


# ---------------------------------------------------------------- unit
def _run_unit(case: Case, repeat: int) -> RepeatResult:
    from ksor_worker.common import is_refund_related

    got = is_refund_related(case.turns[0].query)
    ok = got == case.expected.gate_triggered
    return RepeatResult(repeat, "PASS" if ok else "FAIL", [Check("is_refund_related", ok, f"got {got}")])


# ---------------------------------------------------------------- gate, in-process (no Inngest server needed)
def _run_gate_inprocess(case: Case, repeat: int, uid: str) -> RepeatResult:
    from ksor_worker import refund_gate

    turn = case.turns[0]
    db = Path(tempfile.mkdtemp()) / "audit_log.db"
    sent: list[object] = []

    async def ok_send(event: object) -> list[str]:
        sent.append(event)
        return ["evt"]

    async def failing_send(event: object) -> list[str]:
        raise ConnectionError("inngest unreachable (simulated)")

    real_send, real_db = refund_gate.client.send, refund_gate.AUDIT_DB
    old_thr = os.environ.get("REFUND_GATE_THRESHOLD")
    os.environ["REFUND_GATE_THRESHOLD"] = "5000"
    refund_gate.client.send = failing_send if turn.send_fails else ok_send  # type: ignore[method-assign]
    refund_gate.AUDIT_DB = str(db)
    try:
        answer = asyncio.run(refund_gate.submit_refund(_fill(turn.request_id or "", uid), float(turn.amount or 0)))
    finally:
        refund_gate.client.send, refund_gate.AUDIT_DB = real_send, real_db  # type: ignore[method-assign]
        if old_thr is None:
            os.environ.pop("REFUND_GATE_THRESHOLD", None)
        else:
            os.environ["REFUND_GATE_THRESHOLD"] = old_thr

    checks = grade(case, answer, None)
    if case.expected.event_sent is not None:
        checks.append(Check("event_sent", bool(sent) == case.expected.event_sent, f"sent={len(sent)}"))
    checks += _check_audit(case, uid, db)
    return RepeatResult(repeat, "PASS" if passed(checks) else "FAIL", checks, answer)


# ---------------------------------------------------------------- gate, live Inngest
def _send_event(name: str, data: dict) -> None:
    httpx.post(INNGEST_EVENT_URL, json={"name": name, "data": data}, timeout=10).raise_for_status()


def _run_gate_live(case: Case, repeat: int, uid: str) -> RepeatResult:
    turn = case.turns[0]
    if turn.decision == "timeout" and not EXPECT_TIMEOUT_SECONDS:
        return RepeatResult(repeat, "SKIP", detail="needs the worker started with REFUND_GATE_TIMEOUT_SECONDS<=10 and EVAL_EXPECT_TIMEOUT_SECONDS set")
    if not client.worker_up():
        return RepeatResult(repeat, "ERROR", detail=f"worker not reachable at {client.BASE_URL}")
    rid = _fill(turn.request_id or "", uid)
    try:
        _send_event("refund/approval.requested", {"request_id": rid, "amount": turn.amount, "currency": "PKR"})
        time.sleep(5)
        if turn.decision == "approve":
            _send_event("refund/approval.decided", {"request_id": rid, "approved": True})
        elif turn.decision == "reject":
            _send_event("refund/approval.decided", {"request_id": rid, "approved": False})
        elif turn.decision == "wrong_id":
            _send_event("refund/approval.decided", {"request_id": f"other-{uid}", "approved": True})
        time.sleep(float(EXPECT_TIMEOUT_SECONDS) + 8 if turn.decision == "timeout" else 8)
    except httpx.HTTPError as exc:
        return RepeatResult(repeat, "ERROR", detail=f"Inngest dev server unreachable: {exc}")
    checks = _check_audit(case, uid, WORKER_AUDIT_DB)
    return RepeatResult(repeat, "PASS" if passed(checks) else "FAIL", checks)


# ---------------------------------------------------------------- LLM endpoints
def _run_http(case: Case, repeat: int, uid: str) -> RepeatResult:
    filled = case.model_copy(deep=True)
    for t in filled.turns:
        t.query = _fill(t.query, uid)
    run = client.run_case(filled, repeat)
    if run.error:
        return RepeatResult(repeat, "ERROR", detail=run.error)
    answer, routed = run.answer, run.routed_to[-1] if run.routed_to else None
    latency = sum(run.latency_ms)
    checks = grade(case, answer, routed, latency)
    if case.expected.audit:
        time.sleep(6)  # let the tool call / Inngest step finish writing
        checks += _check_audit(case, uid, WORKER_AUDIT_DB)
    return RepeatResult(repeat, "PASS" if passed(checks) else "FAIL", checks, answer, routed, latency)


def run_repeat(case: Case, repeat: int) -> RepeatResult:
    uid = uuid.uuid4().hex[:6]
    if case.endpoint == "unit":
        return _run_unit(case, repeat)
    if case.endpoint == "gate":
        return _run_gate_inprocess(case, repeat, uid) if case.turns[0].decision is None else _run_gate_live(case, repeat, uid)
    return _run_http(case, repeat, uid)


def run_case(case: Case, repeats: int | None = None) -> CaseResult:
    n = repeats or case.repeats
    if case.endpoint in ("unit",) or (case.endpoint == "gate" and case.turns[0].decision is None):
        n = 1  # deterministic code: repeating adds nothing
    return CaseResult(case, [run_repeat(case, i + 1) for i in range(n)])
