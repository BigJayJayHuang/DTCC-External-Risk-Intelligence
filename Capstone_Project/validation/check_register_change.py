"""CI check: how event_register.csv may change in a pull request.

    python -m validation.check_register_change --base <git revision>

Compared with the register at --base:
  - the header may only gain review_status and proposal_id, appended at the end (no column removed or reordered);
  - existing rows (same event_id) are unchanged, apart from those two new columns, which stay empty;
  - every added row has non-empty entered_by, review_status and proposal_id;
  - every removed row has a "removed" entry for its event_id in data/events/register_changelog.csv.
Exit code 1 lists every violation. Standard library only; reads the base version with `git show`.
"""
import argparse, csv, io, subprocess, sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REGISTER = "data/events/event_register.csv"
CHANGELOG = "data/events/register_changelog.csv"
NEW_COLUMNS = ["review_status", "proposal_id"]
ADDED_REQUIRED = ["entered_by", "review_status", "proposal_id"]


def rows_of(text: str) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return list(reader.fieldnames or []), list(reader)


def check(base_text: str, head_text: str, changelog_text: str = "") -> list[str]:
    problems = []
    base_cols, base_rows = rows_of(base_text)
    head_cols, head_rows = rows_of(head_text)
    extra = head_cols[len(base_cols):]
    if head_cols[:len(base_cols)] != base_cols or any(c not in NEW_COLUMNS for c in extra) or len(set(extra)) != len(extra):
        problems.append(f"header may only append {NEW_COLUMNS} to the base columns; base {base_cols}, head {head_cols}")
        return problems
    for name, rows in (("base", base_rows), ("head", head_rows)):
        ids = [r.get("event_id", "") for r in rows]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup or not all(ids):
            problems.append(f"{name} register has duplicate or empty event_id: {dup}")
    if problems:
        return problems
    base = {r["event_id"]: r for r in base_rows}
    head = {r["event_id"]: r for r in head_rows}
    for eid in base.keys() & head.keys():
        changed = [c for c in base_cols if (base[eid].get(c) or "") != (head[eid].get(c) or "")]
        filled = [c for c in extra if (head[eid].get(c) or "").strip()]
        if changed or filled:
            problems.append(f"{eid}: existing row changed ({', '.join(changed + filled)})")
    for eid in sorted(head.keys() - base.keys()):
        missing = [c for c in ADDED_REQUIRED if not (head[eid].get(c) or "").strip()]
        if missing:
            problems.append(f"{eid}: added row needs non-empty {', '.join(missing)}")
    logged = set()
    if changelog_text.strip():
        _, log_rows = rows_of(changelog_text)
        logged = {r.get("event_id", "") for r in log_rows if (r.get("action") or "").strip() == "removed"
                  and (r.get("reason") or "").strip() and (r.get("by") or "").strip()}
    for eid in sorted(base.keys() - head.keys()):
        if eid not in logged:
            problems.append(f"{eid}: removed without a 'removed' entry (with reason and by) in {CHANGELOG}")
    return problems


def git_show(rev: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:./{path}"], cwd=PROJECT, check=True, capture_output=True, text=True).stdout


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", required=True, help="git revision of the PR base")
    a = p.parse_args(argv)
    changelog = PROJECT / CHANGELOG
    problems = check(git_show(a.base, REGISTER), (PROJECT / REGISTER).read_text(encoding="utf-8"),
                     changelog.read_text(encoding="utf-8") if changelog.exists() else "")
    for problem in problems:
        print("::error title=event_register.csv change not allowed::" + problem)
    print(f"event_register.csv vs {a.base}: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
