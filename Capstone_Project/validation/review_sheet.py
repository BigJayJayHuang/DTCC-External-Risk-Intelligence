"""Group relevant classifier candidates into proposed events and write a human review sheet.

    python -m validation.review_sheet --candidates <candidates.csv> --week 2026-11-02 --out data/events/review/review_2026-11-02.csv

Grouping (simple, explainable): two candidates describe the same occurrence when
  (1) their card_ids overlap, (2) their announced_dates are at most 2 days apart, and
  (3) the word overlap of title + summary (lower-case words of 3+ letters, minus stop words) has Jaccard >= 0.25.
Groups are the connected components of that pairwise relation.
market_move items are grouped per card instead (Amendment D): for each card, its market_move items whose
announced_dates chain within 2 days form one proposed event for that card alone, whatever the wording. An item
naming several cards joins one such event per card, so a multi-card item never merges different cards' groups.
Syndication: sources from different outlets whose headlines have word Jaccard >= 0.8 count as one source when
validate() counts independent outlets; the number collapsed is reported per event.
Context rule (Amendment D): on an indicator card, an event of type market_move is context; it gets no would-be
severity, does not count toward review_tier, and is written to the context-news file instead.
Checks after validate() (prompt v1.6 fields; older candidate files simply skip them):
  - geography = non_us: dropped before grouping and logged to filtered_non_us.csv;
  - every item has same_as_event_id and new_information = false: review_tier "duplicate" (never promoted; its items are
    listed as related news on its cards);
  - one independent source, headline-only, event_type operational or cyber: date flag "date_unverified";
  - an item's announced_date more than 14 days from its feed published date: date flag "date_mismatch", and
    review_tier "date_review" (kept out of the week's tiering until reviewed).
FICC-GSD-11 gate (Amendment E5), after the non-US filter and before grouping: the card stays on an item only if the
source text the model saw (headline, summary or text) names Treasury/Treasuries, repo, basis trade, SOFR, sponsored or
agent clearing. Otherwise the card is removed (an item left with no card is dropped) and the removal is logged.

Per proposed event: union of card_ids; the highest model certainty and reach among members; earliest announced_date;
the effect_date of the most confident member; all sources and evidence quotes. The existing event_scoring.validate()
is then run once on the combined sources, so two or more independent outlets may lift the single-source certainty
cap exactly as the rubric allows ("certainty before" = best single-source checked value; "after" = combined).
Would-be S for the week comes from event_scoring.event_score (rubric v1.2); would-be severity = S x the card's
final16 V as of that week's Friday. review_tier = "required" if S >= 4 or any severity >= 6, else "auto".
Reads only; never writes the event register.
"""
import argparse, csv, hashlib, json, re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from . import event_scoring as E
from .final16_vulnerability import get_v
from .llm_classifier import MAJOR, PROJECT, prompt_parts_v13, PROMPT_V14

STOP = set("the and for with from after amid are its this that new says said into over amid than more has have was were will its "
           "his her their they them out about what when where which who why how but not all any can may could".split())
JACCARD = 0.25
SYNDICATION_JACCARD = 0.8
MAX_DAYS = 2
INDICATOR_CARDS = {"FICC-GSD-01", "FICC-GSD-02", "FICC-MBSD-01", "ECS-NSCC-LIQ", "ECS-NSCC-03", "XE-MEMBER"}   # Amendment D
CONTEXT_NEWS = PROJECT / "data/events/context_news.csv"
CONTEXT_FIELDS = ["week", "card_id", "title", "outlet", "url", "event_type", "proposed_event_id"]
TIER_ORDER = ["regulator", "dtcc", "official", "issuer_filing", "major_media", "other"]
DATE_MISMATCH_DAYS = 14
HEADLINE_SCOPES = {"headline_only", "headline_snippet"}
GATED_CARD = "FICC-GSD-11"   # Amendment E5
GATE_TERMS = re.compile(r"\b(treasury|treasuries|repos?|basis[- ]trades?|sofr|sponsored|agent[- ]clearing)\b", re.I)
GATE_FLAG = "FICC-GSD-11 removed: no Treasury, repo, basis trade, SOFR, sponsored or agent clearing term in the source text"
GATE_FIELDS = ["candidate_id", "title", "card_ids_before", "card_ids_after", "action", "outlet", "url"]
FILTERED_FIELDS = ["candidate_id", "title", "card_ids", "event_type", "geography", "outlet", "url", "announced_date", "published_date"]
FIELDS = ["proposed_event_id", "title", "event_type", "card_ids", "scored_card_ids", "context_card_ids", "certainty", "certainty_before_grouping",
          "reach", "reach_basis", "announced_date", "effect_date", "would_be_S", "would_be_severity", "review_tier", "geography", "new_information", "date_flags",
          "same_as_event_id", "stage",
          "named_participants", "independent_outlets", "syndication_collapsed", "member_event_types", "sources", "evidence_quotes", "confidence", "validate_flags", "candidate_ids", "prompt_version", "model",
          "decision", "reviewer", "corrected_card_ids", "corrected_certainty", "corrected_reach", "reviewer_notes"]


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in STOP}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


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


