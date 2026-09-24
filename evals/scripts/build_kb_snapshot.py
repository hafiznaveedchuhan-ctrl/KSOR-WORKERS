"""Capture the served knowledge corpus into evals/fixtures/kb_snapshot.json.

The dataset must not depend on ../handbook being on disk at run time, so grounded
quotes are validated against this snapshot instead. Only `stable` documents get
their body copied in (they are published on the owner's site). `draft` documents
are recorded as pointers + sha only: their text is unpublished by design and this
repo is public.

    uv run python scripts/build_kb_snapshot.py --knowledge-dir /home/naveed/handbook/knowledge
    uv run python scripts/build_kb_snapshot.py --knowledge-dir ... --check   # drift check, exit 1 if changed
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

SNAPSHOT = Path(__file__).resolve().parent.parent / "fixtures" / "kb_snapshot.json"
RESERVED = {"index.md", "log.md", "README.md"}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def plain(text: str) -> str:
    """Markdown stripped just enough that a prose quote matches: emphasis, code ticks,
    footnote refs, link syntax, list bullets, table pipes."""
    text = re.sub(r"\[\^[^\]]+\]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*`|]", "", text)
    text = re.sub(r"(?m)^\s*[-#>]+\s*", "", text)
    return normalize(text)


def split_doc(raw: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError("no frontmatter")
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def build(knowledge_dir: Path) -> dict:
    docs: dict[str, dict] = {}
    for path in sorted(knowledge_dir.rglob("*.md")):
        if path.name in RESERVED or path.name.endswith(".summary.md"):
            continue
        rel = path.relative_to(knowledge_dir).with_suffix("")
        raw = path.read_text(encoding="utf-8")
        fm, body = split_doc(raw)
        stable_id = f"knowledge/{rel.as_posix()}"
        entry = {
            "stable_id": stable_id,
            "title": fm.get("title"),
            "status": fm.get("status"),
            "sha256": hashlib.sha256(raw.encode()).hexdigest(),
        }
        if fm.get("status") == "stable":
            entry["body"] = body.strip()
            entry["plain"] = plain(body)
            entry["source_urls"] = [s.get("resource") for s in fm.get("sources", []) or []]
        docs[stable_id] = entry
    commit = subprocess.run(
        ["git", "-C", str(knowledge_dir), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()
    return {"handbook_commit": commit, "docs": docs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--knowledge-dir", required=True, type=Path)
    ap.add_argument("--check", action="store_true", help="compare with the committed snapshot, don't write")
    args = ap.parse_args()
    snap = build(args.knowledge_dir)
    if args.check:
        old = json.loads(SNAPSHOT.read_text())
        drift = [k for k in snap["docs"] if snap["docs"][k]["sha256"] != old["docs"].get(k, {}).get("sha256")]
        drift += [k for k in old["docs"] if k not in snap["docs"]]
        if drift:
            print("DRIFT: the record changed since the snapshot; re-review affected cases:", *sorted(set(drift)), sep="\n  ")
            return 1
        print("kb_snapshot: in sync with the record")
        return 0
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stable = sum(1 for d in snap["docs"].values() if d["status"] == "stable")
    print(f"wrote {SNAPSHOT} — {len(snap['docs'])} docs ({stable} stable with body, handbook @ {snap['handbook_commit']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
