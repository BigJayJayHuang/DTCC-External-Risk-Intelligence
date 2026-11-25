#!/usr/bin/env python3
"""Collect Kalshi market data for Risk Horizon (read-only, no API key).

Commands
  discover  --search "debt ceiling" [--category Politics]   find series tickers to put in config/series.json
  snapshot                                                   current prices for every configured series -> output/snapshots/<date>.jsonl
  history   --series KXFEDDECISION --days 730                daily price history (open + settled markets) -> output/history/<series>.csv

Add --offline to any command to read fixtures/ instead of the network.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kalshi_client import KalshiClient, candle_close, market_label, market_prob, to_float  # noqa: E402

OUT = HERE / "output"


def client_for(offline: bool):
    if offline:
        from fixture_client import FixtureClient
        return FixtureClient(HERE / "fixtures")
    return KalshiClient()


def cmd_discover(a):
    c = client_for(a.offline)
    words = [w.lower() for w in a.search]
    hits = [s for s in c.all_series(a.category) if all(w in (s.get("title", "") + " " + s.get("ticker", "")).lower() for w in words)]
    for s in hits[:50]:
        print(f"{s.get('ticker',''):<22} {s.get('category',''):<14} {s.get('frequency',''):<10} {s.get('title','')}")
    print(f"{len(hits)} match(es). Put the right ticker in config/series.json and set status to 'confirmed'.")
    return hits


def cmd_snapshot(a):
    c = client_for(a.offline)
    cfg = json.loads((HERE / "config" / "series.json").read_text())
    now = datetime.now(timezone.utc)
    rows = []
    for s in cfg["series"]:
        if not s.get("series"):
            continue
        for m in c.markets(series_ticker=s["series"], status="open"):
            rows.append({"collected_at": now.isoformat(), "series": s["series"], "event_ticker": m.get("event_ticker"), "ticker": m.get("ticker"),
                         "outcome": market_label(m), "prob": market_prob(m), "yes_bid": to_float(m.get("yes_bid_dollars")),
                         "yes_ask": to_float(m.get("yes_ask_dollars")), "open_interest": to_float(m.get("open_interest_fp")),
                         "volume_24h": to_float(m.get("volume_24h_fp")), "close_time": m.get("close_time")})
    d = OUT / "snapshots"; d.mkdir(parents=True, exist_ok=True)
    p = d / f"{now:%Y-%m-%d}.jsonl"
    with p.open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows)} market rows -> {p}")
    return rows


def cmd_history(a):
    c = client_for(a.offline)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=a.days)
    markets = c.markets(series_ticker=a.series) + c.historical_markets(series_ticker=a.series)
    seen, rows = set(), []
    for m in markets:
        t = m.get("ticker")
        if not t or t in seen:
            continue
        seen.add(t)
        close = m.get("close_time") or m.get("latest_expiration_time")
        try:
            cs = c.candles(a.series, t, int(start.timestamp()), int(now.timestamp()), 1440)
        except Exception as e:
            print(f"  skip {t}: {e}")
            continue
        for k in cs:
            p = candle_close(k)
            if p is None:
                continue
            rows.append({"date": datetime.fromtimestamp(k["end_period_ts"], timezone.utc).date().isoformat(), "series": a.series,
                         "event_ticker": m.get("event_ticker"), "ticker": t, "outcome": market_label(m), "prob": round(p, 4),
                         "volume": to_float(k.get("volume_fp"), 0.0), "event_close": close})
    d = OUT / "history"; d.mkdir(parents=True, exist_ok=True)
    p = d / f"{a.series}.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "series", "event_ticker", "ticker", "outcome", "prob", "volume", "event_close"])
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r["date"], r["ticker"])))
    print(f"{len(seen)} markets, {len(rows)} daily rows -> {p}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover"); d.add_argument("--search", nargs="+", required=True); d.add_argument("--category")
    sub.add_parser("snapshot")
    h = sub.add_parser("history"); h.add_argument("--series", required=True); h.add_argument("--days", type=int, default=730)
    for sp in sub.choices.values():
        sp.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    return {"discover": cmd_discover, "snapshot": cmd_snapshot, "history": cmd_history}[a.cmd](a)


if __name__ == "__main__":
    main()