def market_move_groups(cands: list[dict]) -> list[list[dict]]:
    """Per card: market_move items whose announced_dates chain within MAX_DAYS; each member restricted to that card."""
    out = []
    for card in sorted({c for m in cands for c in m["card_ids"]}):
        items = sorted((m for m in cands if card in m["card_ids"]), key=lambda m: (m["announced_date"], m["candidate_id"]))
        current = []
        for m in items:
            if current and date.fromisoformat(m["announced_date"]) - date.fromisoformat(current[-1]["announced_date"]) > timedelta(days=MAX_DAYS):
                out.append(current); current = []
            current.append({**m, "card_ids": [card]})
        if current:
            out.append(current)
    return [sorted(g, key=lambda c: -c["confidence"]) for g in out]


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
                        "flags": json.loads(r["validation_reasons"]), "prompt_version": r["prompt_version"], "model": r["model_id"],
                        "event_type": r.get("event_type") or "", "geography": r.get("geography") or "",
                        "new_information": {"True": True, "False": False}.get(r.get("new_information") or ""),
                        "published_date": r.get("published_date") or ""})
    return out


def gate_text(c: dict) -> str:
    """The source text the model saw (the saved article file: headline, then summary or text); the model's own title and
    summary only when no article file was saved."""
    return c["text"] if c["text"] else c["title"] + "\n" + c["summary"]


def card_gate(cands: list[dict]) -> tuple[list[dict], list[dict]]:
    """Amendment E5. Returns (kept candidates, log rows)."""
    kept, log = [], []
    for c in cands:
        if GATED_CARD not in c["card_ids"] or GATE_TERMS.search(gate_text(c)):
            kept.append(c); continue
        after = [x for x in c["card_ids"] if x != GATED_CARD]
        log.append({"candidate_id": c["candidate_id"], "title": c["headline"] or c["title"], "card_ids_before": "|".join(c["card_ids"]),
                    "card_ids_after": "|".join(after), "action": "card_removed" if after else "item_dropped", "outlet": c["outlet"], "url": c["url"]})
        if after:
            kept.append({**c, "card_ids": after, "flags": c["flags"] + [GATE_FLAG]})
    return kept, log


def syndication_sources(members: list[dict]) -> tuple[list[dict], int]:
    """One source per cluster of near-identical headlines from different outlets; returns (kept members, collapsed)."""
    kept = []
    for m in members:
        hw = words(m["headline"] or m["title"])
        if not any(k["outlet"] != m["outlet"] and jaccard(hw, words(k["headline"] or k["title"])) >= SYNDICATION_JACCARD for k in kept):
            kept.append(m)
    return kept, len(members) - len(kept)


