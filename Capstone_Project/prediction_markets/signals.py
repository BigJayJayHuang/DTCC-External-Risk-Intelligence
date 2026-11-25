#!/usr/bin/env python3
"""Turn Kalshi prediction-market prices into weekly inputs for the Risk Horizon model.

Two uses, set per series in config/series.json:
  * market_signal (multi-outcome series, e.g. the next Fed decision): weekly REPRICING in percentage points
    = how far the market's probabilities moved over the lookback. Treated like any other market signal
    (it must pass Test 1 before it can set a shock score).
  * event_rubric (yes/no series, e.g. a government shutdown): probability -> rubric CERTAINTY (0/1/2) and the
    market's resolution date -> rubric TIMING, scored with the team's own rubric (validation/event_scoring.py).
    Every market-derived event is flagged for human review; the market is evidence, not a primary source.

Output: output/pm_signals_<week>.json, one record per series plus a by-chain index. Nothing else in the repo
is changed; the risk-model export can merge these records later (see README).

Usage:
  python3 signals.py --week 2026-11-23            # live (needs network access to Kalshi)
  python3 signals.py --week 2026-11-23 --offline  # uses fixtures/ (for tests and demos)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kalshi_client import KalshiClient, candle_close, market_label, market_prob, to_float  # noqa: E402

SIGNAL_VERSION = "pm-signals-v0.1"


# ---------------- pure helpers ----------------
def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_time(m: dict) -> datetime | None:
    return parse_ts(m.get("close_time")) or parse_ts(m.get("latest_expiration_time"))


def pick_event(markets: list[dict], now: datetime) -> tuple[str | None, list[dict]]:
    """Nearest event that has not resolved yet (smallest close time after `now`)."""
    by_ev: dict[str, list[dict]] = {}
    for m in markets:
        t = resolve_time(m)
        if t and t > now and m.get("event_ticker"):
            by_ev.setdefault(m["event_ticker"], []).append(m)
    if not by_ev:
        return None, []
    ev = min(by_ev, key=lambda e: min(resolve_time(m) for m in by_ev[e]))
    return ev, by_ev[ev]


def is_liquid(m: dict, d: dict) -> bool:
    oi = to_float(m.get("open_interest_fp"), 0.0)
    v24 = to_float(m.get("volume_24h_fp"), 0.0)
    return oi >= d["min_open_interest"] or v24 >= d["min_volume_24h"]


def repricing_pp(now: dict[str, float], before: dict[str, float]) -> float | None:
    """Total-variation distance between two outcome distributions, in percentage points.
    For a yes/no market this is just |p_now - p_before| x 100."""
    keys = [k for k in now if k in before and now[k] is not None and before[k] is not None]
    if not keys:
        return None
    if len(keys) == 1:
        k = keys[0]
        return round(abs(now[k] - before[k]) * 100, 1)
    return round(0.5 * sum(abs(now[k] - before[k]) for k in keys) * 100, 1)


def certainty_from_prob(p: float | None) -> int | None:
    """Rubric certainty from a market probability: >= 70% -> 2, 30-70% -> 1, < 30% -> 0 (proposed, freeze before use)."""
    if p is None:
        return None
    return 2 if p >= 0.70 else 1 if p >= 0.30 else 0


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def rubric_score(card_ids, title, effect: date, certainty: int, reach: int, reach_basis: str, week_start: date, url: str):
    """Score with the team's own rubric (validation/event_scoring.py) if it is importable; otherwise return the inputs only."""
    try:
        sys.path.insert(0, str(HERE.parent / "validation"))
        import event_scoring as E  # type: ignore
    except Exception as e:  # pragma: no cover - depends on repo layout
        return {"certainty": certainty, "reach": reach, "effect_date": effect.isoformat(), "S": None,
                "note": f"validation/event_scoring.py not importable ({e}); S left for the model run"}
    ev = E.Event(event_id=f"PM-{title[:40]}", card_ids=list(card_ids), title=title, announced_date=week_start,
                 effect_date=effect, certainty=certainty, reach=reach, evidence_quotes=[], reach_basis=reach_basis,
                 sources=[{"url": url, "outlet": "Kalshi", "tier": "other"}],
                 review_reasons=["probability from a prediction market: confirm the event with a primary source"])
    r = E.event_score(ev, week_start)
    r["effect_date"] = effect.isoformat()
    return r


