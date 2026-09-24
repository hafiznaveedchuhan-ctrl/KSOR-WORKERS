"""Offline (no key, no servers): unit + in-process refund-gate cases from the golden set."""

import pytest
import runner
from validate import load

CASES = [c for c in load()[0] if c.endpoint == "unit" or (c.endpoint == "gate" and c.turns[0].decision is None)]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_deterministic_case(case):
    result = runner.run_case(case)
    failing = [(k.name, k.detail) for r in result.repeats for k in r.checks if not k.passed]
    assert result.verdict == "PASS", failing
