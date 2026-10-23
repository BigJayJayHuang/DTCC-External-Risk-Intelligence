"""
Event scoring and ranking (rubric v1.2) for the DTCC Risk Horizon engine.

The LLM only classifies news (cards, certainty, reach, dates, stage, evidence).
Everything below is deterministic: same inputs -> same scores.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

RUBRIC_VERSION = "event-rubric-v1.2"

# Total (0-6) -> shock score S (1-5)
TOTAL_TO_S = {6: 5, 5: 4, 4: 3, 3: 2}

ACTIVE_AFTER_EFFECT_DAYS = 84          # event stays active 12 weeks after its effect date
LLM_CONFIDENCE_REVIEW = 0.7            # below this -> human review
HUMAN_REVIEW_S = 4                     # S >= 4 is always checked by a person before publishing
PRIMARY_TIERS = {"regulator", "dtcc", "issuer_filing", "official"}
MIN_INDEPENDENT_SOURCES_FOR_FINAL = 2  # certainty 2 needs a primary source or >= 2 independent outlets

# Escalation floors for the "Member stress / default" card (stage set by the LLM, checked by a person)
# 1 = stress signal (downgrade, big loss); 2 = DTCC action (Watch List, special charge)
# 3 = default / DTCC ceases to act; 4 = loss allocation to other members
STAGE_FLOOR = {3: 4, 4: 5}


@dataclass
class Event:
    event_id: str
    card_ids: list[str]
    title: str
    announced_date: date
    effect_date: date
    certainty: int                       # 0 / 1 / 2 from the LLM
    reach: int                           # 0 / 1 / 2 from the LLM
    evidence_quotes: list[str]
    sources: list[dict]                  # [{"url":..., "outlet":..., "tier": "regulator|dtcc|issuer_filing|official|major_media|other"}]
    llm_confidence: float = 1.0
    stage: int | None = None             # only for escalation cards
    named_participants: list[str] = field(default_factory=list)
    reach_basis: str = ""                # "market_wide" | "business_line" | "major_participant" | "group" | "single"
    updated_date: date | None = None
    review_reasons: list[str] = field(default_factory=list)


def week_bounds(week_start: date) -> tuple[date, date]:
    """Scoring week = Monday..Friday, labelled by Monday."""
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    return week_start, week_start + timedelta(days=4)


def timing_level(effect_date: date, week_start: date) -> int:
    """2 = within 4 weeks ahead or past; 1 = 5-12 weeks; 0 = more than 12 weeks."""
    ws, we = week_bounds(week_start)
    if ws <= effect_date <= we:
        days = 0
    elif effect_date > we:
        days = (effect_date - we).days
    else:
        days = (ws - effect_date).days
    weeks = math.ceil(days / 7)
    if weeks <= 4:
        return 2
    if weeks <= 12:
        return 1
    return 0


def is_active(ev: Event, week_start: date) -> bool:
    ws, we = week_bounds(week_start)
    return ev.announced_date <= we and ws <= ev.effect_date + timedelta(days=ACTIVE_AFTER_EFFECT_DAYS)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def validate(ev: Event, article_texts: list[str], catalog: set[str], major_participants: set[str]) -> Event:
    """Hard checks on LLM output. Adjusts levels conservatively and records review reasons."""
    reasons = []
    if ev.certainty not in (0, 1, 2) or ev.reach not in (0, 1, 2):
        raise ValueError(f"{ev.event_id}: levels must be 0, 1 or 2")

    unknown = [c for c in ev.card_ids if c not in catalog]
    if unknown or not ev.card_ids:
        reasons.append(f"unknown or missing card ids: {unknown}")
        ev.card_ids = [c for c in ev.card_ids if c in catalog]

    corpus = _norm(" ".join(article_texts))
    if not ev.evidence_quotes or any(_norm(q) not in corpus for q in ev.evidence_quotes):
        reasons.append("evidence quote not found verbatim in source text")

    if ev.certainty == 2:
        primary = any(s.get("tier") in PRIMARY_TIERS for s in ev.sources)
        outlets = {s.get("outlet") for s in ev.sources if s.get("outlet")}
        if not primary and len(outlets) < MIN_INDEPENDENT_SOURCES_FOR_FINAL:
            ev.certainty = 1
            reasons.append("certainty capped at 1: no primary source and fewer than 2 independent outlets")

    if ev.reach == 2 and ev.reach_basis == "major_participant":
        if not any(p in major_participants for p in ev.named_participants):
            ev.reach = 1
            reasons.append("reach capped at 1: named firm not on the major-participant list")

    if ev.llm_confidence < LLM_CONFIDENCE_REVIEW:
        reasons.append(f"LLM confidence {ev.llm_confidence:.2f} below {LLM_CONFIDENCE_REVIEW}")

    if ev.stage is not None and ev.stage not in (1, 2, 3, 4):
        reasons.append(f"invalid stage {ev.stage}")
        ev.stage = None

    ev.review_reasons = reasons
    return ev


def event_score(ev: Event, week_start: date) -> dict:
    """Shock score S (1-5) for one event in one scoring week."""
    if not is_active(ev, week_start):
        return {"event_id": ev.event_id, "active": False, "S": None}
    t = timing_level(ev.effect_date, week_start)
    total = ev.certainty + ev.reach + t
    s = TOTAL_TO_S.get(total, 1)
    capped = []
    if ev.certainty == 0 and s > 2:
        s = 2
        capped.append("certainty=0 cap")
    if t == 0 and s > 2:
        s = 2
        capped.append("timing=0 cap")
    floored = None
    if ev.stage in STAGE_FLOOR and ev.certainty == 2 and t >= 1:
        if s < STAGE_FLOOR[ev.stage]:
            floored = f"stage {ev.stage} floor"
        s = max(s, STAGE_FLOOR[ev.stage])
    reasons = list(ev.review_reasons)
    if s >= HUMAN_REVIEW_S:
        reasons.append(f"S >= {HUMAN_REVIEW_S}: human check before publishing")
    return {
        "event_id": ev.event_id, "active": True, "S": s,
        "certainty": ev.certainty, "reach": ev.reach, "timing": t, "total": total,
        "caps": capped, "floor": floored, "card_ids": ev.card_ids,
        "needs_review": bool(reasons), "review_reasons": reasons,
        "rubric_version": RUBRIC_VERSION,
    }


def rank_events(events: list[Event], week_start: date) -> list[dict]:
    """Event list view: S desc, then certainty, reach, most recent update."""
    rows = []
    for ev in events:
        r = event_score(ev, week_start)
        if r["active"]:
            r["recency"] = (ev.updated_date or ev.announced_date).isoformat()
            r["title"] = ev.title
            rows.append(r)
    rows.sort(key=lambda r: (-r["S"], -r["certainty"], -r["reach"], _neg_date(r["recency"])))
    return rows


def _neg_date(iso: str) -> int:
    return -date.fromisoformat(iso).toordinal()


def card_shock_scores(events: list[Event], week_start: date, catalog: set[str]) -> dict[str, dict]:
    """Per card: S = max over active events that map to it (1 if none). Records the driving event."""
    ranked = rank_events(events, week_start)
    out = {c: {"S": 1, "driver_event": None, "events": []} for c in catalog}
    for r in ranked:                      # already sorted, so the first hit per card is the driver
        for c in r["card_ids"]:
            out[c]["events"].append(r["event_id"])
            if out[c]["driver_event"] is None:
                out[c]["S"], out[c]["driver_event"] = r["S"], r["event_id"]
    return out
