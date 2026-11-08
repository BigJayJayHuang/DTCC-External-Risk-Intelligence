"""Group relevant classifier candidates into proposed events and write a human review sheet.

    python -m validation.review_sheet --candidates <candidates.csv> --week 2026-11-02 --out data/events/review/review_2026-11-02.csv

Grouping (simple, explainable): two candidates describe the same occurrence when
  (1) their card_ids overlap, (2) their announced_dates are at most 2 days apart, and
  (3) the word overlap of title + summary (lower-case words of 3+ letters, minus stop words) has Jaccard >= 0.25.
Groups are the connected components of that pairwise relation.

Per proposed event: union of card_ids; the highest model certainty and reach among members; earliest announced_date;
the effect_date of the most confident member; all sources and evidence quotes. The existing event_scoring.validate()
is then run once on the combined sources, so two or more independent outlets may lift the single-source certainty
cap exactly as the rubric allows ("certainty before" = best single-source checked value; "after" = combined).
Would-be S for the week comes from event_scoring.event_score (rubric v1.2); would-be severity = S x the card's
final16 V as of that week's Friday. review_tier = "required" if S >= 4 or any severity >= 6, else "auto".
Reads only; never writes the event register.
"""
import argparse, csv, hashlib, json, re
from datetime import date, timedelta
from pathlib import Path

from . import event_scoring as E
from .final16_vulnerability import get_v
from .llm_classifier import MAJOR, PROJECT, prompt_parts_v13, PROMPT_V14

STOP = set("the and for with from after amid are its this that new says said into over amid than more has have was were will its "
           "his her their they them out about what when where which who why how but not all any can may could".split())
JACCARD = 0.25
MAX_DAYS = 2
TIER_ORDER = ["regulator", "dtcc", "official", "issuer_filing", "major_media", "other"]
FIELDS = ["proposed_event_id", "title", "card_ids", "certainty", "certainty_before_grouping", "reach", "reach_basis", "announced_date",
          "effect_date", "would_be_S", "would_be_severity", "review_tier", "same_as_event_id", "stage", "named_participants",
          "independent_outlets", "sources", "evidence_quotes", "confidence", "validate_flags", "candidate_ids", "prompt_version", "model",
          "decision", "reviewer", "corrected_card_ids", "corrected_certainty", "corrected_reach", "reviewer_notes"]


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in STOP}


def same_occurrence(a: dict, b: dict) -> bool:
    if not set(a["card_ids"]) & set(b["card_ids"]):
        return False
    if abs(date.fromisoformat(a["announced_date"]) - date.fromisoformat(b["announced_date"])) > timedelta(days=MAX_DAYS):
        return False
    wa, wb = words(a["title"] + " " + a["summary"]), words(b["title"] + " " + b["summary"])
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= JACCARD


