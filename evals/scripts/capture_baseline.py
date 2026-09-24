"""Record a baseline from one or more results.jsonl files (later files override earlier ones per case).

    uv run python scripts/capture_baseline.py runs/<full>/results.jsonl runs/<extra>/results.jsonl --reason "first baseline"

A baseline is a decision (book Decision 6): it must be GREEN on every critical active case, the dataset should be
owner-reviewed, and every change is logged in reports/baseline-history.md with a reason.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "datasets"))
from validate import GOLDEN, load  # noqa: E402

REPORTS = HERE / "reports"


def merge(paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["case_id"]] = r
    return out


def category_rates(results: dict[str, dict]) -> dict[str, dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in results.values():
        if r["status"] == "active":
            by[r["category"]].append(r)
    rates = {}
    for cat, rs in by.items():
        graded = [r for r in rs if r["verdict"] in ("PASS", "FAIL")]
        rates[cat] = {
            "cases": len(rs), "graded": len(graded),
            "pass": sum(r["verdict"] == "PASS" for r in graded),
            "rate": round(sum(r["verdict"] == "PASS" for r in graded) / len(graded), 4) if graded else None,
            "errors": sum(r["verdict"] == "ERROR" for r in rs), "skipped": sum(r["verdict"] == "SKIP" for r in rs),
        }
    return rates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", type=Path)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--allow-red", action="store_true")
    ap.add_argument("--allow-unreviewed", action="store_true")
    args = ap.parse_args()

    cases, errors = load()
    if errors:
        print("dataset invalid:", *errors, sep="\n  ")
        return 2
    results = merge(args.results)
    missing = [c.case_id for c in cases if c.case_id not in results]
    red = [r["case_id"] for r in results.values() if r["status"] == "active" and r["critical"] and r["verdict"] not in ("PASS", "SKIP")]
    unreviewed = [c.case_id for c in cases if not c.reviewed_by]
    problems = []
    if missing:
        problems.append(f"{len(missing)} dataset cases have no result: {missing[:5]}...")
    if red and not args.allow_red:
        problems.append(f"critical cases not green: {red}")
    if unreviewed and not args.allow_unreviewed:
        problems.append(f"{len(unreviewed)} cases are not owner-reviewed (--allow-unreviewed to record a PROVISIONAL baseline)")
    if problems:
        print("refusing to record a baseline:", *problems, sep="\n  - ")
        return 1

    commit = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    baseline = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "worker_commit": commit, "reason": args.reason,
        "provisional": bool(unreviewed),
        "dataset_sha256": hashlib.sha256(GOLDEN.read_bytes()).hexdigest()[:16], "cases": len(cases),
        "categories": category_rates(results),
        "cases_verdict": {cid: {"verdict": r["verdict"], "critical": r["critical"], "status": r["status"]} for cid, r in results.items()},
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

    lines = [f"# Eval baseline{' (PROVISIONAL — dataset not fully owner-reviewed)' if baseline['provisional'] else ''}", "",
             f"- captured: {baseline['captured_at']}  ·  worker commit `{commit}`  ·  dataset `{baseline['dataset_sha256']}` ({len(cases)} cases)",
             f"- reason: {args.reason}", "", "| category | graded | pass | rate | errors | skipped |", "|---|---|---|---|---|---|"]
    for cat, v in sorted(baseline["categories"].items()):
        rate = f"{v['rate']:.0%}" if v["rate"] is not None else "—"
        lines.append(f"| {cat} | {v['graded']} | {v['pass']} | {rate} | {v['errors']} | {v['skipped']} |")
    known = [cid for cid, r in results.items() if r["status"] == "known_failing"]
    blocked = [cid for cid, r in results.items() if r["status"] == "blocked_until_stable"]
    lines += ["", f"Tracked separately (not in the rates above): {len(known)} known_failing, {len(blocked)} blocked_until_stable."]
    (REPORTS / "baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(REPORTS / "baseline-history.md", "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("# Baseline history\n\nEvery baseline change is a reviewed decision; add the reason.\n\n")
        f.write(f"- {baseline['captured_at']} · `{commit}` · dataset `{baseline['dataset_sha256']}` · {args.reason}"
                f"{' · PROVISIONAL' if baseline['provisional'] else ''}\n")
    print((REPORTS / "baseline.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
