"""Market view for one classified news event: what Kalshi expects, and whether it agrees with the article.

Flow: the news classifier (prompt v1.7) tags an article with forward_topic (fed_cut, government_shutdown, ...) and
forward_lean (yes / no / neutral). This module, not the model, finds the matching Kalshi market from
config/topics.json, reads the YES probability, and returns the box shown on the card:

  YES 68% | NO 32%, change vs a week ago, agreement with the article, and a factor in [0.75, 1.25].

factor = 0.75 + 0.5 x (probability the market gives to the article's side), only when the article has a lean.
Neutral articles get the box with factor 1.0. Thin markets or markets resolving far from the article's date get no box.
The factor multiplies the event's shock only after an analyst approves it (export flag --apply-market-factor).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from kalshi_client import candle_close, market_label, market_prob, to_float

HERE = Path(__file__).resolve().parent
TOPICS = json.loads((HERE / "config" / "topics.json").read_text())
DEFAULTS = json.loads((HERE / "config" / "series.json").read_text())["defaults"]


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def _resolve(m):
    return _ts(m.get("close_time")) or _ts(m.get("latest_expiration_time"))


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


def _yes_prob(markets: list[dict], rule: dict) -> tuple[float | None, list[dict]]:
    if "outcome_contains" in rule:
        words = [w.lower() for w in rule["outcome_contains"]]
        used = [m for m in markets if any(w in market_label(m).lower() for w in words)]
        ps = [market_prob(m) for m in used]
        if not used or any(p is None for p in ps):
            return None, used
        return round(min(1.0, sum(ps)), 4), used
    m = max(markets, key=lambda x: to_float(x.get("open_interest_fp"), 0.0))
    p = market_prob(m)
    if p is None:
        return None, [m]
    return (p if rule.get("risk_side", "yes") == "yes" else round(1 - p, 4)), [m]


def _past_yes(client, series, used, rule, now, days):
    start, end = int((now - timedelta(days=days + 2)).timestamp()), int(now.timestamp())
    target = (now - timedelta(days=days)).timestamp()
    vals = []
    for m in used:
        try:
            cs = [c for c in client.candles(series, m["ticker"], start, end, 1440) if c.get("end_period_ts", 0) <= target]
        except Exception:
            return None
        if not cs or candle_close(cs[-1]) is None:
            return None
        vals.append(candle_close(cs[-1]))
    if not vals:
        return None
    p = min(1.0, sum(vals)) if "outcome_contains" in rule else vals[0]
    return round(p if rule.get("risk_side", "yes") == "yes" or "outcome_contains" in rule else 1 - p, 4)


def market_view(client, topic: str, lean: str | None, effect_date: date | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    t = TOPICS["topics"].get(topic)
    base = {"topic": topic, "lean": lean, "source": "Kalshi", "as_of": now.isoformat(timespec="minutes")}
    if not t:
        return {**base, "ok": False, "reason": "topic not tracked"}
    base["question"] = t["question"]
    if not t["series"]:
        return {**base, "ok": False, "reason": "no Kalshi series configured yet: " + t.get("status", "")}
    target = datetime.combine(effect_date, datetime.min.time(), timezone.utc) if effect_date else now
    best = None
    for series in t["series"]:
        by_ev: dict[str, list[dict]] = {}
        for m in client.markets(series_ticker=series, status="open"):
            r = _resolve(m)
            if r and r > now and m.get("event_ticker"):
                by_ev.setdefault(m["event_ticker"], []).append(m)
        for ev, ms in by_ev.items():
            gap = abs((min(_resolve(m) for m in ms) - target).days)
            if gap <= t["max_gap_days"] and (best is None or gap < best[0]):
                best = (gap, series, ev, ms)
    if not best:
        return {**base, "ok": False, "reason": f"no open market resolving within {t['max_gap_days']} days of the article's date"}
    gap, series, ev, ms = best
    p_yes, used = _yes_prob(ms, t["yes_rule"])
    oi = sum(to_float(m.get("open_interest_fp"), 0.0) for m in used)
    v24 = sum(to_float(m.get("volume_24h_fp"), 0.0) for m in used)
    if p_yes is None or (oi < DEFAULTS["min_open_interest"] and v24 < DEFAULTS["min_volume_24h"]):
        return {**base, "ok": False, "reason": "thin or unpriced market", "event_ticker": ev}
    try:
        title = client.event(ev).get("title") or ev
    except Exception:
        title = ev
    p_week = _past_yes(client, series, used, t["yes_rule"], now, DEFAULTS["repricing_lookback_days"])
    p_side = None if lean not in ("yes", "no") else (p_yes if lean == "yes" else 1 - p_yes)
    f = factor_for(p_side, lean)
    return {**base, "ok": True, "series": series, "event_ticker": ev, "market_title": title,
            "markets": [m["ticker"] for m in used], "resolves": min(_resolve(m) for m in ms).date().isoformat(),
            "p_yes": round(p_yes, 3), "p_no": round(1 - p_yes, 3), "p_yes_week_ago": p_week,
            "change_pp": None if p_week is None else round((p_yes - p_week) * 100, 1),
            "agreement": agreement(p_side, lean), "p_article_side": None if p_side is None else round(p_side, 3),
            "factor": f, "applied": False, "open_interest": oi, "volume_24h": v24,
            "url": f"https://kalshi.com/markets/{series.lower()}"}


def adjusted_shock(S: int | None, factor: float) -> float | None:
    return None if S is None else round(min(5.0, S * factor), 1)
