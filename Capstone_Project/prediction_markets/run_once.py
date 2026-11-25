#!/usr/bin/env python3
"""One command for a teammate to run the Kalshi market box end to end, once.

Steps:
  1. Check Kalshi is reachable (public market data, no key).
  2. Run the news classifier with prompt v1.7 (Bedrock, your normal AWS SSO login) into its own folder,
     so it never touches the team's data/events files. For a past week it reuses that week's saved news
     (data/events/weekly/<monday>/<run>/inputs/feeds/classifier_input.csv), so nothing is re-collected.
  3. Build that week's point-in-time Kalshi snapshot (as of the Sunday close) and match the tagged articles
     -> Capstone_Project/data/kalshi/<week>/ and Capstone_Project/data/market_views/market_views_<week>.json
     (the weekly news run does steps 2-3 itself; this script is for back-filling past weeks)
  4. Export the dashboard data to docs/data/risk_output_kalshi.json (the live risk_output.json is not touched).
  5. Print a summary and the link to open.

Usage (from the repo root, in a normal terminal, after `aws sso login --profile devx-bedrock`):
  python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-23
  python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-23 --candidates <existing candidates.csv>   # skip the classifier
  python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-02 --offline                                # dry run on simulated data
Add --apply-market-factor to also apply the factor to event-scored shocks (only after an analyst has reviewed the boxes).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CP = HERE.parent
ROOT = CP.parent
sys.path.insert(0, str(HERE))
import attach_market_views  # noqa: E402

MV_DIR = CP / "data" / "market_views"
OUT_JSON = ROOT / "docs" / "data" / "risk_output_kalshi.json"
# offline dry runs go to their own folder/file so they can never be mistaken for real output
MV_DIR_OFFLINE = MV_DIR / "offline_demo"
OUT_JSON_OFFLINE = ROOT / "docs" / "data" / "risk_output_kalshi_offline.json"


def step(n, msg):
    print(f"\n[{n}/5] {msg}", flush=True)


def check_kalshi():
    from kalshi_client import KalshiClient
    try:
        KalshiClient().series("KXFEDDECISION")
        print("    Kalshi reachable.")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"    Could not reach Kalshi ({e}). Run this from a normal terminal on an open network "
                 "(some school/VPN/sandbox networks block it).")


def run_classifier(a) -> Path:
    out = MV_DIR / "classifier_runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(CP / "validation" / "llm_classifier.py"), "--start", a.start.isoformat(),
           "--end", a.end.isoformat(), "--prompt-version", "v1.7", "--output-dir", str(out)]
    saved = sorted((CP / "data" / "events" / "weekly" / a.week).glob("*/inputs/feeds/classifier_input.csv"))
    if saved:
        cmd += ["--news", str(saved[-1])]
        print(f"    reusing the week's saved news: {saved[-1]}")
    if a.max_articles:
        cmd += ["--max-articles", str(a.max_articles)]
    if a.budget:
        cmd += ["--budget", str(a.budget)]
    print("    " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)
    found = sorted(out.glob("candidates_*.csv"))
    if not found:
        sys.exit(f"    The classifier finished but wrote no candidates CSV in {out}.")
    return found[-1]


def run_export(a):
    sys.path.insert(0, str(ROOT / "docs" / "data"))
    from export_risk_output import WEEKS
    weeks = list(WEEKS) + ([a.week] if a.week not in WEEKS else [])
    cmd = [sys.executable, str(ROOT / "docs" / "data" / "export_risk_output.py"), "--out", str(a.out_json),
           "--market-views-dir", str(a.mv_dir)]
    for w in weeks:
        cmd += ["--week", w]
    if a.apply_market_factor:
        cmd.append("--apply-market-factor")
    print("    " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def summary(a):
    mv = json.loads((a.mv_dir / f"market_views_{a.week}.json").read_text())
    cards = mv.get("cards", {})
    print(f"    {len(cards)} card(s) got a market box; {len(mv.get('skipped', []))} tagged article(s) had no usable market.")
    print(f"    prices as of {mv.get('as_of')}")
    for cid, v in sorted(cards.items()):
        print(f"    - {cid}: {v.get('agreement')}  factor x{v['factor']:.2f}")
        for r in v.get("rows", []):
            print(f"        {r['question']}  YES {round(r['p_yes'] * 100)}%  (resolves {r['resolves']})")
    for s in mv.get("skipped", [])[:10]:
        print(f"    skipped {s.get('candidate_id')}: {s.get('topic')} ({s.get('reason')})")
    print(f"\n    Open docs/index.html?data=data/{a.out_json.name} through the local server or GitHub Pages to see the boxes.")
    print("    Factor applied to scores:", "YES" if a.apply_market_factor else "no (box and proposed factor only)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="Monday of the snapshot week, YYYY-MM-DD")
    ap.add_argument("--start", type=date.fromisoformat, help="news start date (default: the Monday)")
    ap.add_argument("--end", type=date.fromisoformat, help="news end date (default: the Sunday)")
    ap.add_argument("--candidates", nargs="+", type=Path, help="existing v1.7 candidates CSV(s); skips the classifier")
    ap.add_argument("--max-articles", type=int)
    ap.add_argument("--budget")
    ap.add_argument("--offline", action="store_true", help="simulated Kalshi data and sample candidates; no network")
    ap.add_argument("--apply-market-factor", action="store_true")
    a = ap.parse_args(argv)
    monday = date.fromisoformat(a.week)
    a.start = a.start or monday
    a.end = a.end or monday + timedelta(days=6)
    a.mv_dir = MV_DIR_OFFLINE if a.offline else MV_DIR
    a.out_json = OUT_JSON_OFFLINE if a.offline else OUT_JSON

    step(1, "Kalshi")
    print("    skipped (offline)") if a.offline else check_kalshi()

    step(2, "News classifier, prompt v1.7")
    if a.candidates:
        cands = a.candidates
        print("    using", ", ".join(map(str, cands)))
    elif a.offline:
        cands = [HERE / "fixtures" / "candidates_v17_sample.csv"]
        print("    offline: using the sample candidates file")
    else:
        cands = [run_classifier(a)]

    step(3, "Point-in-time Kalshi snapshot and matching")
    args = ["--week", a.week, "--candidates", *map(str, cands), "--out-dir", str(a.mv_dir)] + (["--offline"] if a.offline else [])
    attach_market_views.main(args)

    step(4, "Export dashboard data")
    run_export(a)

    step(5, "Summary")
    summary(a)


if __name__ == "__main__":
    main()
