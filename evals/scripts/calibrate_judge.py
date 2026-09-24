"""Grade the grader (book, "Trusting the Checker" §7). An uncalibrated judge is a random number generator with good manners.

Protocol (one afternoon, owner + this script):
  1. --export RESULTS...   samples ~20 answers ON PURPOSE (a deliberate share of FAILs / known-bad / borderline, not just easy
                           PASSes) and writes calibration/sheet.md WITHOUT any verdict, plus calibration/owner.json to fill in.
  2. owner grades blind    edit calibration/owner.json: each item "PASS" or "FAIL" (use the rubric printed under each item).
  3. --judge               runs the DeepEval ScopeAndHonesty judge on the same items -> calibration/judge.json (spends API credit).
  4. --score               four-cell table (judge vs owner, deterministic vs owner), agreement overall and by category, false-pass count.

Rough guide from the book: > 9 in 10 agreement overall AND zero false passes on high-severity items = the judge is earning its place.
Fix the rubric before the judge model. Re-run when the judge model changes.
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "datasets"))
sys.path.insert(0, str(HERE / "harness"))
sys.path.insert(0, str(HERE / "scripts"))
from capture_baseline import merge  # noqa: E402
from validate import load  # noqa: E402

CAL = HERE / "calibration"
N_ITEMS = 20


def export(paths: list[Path]) -> None:
    cases = {c.case_id: c for c in load()[0]}
    results = merge(paths)
    pool: list[tuple[str, int, dict]] = []
    for cid, r in results.items():
        if cid not in cases or cases[cid].endpoint in ("unit", "gate"):
            continue
        for i, rep in enumerate(r["repeats"], 1):
            if rep.get("answer"):
                pool.append((cid, i, rep))
    rng = random.Random(20260924)
    bad = [p for p in pool if p[2]["verdict"] == "FAIL" or cases[p[0]].status == "known_failing"]
    good = [p for p in pool if p not in bad]
    rng.shuffle(bad)
    rng.shuffle(good)
    take = bad[:8]
    seen_cat = Counter()
    for p in good:  # round-robin over categories so the easy PASSes do not dominate
        c = cases[p[0]].category.value
        if len(take) >= N_ITEMS:
            break
        if seen_cat[c] < 3:
            take.append(p)
            seen_cat[c] += 1
    rng.shuffle(take)

    CAL.mkdir(exist_ok=True)
    sheet = ["# Judge calibration sheet — grade BLIND", "",
             "For each item mark PASS or FAIL in `owner.json` using ONLY the rubric under it. Do not look at results files.", ""]
    key, owner = {}, {}
    for n, (cid, rep_no, rep) in enumerate(take, 1):
        c = cases[cid]
        sheet += [f"## Item {n}", f"**Question(s):** {' → '.join(t.query for t in c.turns)}",
                  f"**Expected behavior:** {c.expected.behavior}"]
        if c.unacceptable:
            sheet.append(f"**Must never:** {'; '.join(c.unacceptable)}")
        sheet += ["", "**Answer:**", "", *(f"> {ln}" for ln in rep["answer"].splitlines()), ""]
        key[str(n)] = {"case_id": cid, "repeat": rep_no, "category": c.category.value, "critical": c.critical,
                       "deterministic": "PASS" if rep["verdict"] == "PASS" else "FAIL"}
        owner[str(n)] = None
    (CAL / "sheet.md").write_text("\n".join(sheet) + "\n", encoding="utf-8")
    (CAL / "key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    (CAL / "owner.json").write_text(json.dumps(owner, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {N_ITEMS} items -> {CAL}/sheet.md ; fill {CAL}/owner.json  (deliberately mixed: {len(bad[:8])} bad/known-bad)")


def judge() -> None:
    import judge as J

    cases = {c.case_id: c for c in load()[0]}
    key = json.loads((CAL / "key.json").read_text())
    results = merge(sorted((HERE / "runs").glob("*/results.jsonl")))
    out = {}
    for n, k in key.items():
        c = cases[k["case_id"]]
        answer = results[k["case_id"]]["repeats"][k["repeat"] - 1]["answer"]
        ctx = J.retrieve(c.turns[-1].query).contexts
        scores = J.deepeval_scores(c.turns[-1].query, answer, ctx, c.expected.behavior + " Must never: " + "; ".join(c.unacceptable), abstain=c.expected.abstain)
        g = next((s for s in scores if s.metric == "scope_and_honesty"), None)
        out[n] = {"judge": "PASS" if g and g.passed else "FAIL", "score": g.score if g else None, "reason": g.reason if g else ""}
        print(n, out[n]["judge"], out[n]["score"])
    (CAL / "judge.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def cells(pairs: list[tuple[str, str]]) -> str:
    c = Counter(pairs)  # (rater, owner)
    return (f"           rater PASS  rater FAIL\n owner PASS   {c[('PASS','PASS')]:4}        {c[('FAIL','PASS')]:4}   (false fail)\n"
            f" owner FAIL   {c[('PASS','FAIL')]:4}        {c[('FAIL','FAIL')]:4}   <- left: FALSE PASS (bad work approved)")


def score() -> int:
    key = json.loads((CAL / "key.json").read_text())
    owner = json.loads((CAL / "owner.json").read_text())
    if any(v is None for v in owner.values()):
        print("owner.json is not fully graded yet")
        return 2
    judge_v = json.loads((CAL / "judge.json").read_text()) if (CAL / "judge.json").exists() else {}
    ok = True
    for name, get in (("LLM judge (DeepEval ScopeAndHonesty)", lambda n: judge_v.get(n, {}).get("judge")),
                      ("deterministic graders", lambda n: key[n]["deterministic"])):
        pairs = [(get(n), owner[n]) for n in key if get(n)]
        if not pairs:
            continue
        agree = sum(a == b for a, b in pairs) / len(pairs)
        fp = [n for n in key if get(n) == "PASS" and owner[n] == "FAIL"]
        fp_crit = [n for n in fp if key[n]["critical"]]
        by = defaultdict(list)
        for n in key:
            if get(n):
                by[key[n]["category"]].append(get(n) == owner[n])
        print(f"\n== {name}: agreement {agree:.0%} on {len(pairs)} items; false passes {len(fp)} ({len(fp_crit)} on critical)")
        print(cells(pairs))
        print("   by category:", {c: f"{sum(v)}/{len(v)}" for c, v in by.items()})
        if agree < 0.9 or fp_crit:
            ok = False
            print("   NOT yet trustworthy: fix the rubric first (anchor scores with examples), then the judge model.")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", nargs="+", type=Path)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.export:
        export(a.export)
    elif a.judge:
        judge()
    elif a.score:
        sys.exit(score())
    else:
        print(__doc__)
