#!/usr/bin/env python3
"""Check a Risk Horizon output file before committing it.

Usage: python3 docs/data/validate_output.py docs/data/risk_output.json [--playbook <card_playbook.csv>]
Exit code 0 = OK, 1 = errors found. Standard library only.
"""
import csv
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

LINES = {"FICC", "ECS", "RDS", "WIS", "ITP", "Asset Services", "DAS", "DDA", "Data Services", "Consulting"}
FAMILIES = {"Credit", "Liquidity", "Market", "Operational", "Cyber", "Regulatory", "Strategic"}
STATUSES = {"scored", "news_not_scanned", "data_incomplete", "no_relevant_news"}
UNSCORED = {"news_not_scanned", "data_incomplete", "no_relevant_news"}   # shock may be null only for these
COVERAGE = {"manual_register_only", "headline_level_ai_screen"}           # snapshots[].news_coverage (Amendment F1)
ANALYSIS_FIELDS = ("so_what", "so_now_what")                 # null only while analysis_status is pending_llm / pending_review
ANALYSIS_STATUSES = {"pending_llm", "pending_review", "template", "ai_reviewed"}
_NC_PATH = Path(__file__).resolve().parents[2] / "Capstone_Project/validation/narrative_checks.py"
NC = None
if _NC_PATH.exists():                                         # word limits, banned phrases, fixed texts (standard library)
    _spec = importlib.util.spec_from_file_location("narrative_checks", _NC_PATH)
    NC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(NC)
_FC_PATH = Path(__file__).resolve().parents[2] / "Capstone_Project/validation/card_front_checks.py"
FC = None
if _FC_PATH.exists():                                         # card front limits, fixed texts, reviewed playbook (standard library)
    _fspec = importlib.util.spec_from_file_location("card_front_checks", _FC_PATH)
    FC = importlib.util.module_from_spec(_fspec); _fspec.loader.exec_module(FC)
PLAYBOOK = Path(__file__).resolve().parents[2] / "Capstone_Project/data/narratives/card_playbook.csv"
FRONT_STATUSES = {"none", "pending_review", "template", "ai_reviewed"}
FRONT_TEXT = ("front_headline", "front_what_happened", "front_so_what", "front_so_now_what", "front_action_id")


def load_playbook(path=None):
    """card_id -> reviewed playbook ({chain_short, actions}) as the export uses it, or None when not checkable."""
    path = Path(path) if path else PLAYBOOK
    if FC is None or not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = {r["card_id"]: FC.effective_playbook(r) for r in csv.DictReader(f)}
    return {k: v for k, v in rows.items() if v}


def front_errors(it, playbook):
    """Card front layer (front_* fields): published text only when reviewed, within limits and from the reviewed playbook."""
    errs = []
    fs = it.get("front_status")
    if fs is None:
        return errs
    if fs not in FRONT_STATUSES:
        return [f"front_status '{fs}' is not one of {sorted(FRONT_STATUSES)}"]
    status = it.get("status") or "scored"
    labelled = bool(it.get("front_review_label")) or bool(it.get("front_ai_fields"))
    chain = it.get("front_chain_short")
    if chain is not None:
        if not (isinstance(chain, list) and len(chain) == 3 and all(isinstance(c, str) and c.strip() for c in chain)):
            errs.append("front_chain_short must be a list of 3 labels or null")
        elif FC is not None and any(FC.words(c) > FC.CHAIN_WORDS for c in chain):
            errs.append(f"front_chain_short label over {FC.CHAIN_WORDS if FC else 6} words")
        elif playbook is not None and (playbook.get(it.get("card_id")) or {}).get("chain_short") != chain:
            errs.append("front_chain_short is not the reviewed card_playbook.csv text")
    if not isinstance(it.get("front_sources_line"), str):
        errs.append("front_sources_line must be a string")
    if fs in ("none", "pending_review"):
        if any(it.get(k) is not None for k in FRONT_TEXT):
            errs.append(f"front text published but front_status is {fs} (unreviewed front text is never published)")
        if labelled:
            errs.append(f"front_status {fs} must not carry an AI front label")
    elif fs == "template":
        if status == "scored":
            errs.append("a scored record cannot have template front text")
        if it.get("front_headline") != it.get("title"):
            errs.append("template front headline must be the card name")
        if FC is not None and it.get("front_what_happened") != FC.TEMPLATE_WHAT_HAPPENED.get(status):
            errs.append("template front what_happened differs from the fixed text")
        if any(it.get(k) is not None for k in ("front_so_what", "front_so_now_what", "front_action_id")):
            errs.append("template front has no so what / so now what")
        if labelled:
            errs.append("template front text must not be marked AI-drafted")
    elif fs == "ai_reviewed":
        if status != "scored":
            errs.append("only scored records can have AI front text")
        if FC is not None and it.get("front_review_label") != FC.FRONT_REVIEW_LABEL:
            errs.append(f"ai_reviewed front needs front_review_label '{FC.FRONT_REVIEW_LABEL}'")
        if not {"front_headline", "front_so_what", "front_so_now_what"} <= set(it.get("front_ai_fields") or []):
            errs.append("ai_reviewed front must list its fields in front_ai_fields")
        if any(not isinstance(it.get(k), str) or not it[k].strip() for k in FRONT_TEXT):
            errs.append("ai_reviewed front needs headline, what_happened, so_what, so_now_what and action_id")
        elif FC is not None:
            for k, limit, one in (("front_headline", 10, False), ("front_what_happened", 20, True), ("front_so_what", 20, True),
                                  ("front_so_now_what", FC.ACTION_WORDS, False)):
                if FC.words(it[k]) > limit or (one and FC.NC.sentences(it[k]) > 1):
                    errs.append(f"{k} exceeds {'1 sentence / ' if one else ''}{limit} words")
                if FC.NC.BANNED.search(it[k]):
                    errs.append(f"{k} contains a banned phrase")
            for k in ("front_headline", "front_so_what"):
                if FC.JARGON.search(it[k]):
                    errs.append(f"{k} contains percentiles, scores or jargon ('{FC.JARGON.search(it[k]).group(0)}')")
            if playbook is not None:
                pb = playbook.get(it.get("card_id"))
                if pb is None or pb["actions"].get(it["front_action_id"]) != it["front_so_now_what"]:
                    errs.append("front_so_now_what is not a reviewed card_playbook.csv action of this card")
    return errs


