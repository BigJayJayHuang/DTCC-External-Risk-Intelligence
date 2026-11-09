#!/usr/bin/env python3
"""Check a Risk Horizon output file before committing it.

Usage: python3 docs/data/validate_output.py docs/data/risk_output.json
Exit code 0 = OK, 1 = errors found. Standard library only.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

LINES = {"FICC", "ECS", "RDS", "WIS", "ITP", "Asset Services", "DAS", "DDA", "Data Services", "Consulting"}
FAMILIES = {"Credit", "Liquidity", "Market", "Operational", "Cyber", "Regulatory", "Strategic"}
STATUSES = {"scored", "news_not_scanned", "data_incomplete", "no_relevant_news"}
UNSCORED = {"news_not_scanned", "data_incomplete", "no_relevant_news"}   # shock may be null only for these
COVERAGE = {"manual_register_only", "headline_level_ai_screen"}           # snapshots[].news_coverage (Amendment F1)
ANALYSIS_FIELDS = ("so_what", "so_now_what")                 # null only while analysis_status = "pending_llm"
# Business-line rows per card (scoring v1.3), including the FICC and ECS rows of cross-entity (XE-) cards
CARD_LINES = Path(__file__).resolve().parents[2] / "Capstone_Project/results/scoring/v1.3_indicator/config/card_lines.csv"


def load_card_lines():
    if not CARD_LINES.exists():
        return None
    rows = {}
    with CARD_LINES.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rid = r["card_id"].lower() + (f"-{r['id_suffix']}" if r["id_suffix"] else "")
            rows[(r["card_id"], r["business_line"])] = rid
    return rows


def is_date(s):
    try:
        datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def score_ok(v, allow_none=False):
    if v is None:
        return allow_none
    return isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5


def main(path):
    errors, warnings = [], []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    snaps = data.get("snapshots", [])
    snap_ids = set()
    for n, s in enumerate(snaps):
        if not s.get("id"):
            errors.append(f"snapshots[{n}]: missing id")
        elif not is_date(s.get("date", s["id"])):
            errors.append(f"snapshots[{n}]: date is not ISO (YYYY-MM-DD)")
        snap_ids.add(s.get("id"))
        if "news_coverage" in s and s["news_coverage"] not in COVERAGE:
            errors.append(f"snapshots[{n}]: news_coverage '{s['news_coverage']}' is not one of {sorted(COVERAGE)}")
    coverage = {s.get("id"): s.get("news_coverage", "manual_register_only") for s in snaps}

    card_lines = load_card_lines()
    if card_lines is None:
        warnings.append(f"{CARD_LINES} not found: card/business-line rows not checked")
    seen = set()
    for n, it in enumerate(data.get("items", [])):
        tag = f"items[{n}] ({it.get('id', '?')})"
        for k in ("id", "snapshot", "business_line", "title", "risk_family"):
            if not it.get(k):
                errors.append(f"{tag}: missing {k}")
        if it.get("snapshot") and it["snapshot"] not in snap_ids:
            warnings.append(f"{tag}: snapshot {it['snapshot']} not listed in snapshots (page will add it)")
        if it.get("business_line") and it["business_line"] not in LINES:
            errors.append(f"{tag}: business_line '{it['business_line']}' is not one of the 10 lines")
        if it.get("risk_family") and it["risk_family"] not in FAMILIES:
            warnings.append(f"{tag}: risk_family '{it['risk_family']}' is not a standard family")
        status = it.get("status")
        if status is not None and status not in STATUSES:
            errors.append(f"{tag}: status '{status}' is not one of {sorted(STATUSES)}")
        if not score_ok(it.get("shock"), allow_none=status in UNSCORED):
            errors.append(f"{tag}: shock must be an integer 1-5" + (" (null only when status is news_not_scanned or data_incomplete)"
                                                                     if it.get("shock") is None else ""))
        if status in UNSCORED and it.get("shock") is not None:
            errors.append(f"{tag}: status {status} must have shock null")
        cov = coverage.get(it.get("snapshot"), "manual_register_only")
        if status == "no_relevant_news" and cov != "headline_level_ai_screen":       # Amendment F2/F3
            errors.append(f"{tag}: no_relevant_news only in a week with news_coverage headline_level_ai_screen (this week: {cov})")
        if status == "news_not_scanned" and cov == "headline_level_ai_screen":
            errors.append(f"{tag}: news_not_scanned in a week the news screen covered; expected no_relevant_news")
        if status == "no_relevant_news" and it.get("show_on_main"):
            errors.append(f"{tag}: no_relevant_news must have show_on_main false")
        for k in ANALYSIS_FIELDS:
            if k in it and it[k] is None and it.get("analysis_status") != "pending_llm":
                errors.append(f"{tag}: {k} is null; allowed only when analysis_status is 'pending_llm'")
            elif it.get(k) is not None and not isinstance(it[k], str):
                errors.append(f"{tag}: {k} must be a string or null")
        if card_lines is not None and it.get("card_id"):
            want = card_lines.get((it["card_id"], it.get("business_line")))
            if want is None:
                errors.append(f"{tag}: card {it['card_id']} has no '{it.get('business_line')}' row in card_lines.csv")
            elif it.get("id") != want:
                errors.append(f"{tag}: id should be '{want}' for card {it['card_id']} on {it.get('business_line')}")
        if not score_ok(it.get("vulnerability"), allow_none=True):
            errors.append(f"{tag}: vulnerability must be an integer 1-5 or null (never 0)")
        if it.get("updated_at") and not is_date(it["updated_at"]):
            errors.append(f"{tag}: updated_at is not ISO 8601")
        key = (it.get("id"), it.get("snapshot"))
        if key in seen:
            errors.append(f"{tag}: duplicate id within snapshot {it.get('snapshot')}")
        seen.add(key)
        rel = it.get("related_news")
        if rel is not None:
            if not isinstance(rel, list):
                errors.append(f"{tag}: related_news must be a list")
            else:
                for k, n in enumerate(rel):
                    if not isinstance(n, dict) or not n.get("title") or not str(n.get("url", "")).startswith(("https://", "http://")):
                        errors.append(f"{tag}: related_news[{k}] needs a title and an http(s) url")
        ai_ev = it.get("ai_unreviewed_events")
        if ai_ev is not None and not (isinstance(ai_ev, list) and all(isinstance(x, str) for x in ai_ev)):
            errors.append(f"{tag}: ai_unreviewed_events must be a list of event ids")
        if ai_ev and it.get("ai_review_label") != "AI-classified, not reviewed":
            errors.append(f"{tag}: unreviewed AI events {ai_ev} but no 'AI-classified, not reviewed' label")
        tr = it.get("transmission")
        if tr is not None and not all(k in tr for k in ("event", "mechanism", "dtcc_process")):
            warnings.append(f"{tag}: transmission should have event, mechanism, dtcc_process")

    for line in data.get("lines", {}):
        if line not in LINES:
            errors.append(f"lines: '{line}' is not one of the 10 lines")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(data.get('items', []))} items, {len(snaps)} snapshots: "
          f"{'OK' if not errors else str(len(errors)) + ' error(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/risk_output.json"))
