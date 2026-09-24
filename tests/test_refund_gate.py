import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("INNGEST_DEV", "1")

from ksor_worker import refund_gate  # noqa: E402


def _use_temp_db() -> str:
    path = os.path.join(tempfile.mkdtemp(), "audit_log.db")
    refund_gate.AUDIT_DB = path
    return path


def _rows(path: str) -> list[tuple[str, str]]:
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT request_id, action FROM audit_log ORDER BY id"
        ).fetchall()


def _call_tool(request_id: str, amount: float) -> str:
    return asyncio.run(refund_gate.submit_refund(request_id, amount))


def test_tool_is_registered_with_expected_schema() -> None:
    tool = refund_gate.request_refund
    assert tool.name == "request_refund"
    assert set(tool.params_json_schema["properties"]) == {"request_id", "amount"}


def test_threshold_reads_env_at_call_time() -> None:
    os.environ["REFUND_GATE_THRESHOLD"] = "123"
    assert refund_gate.refund_gate_threshold() == 123.0
    del os.environ["REFUND_GATE_THRESHOLD"]
    assert refund_gate.refund_gate_threshold() == 5000.0


def test_audit_write_is_idempotent() -> None:
    path = _use_temp_db()
    assert refund_gate.write_audit("r1", "refund_issued", 6000, "x") is True
    assert refund_gate.write_audit("r1", "refund_issued", 6000, "x") is False
    assert _rows(path) == [("r1", "refund_issued")]


def test_below_threshold_issues_directly_without_event() -> None:
    path = _use_temp_db()
    sent: list[object] = []

    async def fake_send(event: object) -> list[str]:
        sent.append(event)
        return ["id"]

    real_send = refund_gate.client.send
    refund_gate.client.send = fake_send  # type: ignore[method-assign]
    try:
        result = _call_tool("r-small", 1000)
    finally:
        refund_gate.client.send = real_send  # type: ignore[method-assign]
    assert "has been issued" in result
    assert sent == []
    assert _rows(path) == [("r-small", "refund_issued")]


def test_at_threshold_fires_event_and_issues_nothing() -> None:
    path = _use_temp_db()
    sent: list[object] = []

    async def fake_send(event: object) -> list[str]:
        sent.append(event)
        return ["id"]

    real_send = refund_gate.client.send
    refund_gate.client.send = fake_send  # type: ignore[method-assign]
    try:
        result = _call_tool("r-big", 5000)
    finally:
        refund_gate.client.send = real_send  # type: ignore[method-assign]
    assert "pending" in result and "NOT been issued" in result
    assert len(sent) == 1
    assert sent[0].name == refund_gate.REQUESTED_EVENT  # type: ignore[attr-defined]
    assert sent[0].data["request_id"] == "r-big"  # type: ignore[attr-defined]
    assert not os.path.exists(path)


def test_send_failure_is_reported_not_swallowed() -> None:
    path = _use_temp_db()

    async def boom(event: object) -> list[str]:
        raise ConnectionError("dev server down")

    real_send = refund_gate.client.send
    refund_gate.client.send = boom  # type: ignore[method-assign]
    try:
        result = _call_tool("r-big", 9000)
    finally:
        refund_gate.client.send = real_send  # type: ignore[method-assign]
    assert "NOT been issued" in result
    assert not os.path.exists(path)


if __name__ == "__main__":
    test_tool_is_registered_with_expected_schema()
    test_threshold_reads_env_at_call_time()
    test_audit_write_is_idempotent()
    test_below_threshold_issues_directly_without_event()
    test_at_threshold_fires_event_and_issues_nothing()
    test_send_failure_is_reported_not_swallowed()
    print("test_refund_gate: OK")
