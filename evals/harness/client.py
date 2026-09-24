"""Run one case against the live worker over HTTP.

Serial and paced on purpose: rapid back-to-back calls produced timeouts and a
prime-decline misfire in this project (docs/adr/005, progress.md), and that is
noise an eval must not mistake for a regression. Infrastructure failures
(502/500/timeouts) are reported as ERROR, never as a wrong answer.
"""

import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "datasets"))
from schema import Case  # noqa: E402

BASE_URL = os.environ.get("WORKER_URL", "http://127.0.0.1:8000")
PACING_SECONDS = float(os.environ.get("EVAL_PACING_SECONDS", "4"))
TIMEOUT_SECONDS = float(os.environ.get("EVAL_TIMEOUT_SECONDS", "90"))

PATHS = {"ask": "/ask", "chat": "/chat", "refund": "/refund", "triage": "/triage", "compare": "/compare"}
SESSIONED = {"chat", "refund", "triage"}


@dataclass
class Run:
    case_id: str
    repeat: int
    answers: list[str] = field(default_factory=list)  # one per turn
    routed_to: list[str | None] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)
    error: str | None = None  # "infra: ..." — the case could not be evaluated

    @property
    def answer(self) -> str:
        return self.answers[-1] if self.answers else ""


def worker_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


def _post(client: httpx.Client, path: str, body: dict) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(2):  # one retry, infra errors only
        try:
            resp = client.post(path, json=body)
            if resp.status_code in (500, 502, 503, 504) and attempt == 0:
                time.sleep(PACING_SECONDS + 2)
                continue
            return resp
        except httpx.HTTPError as exc:
            last = exc
            time.sleep(PACING_SECONDS + 2)
    raise httpx.HTTPError(f"no response after retry: {last}")


def run_case(case: Case, repeat: int) -> Run:
    """Fresh session_id per repeat; the turns of one case share it, in order."""
    run = Run(case.case_id, repeat)
    session_id = f"eval-{case.case_id}-{repeat}-{uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_SECONDS) as client:
        for turn in case.turns:
            body: dict = {"query": turn.query}
            if case.endpoint in SESSIONED:
                body["session_id"] = session_id
            try:
                resp = _post(client, PATHS[case.endpoint], body)
            except httpx.HTTPError as exc:
                run.error = f"infra: {exc}"
                return run
            if resp.status_code != 200:
                run.error = f"infra: HTTP {resp.status_code} {resp.text[:200]}"
                return run
            data = resp.json()
            run.answers.append(data["answer"])
            run.routed_to.append(data.get("routed_to"))
            run.latency_ms.append(data.get("latency_ms", 0.0))
            time.sleep(PACING_SECONDS)
    return run
