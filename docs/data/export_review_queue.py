#!/usr/bin/env python3
"""Export the weekly review sheets as the queue for the Admin review page (docs/review.html).

Reads Capstone_Project/data/events/review/review_<Monday>.csv (the main sheet of each week, not the *_run_* copies) and
writes docs/data/review_queue.json: one item per proposed event with its title, cards, would-be shock and severity,
review tier, flags, evidence and sources. Rows that already have a decision in the sheet are exported with it, so the
page shows them as done.

    python3 docs/data/export_review_queue.py                 # all weeks
    python3 docs/data/export_review_queue.py --week 2026-11-02
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "Capstone_Project" / "data" / "events" / "review"
OUT = Path(__file__).resolve().parent / "review_queue.json"


def _json(s, default):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default


def item(r: dict, week: str) -> dict:
    sev = _json(r.get("would_be_severity"), {})
    sources = [{"headline": s.get("headline", ""), "outlet": s.get("outlet", ""), "url": s.get("url", ""),
                "tier": s.get("source_tier", ""), "scope": s.get("content_scope", "")} for s in _json(r.get("sources"), [])]
    return {"id": r["proposed_event_id"], "week": week, "title": r["title"],
            "card_ids": [c for c in (r.get("card_ids") or "").split("|") if c],
            "S": int(r["would_be_S"]) if (r.get("would_be_S") or "").isdigit() else None,
            "severity": {k: v for k, v in sev.items()} if isinstance(sev, dict) else {},
            "tier": r.get("review_tier", ""), "certainty": r.get("certainty", ""), "reach": r.get("reach", ""),
            "announced": r.get("announced_date", ""), "effect": r.get("effect_date", ""),
            "confidence": r.get("confidence", ""), "flags": _json(r.get("validate_flags"), []),
            "evidence": _json(r.get("evidence_quotes"), []), "outlets": r.get("independent_outlets", ""),
            "sources": sources, "sheet_decision": r.get("decision", ""), "sheet_reviewer": r.get("reviewer", "")}


def build(weeks=None) -> dict:
    items = []
    for p in sorted(REVIEW.glob("review_*.csv")):
        m = re.fullmatch(r"review_(\d{4}-\d{2}-\d{2})\.csv", p.name)
        if not m or (weeks and m.group(1) not in weeks):
            continue
        with p.open(encoding="utf-8", newline="") as f:
            items += [item(r, m.group(1)) for r in csv.DictReader(f)]
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "Capstone_Project/data/events/review/review_<Monday>.csv",
            "weeks": sorted({i["week"] for i in items}, reverse=True), "items": items}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", action="append")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    data = build(a.week)
    a.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(data['items'])} queue items, weeks {data['weeks']} -> {a.out}")


if __name__ == "__main__":
    main()