def proposed_event(members: list[dict], week: date, catalog: set[str], major: set[str]) -> tuple[dict, list[dict]]:
    rep = members[0]
    types = Counter(m["event_type"] for m in members if m["event_type"])
    top = types.most_common()
    event_type = rep["event_type"] if not top or (len(top) > 1 and top[0][1] == top[1][1]) else top[0][0]
    cards = sorted({c for m in members for c in m["card_ids"]}, key=lambda c: (-sum(c in m["card_ids"] for m in members), c))
    independent, collapsed = syndication_sources(members)
    outlets = {}
    for m in independent:
        outlets.setdefault(m["outlet"], m["source_tier"])
    quotes = list(dict.fromkeys(q for m in members for q in m["evidence_quotes"]))
    stage = max((m["stage"] for m in members if m["stage"] is not None), default=None) if "XE-MEMBER" in cards else None
    best_reach = max(members, key=lambda m: m["original_reach"])
    event = E.Event(event_id="proposed", card_ids=cards, title=rep["title"], announced_date=date.fromisoformat(min(m["announced_date"] for m in members)),
                    effect_date=date.fromisoformat(rep["effect_date"]), certainty=max(m["original_certainty"] for m in members),
                    reach=best_reach["original_reach"], evidence_quotes=quotes,
                    sources=[{"url": m["url"], "outlet": m["outlet"], "tier": m["source_tier"]} for m in independent],
                    llm_confidence=rep["confidence"], stage=stage, named_participants=sorted({p for m in members for p in m["named_participants"]}),
                    reach_basis=best_reach["reach_basis"])
    E.validate(event, [m["text"] for m in members], catalog, major)          # unchanged rubric checks on the combined sources
    scored = E.event_score(event, week)
    S = scored["S"]
    friday = (week + timedelta(days=4)).isoformat()
    context = [c for c in event.card_ids if c in INDICATOR_CARDS and event_type == "market_move"]
    scored = [c for c in event.card_ids if c not in context]
    severity = {}
    for c in scored:
        V = get_v(c, friday).get("V")
        severity[c] = {"V": V, "severity": S * V if S is not None and V is not None else None}
    if not scored:
        tier = "context"
    else:
        tier = "required" if (S is not None and S >= 4) or any((v["severity"] or 0) >= 6 for v in severity.values()) else "auto"
    # checks after validate()
    flags = []
    if len(independent) == 1 and all(m["content_scope"] in HEADLINE_SCOPES for m in members) and event_type in ("operational", "cyber"):
        flags.append("date_unverified")
    if any(m["published_date"] and abs(date.fromisoformat(m["announced_date"]) - date.fromisoformat(m["published_date"])) > timedelta(days=DATE_MISMATCH_DAYS)
           for m in members):
        flags.append("date_mismatch")
    duplicate = all(m["same_as_event_id"] for m in members) and all(m["new_information"] is False for m in members)
    if duplicate:
        tier = "duplicate"
    elif "date_mismatch" in flags:
        tier = "date_review"
    new_info = "true" if any(m["new_information"] is True for m in members) else ("false" if duplicate else "")
    geography = "|".join(sorted({m["geography"] for m in members if m["geography"]}))
    ids = sorted(m["candidate_id"] for m in members)
    key = "|".join(ids) + ("#" + "|".join(event.card_ids) if event_type == "market_move" else "")   # per-card market-move events
    pid = "PE-" + week.isoformat() + "-" + hashlib.sha256(key.encode()).hexdigest()[:8]
    related_cards = event.card_ids if duplicate else context      # duplicates are related news on every card
    ctx_rows = [{"week": week.isoformat(), "card_id": c, "title": m["headline"] or m["title"], "outlet": m["outlet"], "url": m["url"],
                 "event_type": event_type, "proposed_event_id": pid} for c in related_cards for m in members]
    return {"proposed_event_id": pid, "title": rep["title"], "event_type": event_type, "card_ids": "|".join(event.card_ids),
            "scored_card_ids": "|".join(scored), "context_card_ids": "|".join(context), "certainty": event.certainty,
            "certainty_before_grouping": max(m["certainty"] for m in members), "reach": event.reach, "reach_basis": event.reach_basis,
            "announced_date": event.announced_date.isoformat(), "effect_date": event.effect_date.isoformat(),
            "would_be_S": "" if S is None else S, "would_be_severity": json.dumps(severity), "review_tier": tier,
            "geography": geography, "new_information": new_info, "date_flags": "|".join(flags),
            "same_as_event_id": "|".join(sorted({m["same_as_event_id"] for m in members if m["same_as_event_id"]})),
            "stage": "" if event.stage is None else event.stage, "named_participants": "|".join(event.named_participants),
            "independent_outlets": len(outlets), "syndication_collapsed": collapsed,
            "member_event_types": json.dumps(dict(types)),
            "sources": json.dumps([{"outlet": m["outlet"], "url": m["url"], "content_scope": m["content_scope"], "source_tier": m["source_tier"],
                                    "headline": m["headline"], "evidence_quotes": m["evidence_quotes"], "item_flags": m["flags"]} for m in members],
                                  ensure_ascii=False),
            "evidence_quotes": json.dumps(quotes, ensure_ascii=False), "confidence": rep["confidence"],
            "validate_flags": json.dumps(event.review_reasons + (["S >= 4: human check before publishing"] if S is not None and S >= 4 else [])
                                         + ([GATE_FLAG] if any(GATE_FLAG in m["flags"] for m in members) else []), ensure_ascii=False),
            "candidate_ids": "|".join(ids), "prompt_version": rep["prompt_version"], "model": rep["model"],
            "decision": "", "reviewer": "", "corrected_card_ids": "", "corrected_certainty": "", "corrected_reach": "", "reviewer_notes": ""}, ctx_rows


