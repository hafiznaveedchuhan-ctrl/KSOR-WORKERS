"""Validate golden.jsonl: schema, uniqueness, quotes against the KB snapshot, mix.

Offline, no key, no server — this is what CI runs.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import Case, Category  # noqa: E402

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden.jsonl"
SNAPSHOT = HERE.parent / "fixtures" / "kb_snapshot.json"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def load(path: Path = GOLDEN) -> tuple[list[Case], list[str]]:
    cases: list[Case] = []
    errors: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(Case.model_validate(json.loads(line)))
        except (ValidationError, json.JSONDecodeError) as exc:
            errors.append(f"line {n}: {exc}")
    return cases, errors


def validate(path: Path = GOLDEN, *, require_reviewed: bool = False) -> tuple[list[Case], list[str], list[str]]:
    """Returns (cases, errors, warnings)."""
    cases, errors = load(path)
    warnings: list[str] = []
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["docs"]

    ids = Counter(c.case_id for c in cases)
    errors += [f"duplicate case_id: {i}" for i, n in ids.items() if n > 1]
    keys = Counter((c.endpoint, c.language, tuple((norm(t.query), t.amount, t.decision) for t in c.turns)) for c in cases)
    errors += [f"duplicate input: {k[2][0][0][:60]!r} on {k[0]}" for k, n in keys.items() if n > 1]

    for c in cases:
        if c.source:
            doc = snap.get(c.source.stable_id)
            if doc is None:
                errors.append(f"{c.case_id}: source {c.source.stable_id} is not in kb_snapshot")
            elif c.status == "blocked_until_stable":
                if doc["status"] == "stable":
                    warnings.append(
                        f"{c.case_id}: {c.source.stable_id} is now STABLE — promote this case to a positive grounded_qa case"
                    )
            elif c.source.quote:
                if doc["status"] != "stable":
                    errors.append(f"{c.case_id}: quotes {c.source.stable_id}, which is {doc['status']} (not served)")
                else:
                    q = norm(c.source.quote)
                    if q not in norm(doc["body"]) and q not in norm(doc["plain"]):
                        errors.append(f"{c.case_id}: quote is not verbatim in {c.source.stable_id}")
        if require_reviewed and not c.reviewed_by:
            errors.append(f"{c.case_id}: not reviewed by the owner")
        elif not c.reviewed_by:
            warnings.append(f"{c.case_id}: awaiting owner review")

    if len(cases) >= 30:
        hard = sum(c.difficulty == "hard" for c in cases) / len(cases)
        if hard < 0.30:
            errors.append(f"only {hard:.0%} hard cases; the book's floor is 30% (Easy-Mode Bias)")
        for cat in Category:
            if not any(c.category == cat for c in cases):
                errors.append(f"no cases in category {cat}")
    return cases, errors, warnings


def summary(cases: list[Case]) -> str:
    rows = [f"{len(cases)} cases"]
    for cat in Category:
        sub = [c for c in cases if c.category == cat]
        if sub:
            d = Counter(c.difficulty for c in sub)
            rows.append(
                f"  {cat.value:15} {len(sub):3}  easy {d['easy']:2} medium {d['medium']:2} hard {d['hard']:2}"
                f"  critical {sum(c.critical for c in sub):2}"
            )
    st = Counter(c.status for c in cases)
    rows.append(f"  status: {dict(st)}  | roman_urdu: {sum(c.language == 'roman_urdu' for c in cases)}")
    return "\n".join(rows)


if __name__ == "__main__":
    req = "--require-reviewed" in sys.argv
    cs, errs, warns = validate(require_reviewed=req)
    print(summary(cs))
    if warns and "-v" in sys.argv:
        print("warnings:", *warns, sep="\n  ")
    elif warns:
        print(f"({len(warns)} warnings; -v to list)")
    if errs:
        print("ERRORS:", *errs, sep="\n  ")
        sys.exit(1)
    print("dataset valid")
