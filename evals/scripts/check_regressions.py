"""Compare a run against reports/baseline.json. Exit 1 blocks the merge.

    uv run python scripts/check_regressions.py runs/<ts>/results.jsonl [more.jsonl ...]

Blocks on: any critical active case not PASS; any case that was PASS in the baseline and is now FAIL;
a category pass-rate drop of more than 5 points. Reports (never blocks on): a known_failing case that now passes
(promote it), infra ERRORs, and cases new since the baseline.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
from capture_baseline import category_rates, merge  # noqa: E402

TOLERANCE = 0.05


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print(__doc__)
        return 2
    base = json.loads((HERE / "reports" / "baseline.json").read_text())
    results = merge(paths)
    block: list[str] = []
    notes: list[str] = []

    for cid, r in results.items():
        was = base["cases_verdict"].get(cid)
        if r["status"] == "active" and r["critical"] and r["verdict"] not in ("PASS", "SKIP"):
            block.append(f"CRITICAL {cid}: {r['verdict']}")
        elif r["status"] == "active" and was and was["verdict"] == "PASS" and r["verdict"] == "FAIL":
            block.append(f"REGRESSION {cid}: PASS -> FAIL")
        if r["verdict"] == "UNEXPECTED_PASS":
            notes.append(f"PROMOTE {cid}: known_failing now passes — set status active")
        if r["verdict"] == "ERROR":
            notes.append(f"ERROR {cid}: infra problem, not a behavior finding")
        if was is None:
            notes.append(f"NEW {cid}: not in the baseline")

    now = category_rates(results)
    for cat, old in base["categories"].items():
        cur = now.get(cat)
        if cur and cur["rate"] is not None and old["rate"] is not None and cur["rate"] < old["rate"] - TOLERANCE:
            block.append(f"CATEGORY {cat}: {old['rate']:.0%} -> {cur['rate']:.0%} (drop > {TOLERANCE:.0%})")

    for n in notes:
        print("note:", n)
    if block:
        print("\nBLOCKED:", *block, sep="\n  ")
        return 1
    print(f"\nno regressions vs baseline {base['captured_at']} ({base['worker_commit']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