def build(candidates: Path, week: date, filtered_out: Path | None = None, gate_out: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Returns (review-sheet rows sorted by confidence, context-news rows). Non-US candidates are dropped first and,
    when filtered_out is given, logged there; then the FICC-GSD-11 gate runs, logged to gate_out when given."""
    _, _, catalog, _ = prompt_parts_v13(PROMPT_V14, "v1.4")
    with MAJOR.open(encoding="utf-8-sig", newline="") as f:
        major = {r["name"] for r in csv.DictReader(f) if r.get("name")}
    cands = load_candidates(candidates)
    non_us = [c for c in cands if c["geography"] == "non_us"]
    cands = [c for c in cands if c["geography"] != "non_us"]
    if filtered_out is not None:
        filtered_out.parent.mkdir(parents=True, exist_ok=True)
        with filtered_out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FILTERED_FIELDS, extrasaction="ignore", lineterminator="\n"); w.writeheader()
            w.writerows({**c, "card_ids": "|".join(c["card_ids"])} for c in non_us)
    cands, gate_log = card_gate(cands)
    if gate_out is not None:
        gate_out.parent.mkdir(parents=True, exist_ok=True)
        with gate_out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=GATE_FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(gate_log)
    moves = [c for c in cands if c["event_type"] == "market_move"]
    others = [c for c in cands if c["event_type"] != "market_move"]
    built = [proposed_event(g, week, catalog, major) for g in market_move_groups(moves) + group(others)]
    rows = sorted((r for r, _ in built), key=lambda r: (-r["confidence"], r["proposed_event_id"]))
    return rows, [c for _, ctx in built for c in ctx]


def append_context(path: Path, rows: list[dict]) -> int:
    """Append context-news rows, skipping (week, card_id, url) already present. Never touches the event register."""
    existing = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            existing = list(csv.DictReader(f))
    seen = {(r["week"], r["card_id"], r["url"]) for r in existing}
    new = [r for r in rows if (r["week"], r["card_id"], r["url"]) not in seen and not seen.add((r["week"], r["card_id"], r["url"]))]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if existing else "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CONTEXT_FIELDS, lineterminator="\n")
        if not existing:
            w.writeheader()
        w.writerows(new)
    return len(new)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--week", type=date.fromisoformat, required=True, help="Monday of the scoring week")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--context-out", type=Path, default=CONTEXT_NEWS)
    p.add_argument("--filtered-out", type=Path, help="default: filtered_non_us.csv next to --out")
    a = p.parse_args(argv)
    if a.week.weekday() != 0:
        raise SystemExit("--week must be a Monday")
    rows, ctx = build(a.candidates, a.week, a.filtered_out or a.out.parent / f"filtered_non_us_{a.week.isoformat()}.csv",
                      a.out.parent / f"card_gate_{a.week.isoformat()}.csv")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x", encoding="utf-8", newline="") as f:          # never overwrite a sheet that may hold decisions
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    added = append_context(a.context_out, ctx)
    print(json.dumps({"proposed_events": len(rows), "tiers": dict(Counter(r["review_tier"] for r in rows)), "out": str(a.out),
                      "context_rows_added": added, "context_out": str(a.context_out)}))


if __name__ == "__main__":
    main()
