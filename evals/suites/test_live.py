"""Live (needs the worker, the KSOR MCP server, OPENAI_API_KEY; Inngest dev server for gate flows).

    uv run pytest suites -m live --live-critical      # or: uv run python scripts/run_live.py
Serial by design (pacing); see harness/client.py.
"""

import os

import pytest
import runner
from validate import load

pytestmark = pytest.mark.live
CASES = [c for c in load()[0] if c.status != "known_failing" and not (c.endpoint == "unit" or (c.endpoint == "gate" and c.turns[0].decision is None))]
if os.environ.get("EVAL_CRITICAL_ONLY"):
    CASES = [c for c in CASES if c.critical]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_live_case(case):
    result = runner.run_case(case)
    if result.verdict == "SKIP":
        pytest.skip(result.repeats[0].detail)
    if result.verdict == "ERROR":
        pytest.fail(f"infra error (not a behavior finding): {[r.detail for r in result.repeats if r.detail]}", pytrace=False)
    failing = [(r.repeat, k.name, k.detail) for r in result.repeats for k in r.checks if not k.passed]
    assert result.verdict == "PASS", failing
