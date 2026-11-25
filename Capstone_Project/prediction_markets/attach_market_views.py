#!/usr/bin/env python3
"""Attach Kalshi market views to cards from a news-classifier run (prompt v1.7).

Reads the classifier's candidate CSV(s) (columns card_ids, forward_topic, forward_lean, effect_date, ...),
looks up each tagged topic on Kalshi, and writes Capstone_Project/data/market_views/market_views_<week>.json:
  {"week": ..., "cards": {card_id: view}}   one view per card: the event with the largest |factor - 1|, ties = latest.
The export (docs/data/export_risk_output.py) adds it to each card as `market_view`; the factor is applied to the
shock only with --apply-market-factor, after analyst review.

Usage:
  python3 attach_market_views.py --week 2026-11-23 --candidates <run_dir>/candidates.csv [--offline]
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
from kalshi_client import KalshiClient  # noqa: E402
from market_view import market_view  # noqa: E402

OUT_DIR = HERE.parent / "data" / "market_views"


def build(rows: list[dict], client, week: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cache, cards, skipped = {}, {}, []
    for r in rows:
        topic = (r.get("forward_topic") or "none").strip()
        if topic in ("", "none"):
            continue
        lean = (r.get("forward_lean") or "neutral").strip() or "neutral"
        eff = date.fromisoformat(r["effect_date"]) if r.get("effect_date") else None
        key = (topic, lean, eff)
        if key not in cache:
            cache[key] = market_view(client, topic, lean, eff, now)
        v = dict(cache[key])
        v.update(article_title=r.get("title", ""), article_url=r.get("url") or r.get("source_url", ""),
                 forward_quote=r.get("forward_quote") or None, candidate_id=r.get("event_id", ""))
        if not v.get("ok"):
            skipped.append({"candidate_id": v["candidate_id"], "topic": topic, "reason": v.get("reason")})
            continue
        for cid in [c for c in (r.get("card_ids") or "").split("|") if c]:
            cur = cards.get(cid)
            if cur is None or abs(v["factor"] - 1) >= abs(cur["factor"] - 1):
                cards[cid] = v
    return {"week": week, "generated_at": now.isoformat(timespec="seconds"), "source": "Kalshi public market data",
            "topics_version": json.loads((HERE / "config" / "topics.json").read_text())["version"],
            "cards": cards, "skipped": skipped}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True)
    ap.add_argument("--candidates", nargs="+", required=True, type=Path)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)
    rows = []
    for p in a.candidates:
        with p.open(encoding="utf-8", newline="") as f:
            rows += list(csv.DictReader(f))
    if a.offline:
        from fixture_client import FixtureClient
        client, now = FixtureClient(HERE / "fixtures"), datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)
    else:
        client, now = KalshiClient(), None
    res = build(rows, client, a.week, now)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    path = a.out_dir / f"market_views_{a.week}{'_offline' if a.offline else ''}.json"
    path.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for cid, v in sorted(res["cards"].items()):
        print(f"{cid:<16} {v['topic']:<20} YES {round(v['p_yes']*100)}% · {v['agreement']:<9} ×{v['factor']:.2f}  {v['article_title'][:60]}")
    print(f"{len(res['cards'])} card(s), {len(res['skipped'])} skipped -> {path}")
    return res


if __name__ == "__main__":
    main()
