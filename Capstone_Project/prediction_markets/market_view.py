"""What the market expected, for one classified news article, from that week's point-in-time candidate list.

Input: the rows of data/kalshi/<monday>/kalshi_candidates.csv (kalshi_candidates.py), i.e. every relevant market that
was live at the end of that week with its price as of then. Nothing here calls the API, so a past week can never use
today's prices.

Two ways to match (the model tags, code matches):
  - vetted topics (config/topics.json: fed_cut, government_shutdown, ...): the configured series, the event that resolves
    closest to the article's date. These can propose a score factor when the article leans yes/no:
        factor = 0.75 + 0.5 x (market probability of the article's side), clamped to [0.75, 1.25]
  - "other" (prompt v1.7 forward_subject, e.g. "Jensen Huang return as Nvidia CEO"): word search over the week's
    markets, up to 3 events (e.g. back by end of month / end of year). Box only: factor 1.0, never scales a score.
A vetted topic with no series configured yet falls back to the subject search when the article gave a subject.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

from kalshi_candidates import content_words, parse_ts, word_hits

HERE = Path(__file__).resolve().parent
TOPICS = json.loads((HERE / "config" / "topics.json").read_text())
MAX_ROWS = 3


def _f(x):
    try:
        return None if x in (None, "") else float(x)
    except ValueError:
        return None


def factor_for(p_side: float | None, lean: str | None, rng=None) -> float:
    lo, hi = rng or TOPICS["factor_range"]
    if p_side is None or lean not in ("yes", "no"):
        return 1.0
    return round(max(lo, min(hi, 0.75 + 0.5 * p_side)), 2)


def combine(*factors: float, rng=None) -> float:
    """Hype x market, kept inside the same band so a card is never boosted or cut by more than 25% in total."""
    lo, hi = rng or TOPICS["factor_range"]
    out = 1.0
    for f in factors:
        out *= f if f else 1.0
    return round(max(lo, min(hi, out)), 2)


def agreement(p_side: float | None, lean: str | None) -> str:
    if lean not in ("yes", "no") or p_side is None:
        return "no_lean"
    if p_side >= TOPICS["agree_threshold"]:
        return "agrees"
    if p_side <= TOPICS["disagree_threshold"]:
        return "disagrees"
    return "split"


def adjusted_shock(S: int | None, factor: float) -> float | None:
    return None if S is None else round(min(5.0, S * factor), 1)


def _row(question, rs, p, p7, extra=None):
    close = min(parse_ts(r["close_time"]) for r in rs)
    results = {r.get("result") for r in rs}
    return {"question": question, "event_ticker": rs[0]["event_ticker"], "markets": [r["market_ticker"] for r in rs],
            "p_yes": round(p, 3), "p_no": round(1 - p, 3), "p_yes_week_ago": None if p7 is None else round(p7, 3),
            "change_pp": None if p7 is None else round((p - p7) * 100, 1), "resolves": close.date().isoformat(),
            "url": rs[0].get("kalshi_url", ""), "liquidity_ok": any(r.get("liquidity_ok") == "Y" for r in rs),
            "result": results.pop() if len(results) == 1 else "mixed", **(extra or {})}


def _events(rows):
    by = {}
    for r in rows:
        if _f(r.get("prob_as_of")) is not None:
            by.setdefault(r["event_ticker"], []).append(r)
    return by


def vetted(rows, topic, lean, effect_date: date | None, as_of: datetime) -> dict:
    t = TOPICS["topics"].get(topic)
    base = {"topic": topic, "lean": lean, "match": "vetted", "as_of": as_of.isoformat(timespec="minutes")}
    if not t:
        return {**base, "ok": False, "reason": "topic not tracked"}
    if not t["series"]:
        return {**base, "ok": False, "reason": "no Kalshi series configured yet: " + t.get("status", "")}
    target = datetime.combine(effect_date, datetime.min.time(), timezone.utc) if effect_date else as_of
    best = None
    for ev, rs in _events([r for r in rows if r["series_ticker"] in t["series"]]).items():
        close = min(parse_ts(r["close_time"]) for r in rs)
        gap = abs((close - target).days)
        if close > as_of and gap <= t["max_gap_days"] and (best is None or gap < best[0]):
            best = (gap, rs)
    if not best:
        return {**base, "ok": False, "reason": f"no market live at the snapshot resolving within {t['max_gap_days']} days of the article's date"}
    rs, rule = best[1], t["yes_rule"]
    if "outcome_contains" in rule:
        used = [r for r in rs if any(w in r["market_title"].lower() for w in rule["outcome_contains"])]
        if not used:
            return {**base, "ok": False, "reason": "no matching outcomes"}
        p = min(1.0, sum(_f(r["prob_as_of"]) for r in used))
        p7s = [_f(r["prob_7d_before"]) for r in used]
        p7 = None if any(x is None for x in p7s) else min(1.0, sum(p7s))
    else:
        used = [max(rs, key=lambda r: _f(r.get("open_interest")) or 0)]
        p, p7 = _f(used[0]["prob_as_of"]), _f(used[0]["prob_7d_before"])
        if rule.get("risk_side", "yes") == "no":
            p, p7 = 1 - p, (None if p7 is None else 1 - p7)
    if not any(r.get("liquidity_ok") == "Y" for r in used):
        return {**base, "ok": False, "reason": "thin market at the snapshot"}
    p_side = None if lean not in ("yes", "no") else (p if lean == "yes" else 1 - p)
    row = _row(t["question"], used, p, p7, {"event_title": used[0]["event_title"]})
    return {**base, "ok": True, "rows": [row], "agreement": agreement(p_side, lean),
            "p_article_side": None if p_side is None else round(p_side, 3), "factor": factor_for(p_side, lean), "applied": False}


def _question(r):
    t, m = r["event_title"].strip(), (r.get("market_title") or "").strip()
    return t if not m or m.lower() in ("yes", t.lower()) or m.lower() in t.lower() else f"{t}: {m}"


def by_subject(rows, subject: str | None, lean, as_of: datetime, k: int = MAX_ROWS) -> dict:
    base = {"topic": "other", "subject": subject, "lean": lean, "match": "auto", "as_of": as_of.isoformat(timespec="minutes")}
    words = content_words(subject)
    if len(words) < 2:
        return {**base, "ok": False, "reason": "subject too short to search"}
    need = max(2, math.ceil(len(words) / 2))
    found = []
    for ev, rs in _events(rows).items():
        scored = [(word_hits(words, f"{r['event_title']} {r['market_title']}"), _f(r.get("open_interest")) or 0, r) for r in rs]
        hits, oi, r = max(scored, key=lambda x: (x[0], x[1]))
        if hits >= need and parse_ts(r["close_time"]) > as_of:
            found.append((hits, r))
    if not found:
        return {**base, "ok": False, "reason": "no market about this subject was live at the snapshot"}
    top = sorted(found, key=lambda x: (-x[0], parse_ts(x[1]["close_time"])))[:k]
    out = [_row(_question(r), [r], _f(r["prob_as_of"]), _f(r["prob_7d_before"]), {"event_title": r["event_title"]}) for _, r in top]
    out.sort(key=lambda x: x["resolves"])
    return {**base, "ok": True, "rows": out, "agreement": "auto_matched", "p_article_side": None, "factor": 1.0, "applied": False}


def market_view(rows, topic, lean, effect_date, as_of, subject=None) -> dict:
    if topic == "other":
        return by_subject(rows, subject, lean, as_of)
    v = vetted(rows, topic, lean, effect_date, as_of)
    if not v["ok"] and subject:
        s = by_subject(rows, subject, lean, as_of)
        if s["ok"]:
            return {**s, "topic": topic, "note": "vetted series not available; matched by subject (box only)"}
    return v


def merge_card(views: list[dict]) -> dict:
    """One box per card: the vetted view with the biggest proposed factor leads, other matches fill up to 3 rows."""
    ok = [v for v in views if v.get("ok")]
    if not ok:
        return {}
    lead = max(ok, key=lambda v: (v["match"] == "vetted", abs(v["factor"] - 1)))
    rows, seen = [], set()
    for v in [lead] + [v for v in ok if v is not lead]:
        for r in v["rows"]:
            if r["event_ticker"] not in seen and len(rows) < MAX_ROWS:
                seen.add(r["event_ticker"]); rows.append(r)
    first = rows[0]
    return {**{k: lead[k] for k in ("topic", "lean", "match", "as_of", "agreement", "p_article_side", "factor", "applied")},
            "ok": True, "rows": rows, "subject": lead.get("subject"),
            # single-row fields kept for older dashboard code
            "question": first["question"], "p_yes": first["p_yes"], "p_no": first["p_no"], "p_yes_week_ago": first["p_yes_week_ago"],
            "change_pp": first["change_pp"], "resolves": first["resolves"], "url": first["url"],
            "article_title": lead.get("article_title", ""), "article_url": lead.get("article_url", ""),
            "forward_quote": lead.get("forward_quote"),
            "articles": [{k: v.get(k) for k in ("article_title", "article_url", "forward_quote", "lean", "topic", "subject", "candidate_id")} for v in ok]}
