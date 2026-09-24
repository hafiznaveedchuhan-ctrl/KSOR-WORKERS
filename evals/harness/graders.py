"""Deterministic graders — no LLM. This layer is the critical gate: it is cheap,
exact and cannot be talked round. LLM/judge metrics sit on top of it, never
instead of it.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "datasets"))
from schema import Case  # noqa: E402

# Wording that turns a scope boundary into a fake outage (documented bug, progress.md
# "cricket question" — 1 of 4 runs said this). An abstention must never read like one.
OUTAGE_PHRASES = ("unable to access", "at the moment", "try again later", "temporarily unavailable")

_URL = re.compile(r"https?://[^\s)\]>\"']+")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _canon(url: str) -> str:
    return url.rstrip(".,;:/").lower()


def urls_in(text: str) -> list[str]:
    return [_canon(u) for u in _URL.findall(text)]


LATENCY_BUDGET_MS = float(__import__("os").environ.get("EVAL_LATENCY_BUDGET_MS", "180000"))


def grade(case: Case, answer: str, routed_to: str | None, latency_ms: float = 0.0) -> list[Check]:
    e = case.expected
    low = answer.lower()
    checks: list[Check] = []

    if e.exact_string is not None:
        checks.append(Check("exact_string", answer.strip() == e.exact_string.strip(),
                            f"got {answer.strip()[:120]!r}"))
    if e.routed_to is not None:
        checks.append(Check("routed_to", routed_to == e.routed_to, f"got {routed_to!r}, want {e.routed_to!r}"))
    for s in e.must_include_all:
        checks.append(Check(f"include:{s}", s.lower() in low))
    for group in e.must_include_any:
        checks.append(Check(f"include_any:{'|'.join(group)}", any(s.lower() in low for s in group)))
    for s in e.must_not_include:
        checks.append(Check(f"exclude:{s}", s.lower() not in low))

    if e.max_words is not None:
        n = len(answer.split())
        checks.append(Check("max_words", n <= e.max_words, f"{n} words > {e.max_words}" if n > e.max_words else ""))

    allowed = {_canon(u) for u in e.forbid_urls_except}
    bad = [u for u in urls_in(answer) if u not in allowed]
    checks.append(Check("no_fabricated_url", not bad, f"unexpected: {bad}" if bad else ""))

    if latency_ms:
        checks.append(Check("latency_budget", latency_ms <= LATENCY_BUDGET_MS, f"{latency_ms / 1000:.0f}s > {LATENCY_BUDGET_MS / 1000:.0f}s budget" if latency_ms > LATENCY_BUDGET_MS else ""))
    if e.abstain:
        leaked = [p for p in OUTAGE_PHRASES if p in low]
        checks.append(Check("abstention_not_an_outage", not leaked, f"outage wording: {leaked}" if leaked else ""))
    return checks


def passed(checks: list[Check]) -> bool:
    return all(c.passed for c in checks)