# ---------------- per-series summary ----------------
def summarize(client, cfg: dict, defaults: dict, week_start: date, now: datetime) -> dict:
    series = cfg.get("series")
    base = {k: cfg.get(k) for k in ("series", "label", "mode", "use", "chains", "status")}
    if not series:
        return {**base, "ok": False, "reason": "no ticker yet; run collect.py discover --search " + " / ".join(cfg.get("discover_search", []))}
    markets = client.markets(series_ticker=series, status="open")
    ev, mk = pick_event(markets, now)
    if not ev:
        return {**base, "ok": False, "reason": "no open event in this series"}
    try:
        title = client.event(ev).get("title") or ev
    except Exception:
        title = ev
    look = defaults["repricing_lookback_days"]
    start_ts = int((now - timedelta(days=look + 2)).timestamp())
    rows = []
    for m in mk:
        p = market_prob(m)
        past = None
        try:
            cs = client.candles(series, m["ticker"], start_ts, int(now.timestamp()), 1440)
            target = (now - timedelta(days=look)).timestamp()
            before = [c for c in cs if c.get("end_period_ts") and c["end_period_ts"] <= target]
            if before:
                past = candle_close(before[-1])
        except Exception:
            past = None
        rows.append({"ticker": m["ticker"], "outcome": market_label(m), "prob": p, "prob_lookback": past,
                     "open_interest": to_float(m.get("open_interest_fp"), 0.0), "volume_24h": to_float(m.get("volume_24h_fp"), 0.0),
                     "liquid": is_liquid(m, defaults), "resolves": (resolve_time(m) or now).isoformat()})
    liquid = [r for r in rows if r["liquid"] and r["prob"] is not None]
    resolves = min(resolve_time(m) for m in mk)
    days_to = max(0, (resolves - now).days)
    url = f"https://kalshi.com/markets/{series.lower()}"
    out = {**base, "ok": bool(liquid), "event_ticker": ev, "event_title": title, "resolves": resolves.date().isoformat(),
           "days_to_resolution": days_to, "markets": rows, "kalshi_url": url,
           "thin_market": not liquid}
    if not liquid:
        out["reason"] = "thin market: below the open-interest / volume floor, not used"
        return out
    now_p = {r["ticker"]: r["prob"] for r in liquid}
    past_p = {r["ticker"]: r["prob_lookback"] for r in liquid if r["prob_lookback"] is not None}
    rep = repricing_pp(now_p, past_p)
    out["repricing_pp"] = rep
    out["jump"] = rep is not None and rep >= defaults["jump_pp"]
    if cfg["mode"] == "multi_outcome":
        top = sorted(liquid, key=lambda r: -r["prob"])
        out["top_outcomes"] = [{"outcome": r["outcome"], "prob": r["prob"]} for r in top[:3]]
        out["uncertainty"] = round(1 - top[0]["prob"], 3)
        out["card_line"] = (f"Kalshi, {title}: " + ", ".join(f"{r['outcome']} {round(r['prob']*100)}%" for r in top[:2])
                            + (f" · moved {rep:.0f} pp in {look} days" if rep is not None else ""))
    else:
        r = max(liquid, key=lambda x: x["open_interest"])
        p, pb = r["prob"], r["prob_lookback"]
        out["prob"] = p
        out["prob_lookback"] = pb
        out["card_line"] = (f"Kalshi: {round(p*100)}% chance · {title}"
                            + (f" ({round(pb*100)}% {look} days ago)" if pb is not None else "") + f" · resolves {resolves.strftime('%b')} {resolves.day}")
        if cfg.get("use") == "event_rubric":
            out["rubric"] = rubric_score(cfg["chains"], title, resolves.date(), certainty_from_prob(p), int(cfg.get("reach", 1)),
                                         cfg.get("reach_basis", ""), week_start, url)
    return out


def build(client, config: dict, week_start: date, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    d = config["defaults"]
    sigs = []
    for cfg in config["series"]:
        try:
            sigs.append(summarize(client, cfg, d, week_start, now))
        except Exception as e:
            sigs.append({k: cfg.get(k) for k in ("series", "label", "mode", "use", "chains")} | {"ok": False, "reason": f"error: {e}"})
    by_chain: dict[str, list[str]] = {}
    for s in sigs:
        if s.get("ok"):
            for c in s.get("chains") or []:
                by_chain.setdefault(c, []).append(s["series"])
    return {"signal_version": SIGNAL_VERSION, "config_version": config.get("version"), "week": week_start.isoformat(),
            "generated_at": now.isoformat(), "source": "Kalshi public market data (read-only)", "signals": sigs, "by_chain": by_chain}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", help="Monday of the scoring week (YYYY-MM-DD); default = this week's Monday")
    ap.add_argument("--config", default=str(HERE / "config" / "series.json"))
    ap.add_argument("--offline", action="store_true", help="read fixtures/ instead of the live API")
    ap.add_argument("--out", default=str(HERE / "output"))
    a = ap.parse_args(argv)
    week = date.fromisoformat(a.week) if a.week else monday(date.today())
    if week.weekday() != 0:
        ap.error("--week must be a Monday")
    config = json.loads(Path(a.config).read_text())
    if a.offline:
        from fixture_client import FixtureClient
        client, now = FixtureClient(HERE / "fixtures"), datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)
    else:
        client, now = KalshiClient(), None
    res = build(client, config, week, now)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    path = Path(a.out) / f"pm_signals_{week.isoformat()}{'_offline' if a.offline else ''}.json"
    path.write_text(json.dumps(res, indent=2))
    for s in res["signals"]:
        print(("OK   " if s.get("ok") else "SKIP ") + f"{s.get('series') or '(no ticker)':<16} " + (s.get("card_line") or s.get("reason", "")))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