def group(cands: list[dict]) -> list[list[dict]]:
    parent = list(range(len(cands)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if same_occurrence(cands[i], cands[j]):
                parent[find(i)] = find(j)
    groups = {}
    for i, c in enumerate(cands):
        groups.setdefault(find(i), []).append(c)
    return [sorted(g, key=lambda c: -c["confidence"]) for g in groups.values()]


def load_candidates(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            text = (PROJECT / r["article_file"]).read_text(encoding="utf-8") if r.get("article_file") and (PROJECT / r["article_file"]).exists() else ""
            out.append({"candidate_id": r["event_id"], "title": r["title"], "summary": r["summary"], "card_ids": r["card_ids"].split("|"),
                        "certainty": int(r["certainty"]), "original_certainty": int(r["original_certainty"]), "reach": int(r["reach"]),
                        "original_reach": int(r["original_reach"]), "reach_basis": r["reach_basis"],
                        "named_participants": [p for p in r["named_participants"].split("|") if p], "announced_date": r["announced_date"],
                        "effect_date": r["effect_date"], "stage": int(r["stage"]) if r["stage"] not in ("", "None") else None,
                        "source_tier": r["source_tier"], "outlet": r["outlet"], "url": r["url"], "content_scope": r["content_scope"],
                        "headline": text.split("\n", 1)[0] if text else "", "text": text, "same_as_event_id": r["same_as_event_id"],
                        "evidence_quotes": json.loads(r["evidence_quotes"]), "confidence": float(r["llm_confidence"]),
                        "flags": json.loads(r["validation_reasons"]), "prompt_version": r["prompt_version"], "model": r["model_id"]})
    return out


def proposed_event(members: list[dict], week: date, catalog: set[str], major: set[str]) -> dict:
    rep = members[0]
    cards = sorted({c for m in members for c in m["card_ids"]}, key=lambda c: (-sum(c in m["card_ids"] for m in members), c))
    outlets = {}
    for m in members:
        outlets.setdefault(m["outlet"], m["source_tier"])
    quotes = list(dict.fromkeys(q for m in members for q in m["evidence_quotes"]))
    stage = max((m["stage"] for m in members if m["stage"] is not None), default=None) if "XE-MEMBER" in cards else None
    best_reach = max(members, key=lambda m: m["original_reach"])
    event = E.Event(event_id="proposed", card_ids=cards, title=rep["title"], announced_date=date.fromisoformat(min(m["announced_date"] for m in members)),
                    effect_date=date.fromisoformat(rep["effect_date"]), certainty=max(m["original_certainty"] for m in members),
                    reach=best_reach["original_reach"], evidence_quotes=quotes,
                    sources=[{"url": m["url"], "outlet": m["outlet"], "tier": m["source_tier"]} for m in members],
                    llm_confidence=rep["confidence"], stage=stage, named_participants=sorted({p for m in members for p in m["named_participants"]}),
                    reach_basis=best_reach["reach_basis"])
    E.validate(event, [m["text"] for m in members], catalog, major)          # unchanged rubric checks on the combined sources
    scored = E.event_score(event, week)
    S = scored["S"]
    friday = (week + timedelta(days=4)).isoformat()
    severity = {}
    for c in event.card_ids:
        V = get_v(c, friday).get("V")
        severity[c] = {"V": V, "severity": S * V if S is not None and V is not None else None}
    required = (S is not None and S >= 4) or any((v["severity"] or 0) >= 6 for v in severity.values())
    ids = sorted(m["candidate_id"] for m in members)
    return {"proposed_event_id": "PE-" + week.isoformat() + "-" + hashlib.sha256("|".join(ids).encode()).hexdigest()[:8],
            "title": rep["title"], "card_ids": "|".join(event.card_ids), "certainty": event.certainty,
            "certainty_before_grouping": max(m["certainty"] for m in members), "reach": event.reach, "reach_basis": event.reach_basis,
            "announced_date": event.announced_date.isoformat(), "effect_date": event.effect_date.isoformat(),
            "would_be_S": "" if S is None else S, "would_be_severity": json.dumps(severity), "review_tier": "required" if required else "auto",
            "same_as_event_id": "|".join(sorted({m["same_as_event_id"] for m in members if m["same_as_event_id"]})),
            "stage": "" if event.stage is None else event.stage, "named_participants": "|".join(event.named_participants),
            "independent_outlets": len(outlets),
            "sources": json.dumps([{"outlet": m["outlet"], "url": m["url"], "content_scope": m["content_scope"], "source_tier": m["source_tier"],
                                    "headline": m["headline"], "evidence_quotes": m["evidence_quotes"], "item_flags": m["flags"]} for m in members],
                                  ensure_ascii=False),
            "evidence_quotes": json.dumps(quotes, ensure_ascii=False), "confidence": rep["confidence"],
            "validate_flags": json.dumps(event.review_reasons + (["S >= 4: human check before publishing"] if S is not None and S >= 4 else []),
                                         ensure_ascii=False),
            "candidate_ids": "|".join(ids), "prompt_version": rep["prompt_version"], "model": rep["model"],
            "decision": "", "reviewer": "", "corrected_card_ids": "", "corrected_certainty": "", "corrected_reach": "", "reviewer_notes": ""}


def build(candidates: Path, week: date) -> list[dict]:
    _, _, catalog, _ = prompt_parts_v13(PROMPT_V14, "v1.4")
    with MAJOR.open(encoding="utf-8-sig", newline="") as f:
        major = {r["name"] for r in csv.DictReader(f) if r.get("name")}
    rows = [proposed_event(g, week, catalog, major) for g in group(load_candidates(candidates))]
    return sorted(rows, key=lambda r: (-r["confidence"], r["proposed_event_id"]))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--week", type=date.fromisoformat, required=True, help="Monday of the scoring week")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.week.weekday() != 0:
        raise SystemExit("--week must be a Monday")
    rows = build(a.candidates, a.week)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x", encoding="utf-8", newline="") as f:          # never overwrite a sheet that may hold decisions
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    print(json.dumps({"proposed_events": len(rows), "required": sum(r["review_tier"] == "required" for r in rows), "out": str(a.out)}))


if __name__ == "__main__":
    main()
