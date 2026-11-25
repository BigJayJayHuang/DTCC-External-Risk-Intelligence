#!/usr/bin/env python3
"""Attach "What the market expects" boxes to cards for one week, point in time.

1. Reads the news classifier's candidates CSV(s) for the week (prompt v1.7: forward_topic, forward_lean, forward_quote,
   forward_subject).
2. Builds (or refreshes) that week's point-in-time Kalshi snapshot, data/kalshi/<monday>/kalshi_candidates.csv, with the
   articles' subjects added to the search (kalshi_candidates.py). Prices are as of the end of that week (Sunday close,
   US Eastern), so past weeks never use today's prices.
3. Matches each tagged article (market_view.py) and writes Capstone_Project/data/market_views/market_views_<monday>.json:
     {"week", "as_of", "cards": {card_id: box}, "skipped": [...]}
   One box per card, up to 3 markets. Vetted topics can propose a factor; subject matches are box only.
The export (docs/data/export_risk_output.py) adds the box to each card; a factor changes the shock only with
--apply-market-factor, after analyst review.

Usage:
  python3 attach_market_views.py --week 2026-11-09 --candidates <run>/candidates_<date>.csv
  python3 attach_market_views.py --week 2026-11-09 --candidates fixtures/candidates_v17_sample.csv --offline
  add --universe <kalshi_candidates.csv> to reuse an existing snapshot instead of rebuilding it
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kalshi_candidates as KC  # noqa: E402
from market_view import market_view, merge_card  # noqa: E402

OUT_DIR = HERE.parent / "data" / "market_views"


def read_candidates(paths):
    rows = []
    for p in paths:
        with Path(p).open(encoding="utf-8-sig", newline="") as f:
            rows += list(csv.DictReader(f))
    return rows


def build(cands: list[dict], universe: list[dict], week: str, as_of: datetime) -> dict:
    per_card, skipped = {}, []
    for r in cands:
        topic = (r.get("forward_topic") or "none").strip()
        if topic in ("", "none"):
            continue
        lean = (r.get("forward_lean") or "neutral").strip() or "neutral"
        eff = date.fromisoformat(r["effect_date"]) if r.get("effect_date") else None
        v = market_view(universe, topic, lean, eff, as_of, (r.get("forward_subject") or "").strip() or None)
        v.update(article_title=r.get("title", ""), article_url=r.get("url") or r.get("source_url", ""),
                 forward_quote=r.get("forward_quote") or None, candidate_id=r.get("event_id", ""))
        if not v.get("ok"):
            skipped.append({"candidate_id": v["candidate_id"], "topic": topic, "subject": v.get("subject"), "reason": v.get("reason")})
            continue
        for cid in [c for c in (r.get("card_ids") or "").split("|") if c]:
            per_card.setdefault(cid, []).append(v)
    cards = {cid: merge_card(vs) for cid, vs in per_card.items()}
    return {"week": week, "as_of": as_of.isoformat(timespec="minutes"), "source": "Kalshi public market data, point in time",
            "topics_version": KC.json.loads((HERE / "config" / "topics.json").read_text())["version"],
            "cards": {k: v for k, v in cards.items() if v}, "skipped": skipped}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, type=date.fromisoformat)
    ap.add_argument("--candidates", nargs="+", required=True, type=Path)
    ap.add_argument("--universe", type=Path, help="existing kalshi_candidates.csv for the week (skips the Kalshi calls)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--kalshi-root", type=Path, help="where weekly snapshots live (default data/kalshi; offline: data/kalshi/_offline_demo)")
    a = ap.parse_args(argv)
    cands = read_candidates(a.candidates)
    subjects = [s for s in dict.fromkeys((r.get("forward_subject") or "").strip() for r in cands
                                         if (r.get("forward_topic") or "none") != "none") if s]
    if a.universe:
        universe = KC.read_rows(a.universe)
        as_of = KC.parse_ts(universe[0]["as_of_utc"]) if universe else KC.as_of_for(a.week)
    else:
        cfg = json.loads(KC.CONFIG.read_text())
        if a.offline:
            from fixture_client import FixtureClient
            client, now, root = FixtureClient(HERE / "fixtures" / "candidates"), KC.OFFLINE_NOW, a.kalshi_root or KC.OUT_ROOT / "_offline_demo"
        else:
            client, now, root = KC.KalshiClient(), datetime.now(timezone.utc), a.kalshi_root or KC.OUT_ROOT
        _, universe, log = KC.run(a.week, client, cfg, root, now, offline=a.offline, subjects=subjects)
        as_of = KC.parse_ts(log["as_of_utc"])
    res = build(cands, universe, a.week.isoformat(), as_of)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    path = a.out_dir / f"market_views_{a.week.isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for cid, v in sorted(res["cards"].items()):
        rows = "; ".join(f"{x['question'][:48]} YES {round(x['p_yes'] * 100)}%" for x in v["rows"])
        print(f"{cid:<15} {v['match']:<7} {v['agreement']:<12} x{v['factor']:.2f}  {rows}")
    print(f"{len(res['cards'])} card(s), {len(res['skipped'])} skipped, as of {res['as_of']} -> {path}")
    return res


if __name__ == "__main__":
    main()