def news_display_errors(it):
    """related_news_display (display order of related_news): every item exactly once, at most 5 at the top and listed
    first (more only when more items are pinned), pinned items first, never an excluded or labelled item at the top
    unless it is pinned (cited by the reviewed card front)."""
    disp = it.get("related_news_display")
    if disp is None:
        return []
    rel = it.get("related_news") or []
    if not isinstance(disp, list) or not all(isinstance(e, dict) and isinstance(e.get("index"), int) for e in disp):
        return ["related_news_display must be a list of {index, top, ...}"]
    errs = []
    if sorted(e["index"] for e in disp) != list(range(len(rel))):
        errs.append("related_news_display must list every related_news item exactly once")
    tops = [n for n, e in enumerate(disp) if e.get("top")]
    pinned = sum(bool(e.get("pinned")) for e in disp)
    if len(tops) > max(5, pinned) or tops != list(range(len(tops))):
        errs.append("related_news_display: at most 5 top items, listed first")
    if any(e.get("top") and (e.get("excluded") or e.get("label")) and not e.get("pinned") for e in disp):
        errs.append("related_news_display: an excluded or labelled item is in the top (allowed only when pinned)")
    if any(e.get("pinned") and not e.get("top") for e in disp) or [e.get("pinned") for e in disp] != sorted((bool(e.get("pinned")) for e in disp), reverse=True):
        errs.append("related_news_display: pinned items must be top items listed first")
    return errs


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


def main(path, playbook_path=None):
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

    playbook = load_playbook(playbook_path)
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
        astatus = it.get("analysis_status")
        if astatus is not None and astatus not in ANALYSIS_STATUSES:
            errors.append(f"{tag}: analysis_status '{astatus}' is not one of {sorted(ANALYSIS_STATUSES)}")
        for k in ANALYSIS_FIELDS:
            if k in it and it[k] is None and astatus not in ("pending_llm", "pending_review"):
                errors.append(f"{tag}: {k} is null; allowed only when analysis_status is 'pending_llm' or 'pending_review'")
            elif it.get(k) is not None and not isinstance(it[k], str):
                errors.append(f"{tag}: {k} must be a string or null")
            elif it.get(k) is not None and astatus in ("pending_llm", "pending_review"):
                errors.append(f"{tag}: {k} has text but analysis_status is {astatus} (unreviewed text is never published)")
        ai_fields = set(it.get("ai_generated_fields") or [])
        if astatus == "ai_reviewed":
            if not {"so_what", "so_now_what"} <= ai_fields:
                errors.append(f"{tag}: ai_reviewed text must list so_what and so_now_what in ai_generated_fields")
            if it.get("narrative_review_label") != "AI-written, reviewed by analyst":
                errors.append(f"{tag}: ai_reviewed text needs narrative_review_label 'AI-written, reviewed by analyst'")
            if NC is not None:
                for k in ANALYSIS_FIELDS:
                    text = it.get(k) or ""
                    max_sent, max_words = NC.LIMITS[k]
                    if len(text.split()) > max_words or NC.sentences(text) > max_sent:
                        errors.append(f"{tag}: {k} exceeds {max_sent} sentences / {max_words} words")
                    if NC.BANNED.search(text):
                        errors.append(f"{tag}: {k} contains a banned phrase")
        if astatus == "template":
            if ai_fields & {"so_what", "so_now_what"}:
                errors.append(f"{tag}: template text must not be marked AI-generated")
            if NC is not None and (it.get("so_what"), it.get("so_now_what")) != (NC.TEMPLATE_SO_WHAT, NC.TEMPLATE_SO_NOW_WHAT):
                errors.append(f"{tag}: template text differs from the fixed template")
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
                    elif n.get("label") not in (None, "", "membership/onboarding"):
                        errors.append(f"{tag}: related_news[{k}] label '{n.get('label')}' is not a known label (Amendment G3)")
        ai_ev = it.get("ai_unreviewed_events")
        if ai_ev is not None and not (isinstance(ai_ev, list) and all(isinstance(x, str) for x in ai_ev)):
            errors.append(f"{tag}: ai_unreviewed_events must be a list of event ids")
        if ai_ev and it.get("ai_review_label") != "AI-classified, not reviewed":
            errors.append(f"{tag}: unreviewed AI events {ai_ev} but no 'AI-classified, not reviewed' label")
        errors.extend(f"{tag}: {e}" for e in front_errors(it, playbook))
        errors.extend(f"{tag}: {e}" for e in news_display_errors(it))
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
    args = sys.argv[1:]
    pb = None
    if "--playbook" in args:                                  # local tests: check against another card_playbook.csv
        i = args.index("--playbook"); pb = args[i + 1]; del args[i:i + 2]
    sys.exit(main(args[0] if args else "docs/data/risk_output.json", pb))
