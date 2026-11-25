#!/usr/bin/env python3
"""Test 1 for a prediction-market signal: does a big daily repricing flag the pre-set event windows?

Reads output/history/<series>.csv (from collect.py history) and config/windows.json.
Signal = daily repricing of the NEXT unresolved event in the series, in percentage points
(total-variation distance between today's and the previous day's outcome probabilities).
Rule (team's Standard Test 1): alert when the value is above the 90th percentile of the prior
252 days (current day excluded; at least --min-prior values). Pass if alerts hit at least 2 of 3
windows (2/3 of the windows in general), at least 25% of days alert in the median window, and the
alert rate outside windows is 15% or less.

Usage: python3 test1.py --series KXFEDDECISION [--min-prior 126]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent


def daily_repricing(rows: list[dict]) -> list[tuple[date, float]]:
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    out, prev = [], None
    for d in days:
        live = [r for r in by_day[d] if (r.get("event_close") or "9999")[:10] > d]
        if not live:
            prev = None
            continue
        ev = min({r["event_ticker"] for r in live}, key=lambda e: min(r["event_close"] or "9999" for r in live if r["event_ticker"] == e))
        now = {r["ticker"]: float(r["prob"]) for r in live if r["event_ticker"] == ev}
        if prev and prev[0] == ev:
            keys = [k for k in now if k in prev[1]]
            if keys:
                tv = abs(now[keys[0]] - prev[1][keys[0]]) if len(keys) == 1 else 0.5 * sum(abs(now[k] - prev[1][k]) for k in keys)
                out.append((date.fromisoformat(d), round(tv * 100, 2)))
        prev = (ev, now)
    return out


def percentile(vals: list[float], q: float) -> float:
    s = sorted(vals)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def test1(series: list[tuple[date, float]], windows: list[dict], lookback=252, min_prior=126, q=0.90) -> dict:
    alerts = []
    for i, (d, v) in enumerate(series):
        prior = [x for _, x in series[max(0, i - lookback):i]]
        alerts.append((d, v, (v > percentile(prior, q)) if len(prior) >= min_prior else None))   # None = not enough history yet
    usable = [a for a in alerts if a[2] is not None]
    win = [(date.fromisoformat(w["start"]), date.fromisoformat(w["end"])) for w in windows]
    inwin = lambda d: any(a <= d <= b for a, b in win)
    per = []
    for (a, b), w in zip(win, windows):
        days = [x for x in usable if a <= x[0] <= b]
        n_alert = sum(1 for x in days if x[2])
        per.append({"window": f"{w['start']} to {w['end']}", "what": w.get("what", ""), "days_with_data": len(days),
                    "alert_days": n_alert, "hit": n_alert > 0, "share": round(n_alert / len(days), 2) if days else None})
    covered = [p for p in per if p["days_with_data"]]
    hits = sum(p["hit"] for p in covered)
    shares = sorted(p["share"] for p in covered)
    med = shares[len(shares) // 2] if shares else None
    outside = [x for x in usable if not inwin(x[0])]
    out_rate = round(sum(1 for x in outside if x[2]) / len(outside), 3) if outside else None
    need = math.ceil(2 * len(covered) / 3) if covered else None
    ok = bool(covered) and hits >= need and med is not None and med >= 0.25 and out_rate is not None and out_rate <= 0.15
    return {"windows": per, "windows_with_data": len(covered), "hits": hits, "hits_needed": need, "median_window_share": med,
            "outside_alert_rate": out_rate, "days": len(series), "result": "PASS" if ok else ("INCONCLUSIVE" if len(covered) < len(win) and not ok else "FAIL"),
            "rule": f"alert > {int(q*100)}th pct of prior {lookback} days (min {min_prior}); pass = hits >= 2/3 of windows, median window share >= 25%, outside rate <= 15%"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", required=True)
    ap.add_argument("--min-prior", type=int, default=126)
    a = ap.parse_args(argv)
    rows = list(csv.DictReader((HERE / "output" / "history" / f"{a.series}.csv").open()))
    windows = json.loads((HERE / "config" / "windows.json").read_text()).get(a.series, [])
    res = test1(daily_repricing(rows), windows, min_prior=a.min_prior)
    print(json.dumps(res, indent=2))
    (HERE / "output" / f"test1_{a.series}.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
