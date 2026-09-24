"""Run golden cases and print a report.

    uv run python scripts/run_live.py --offline               # unit + in-process gate cases only (no key/servers)
    uv run python scripts/run_live.py --category triage_routing --repeats 1
    uv run python scripts/run_live.py --critical              # the smoke set
    uv run python scripts/run_live.py --case-id gq-standard-return-window -v

Live cases need: the worker (uv run uvicorn main:app --port 8000), the KSOR MCP server, OPENAI_API_KEY,
and for the Inngest gate flows the dev server (npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest).
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "harness"))
sys.path.insert(0, str(HERE / "datasets"))
import runner  # noqa: E402
from validate import load  # noqa: E402

OFFLINE_ENDPOINTS = {"unit"}


def is_offline(case) -> bool:
    return case.endpoint == "unit" or (case.endpoint == "gate" and case.turns[0].decision is None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--category")
    ap.add_argument("--case-id", action="append")
    ap.add_argument("--critical", action="store_true")
    ap.add_argument("--repeats", type=int)
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()

    cases, errors = load()
    if errors:
        print("dataset invalid:", *errors, sep="\n  ")
        return 2
    sel = [
        c for c in cases
        if (not args.offline or is_offline(c))
        and (not args.category or c.category.value == args.category)
        and (not args.case_id or c.case_id in args.case_id)
        and (not args.critical or c.critical)
    ]
    print(f"running {len(sel)} case(s)")
    results = []
    for c in sel:
        t0 = time.time()
        r = runner.run_case(c, args.repeats)
        results.append(r)
        cnt = r.counts
        print(f"{r.verdict:16} {c.case_id:44} P{cnt['PASS']} F{cnt['FAIL']} E{cnt['ERROR']} S{cnt['SKIP']}  {time.time() - t0:5.1f}s")
        if args.v or r.verdict in ("FAIL", "ERROR", "UNEXPECTED_PASS"):
            for rep in r.repeats:
                bad = [k for k in rep.checks if not k.passed]
                if rep.verdict in ("FAIL", "ERROR") or args.v:
                    print(f"    run {rep.repeat} {rep.verdict} {rep.detail}", *(f"[{k.name}] {k.detail}" for k in bad))
                    if rep.answer:
                        print(f"      answer: {rep.answer[:240]!r}")

    by_cat: dict[str, list] = defaultdict(list)
    for r in results:
        by_cat[r.case.category.value].append(r)
    print("\ncategory                 PASS FAIL ERR SKIP KNOWN UNEXP")
    for cat, rs in by_cat.items():
        v = [r.verdict for r in rs]
        print(f"{cat:24} {v.count('PASS'):4} {v.count('FAIL'):4} {v.count('ERROR'):3} {v.count('SKIP'):4} {v.count('KNOWN_FAIL'):5} {v.count('UNEXPECTED_PASS'):5}")

    out = HERE / "runs" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "case_id": r.case.case_id, "category": r.case.category.value, "critical": r.case.critical,
                "status": r.case.status, "verdict": r.verdict,
                "repeats": [{"verdict": x.verdict, "latency_ms": x.latency_ms, "answer": x.answer, "routed_to": x.routed_to, "detail": x.detail,
                             "checks": [{"name": k.name, "passed": k.passed, "detail": k.detail} for k in x.checks]} for x in r.repeats],
            }, ensure_ascii=False) + "\n")
    print(f"\nresults: {out / 'results.jsonl'}")
    bad = [r for r in results if r.verdict in ("FAIL", "UNEXPECTED_PASS") or (r.verdict == "ERROR")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
