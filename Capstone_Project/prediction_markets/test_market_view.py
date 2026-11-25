"""Offline tests for the point-in-time market box (market_view.py, attach_market_views.py). python3 -m unittest test_market_view -v"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import attach_market_views as A  # noqa: E402
import kalshi_candidates as KC  # noqa: E402
import market_view as M  # noqa: E402
from fixture_client import FixtureClient  # noqa: E402

CFG = json.loads(KC.CONFIG.read_text())
FX = FixtureClient(HERE / "fixtures" / "candidates")
SAMPLE = HERE / "fixtures" / "candidates_v17_sample.csv"
NOV9, NOV2 = date(2026, 11, 9), date(2026, 11, 2)


def universe(monday, subjects=("Jensen Huang return as Nvidia CEO",)):
    with tempfile.TemporaryDirectory() as t:
        _, rows, log = KC.run(monday, FX, CFG, Path(t), KC.OFFLINE_NOW, subjects=list(subjects))
    return rows, KC.parse_ts(log["as_of_utc"])


class Factor(unittest.TestCase):
    def test_factor_mapping(self):
        self.assertEqual(M.factor_for(0.5, "yes"), 1.0)
        self.assertEqual(M.factor_for(0.8, "yes"), 1.15)
        self.assertEqual(M.factor_for(0.2, "no"), 0.85)
        self.assertEqual(M.factor_for(1.0, "yes"), 1.25)
        self.assertEqual(M.factor_for(0.9, "neutral"), 1.0)

    def test_combined_with_hype_stays_in_band(self):
        self.assertEqual(M.combine(1.25, 1.2), 1.25)
        self.assertEqual(M.combine(0.75, 0.8), 0.75)
        self.assertEqual(M.combine(1.1, 0.9), 0.99)
        self.assertEqual(M.adjusted_shock(4, 1.25), 5.0)


class PointInTime(unittest.TestCase):
    def test_past_week_uses_sunday_close_not_today(self):
        rows, as_of = universe(NOV9)
        self.assertEqual(as_of.isoformat(), "2026-11-16T05:00:00+00:00")      # Sun Nov 15 close, US Eastern
        h0 = next(r for r in rows if r["market_ticker"] == "KXFEDDECISION-26DEC-H0")
        self.assertEqual((h0["prob_as_of"], h0["prob_source"], h0["yes_bid"]), (0.48, "candle_close", ""))   # not today's 0.62
        self.assertEqual((h0["prob_7d_before"], h0["change_7d_pts"]), (0.55, -7.0))

    def test_only_markets_live_at_the_snapshot(self):
        nov2 = {r["market_ticker"] for r in universe(NOV2)[0]}
        nov9 = {r["market_ticker"] for r in universe(NOV9)[0]}
        self.assertIn("KXGOVSHUT-26NOV14", nov2)              # settled later, but live on Nov 8
        self.assertNotIn("KXGOVSHUT-26NOV14", nov9)           # closed Nov 14, before the Nov 15 snapshot
        self.assertNotIn("KXNVDACEO-26DEC31", nov2)           # opened Nov 10
        self.assertIn("KXNVDACEO-26NOV20", nov9)              # settled since: fetched from closed markets
        self.assertNotIn("KXAILAW-27", nov9)                  # opened Nov 18

    def test_outcome_columns(self):
        r = next(x for x in universe(NOV9)[0] if x["market_ticker"] == "KXNVDACEO-26NOV20")
        self.assertEqual((r["result"], r["settled_at"][:10]), ("no", "2026-11-20"))
        self.assertIn("Settled NO", r["outcome_note"])
        self.assertEqual(r["status"], "open")                 # as it was at the snapshot

    def test_subject_pulls_in_markets_outside_the_categories(self):
        rows, _ = universe(NOV9, ["Jensen Huang testify Senate"])
        r = next(x for x in rows if x["market_ticker"] == "KXHUANGSENATE-27")   # category World, not in the list
        self.assertIn("subject:", r["matched_keywords"])
        self.assertNotIn("KXHUANGSENATE-27", {x["market_ticker"] for x in universe(NOV9, [])[0]})


class Matching(unittest.TestCase):
    def test_subject_match_up_to_three_horizons_box_only(self):
        rows, as_of = universe(NOV9)
        v = M.market_view(rows, "other", "neutral", None, as_of, "Jensen Huang return as Nvidia CEO")
        self.assertTrue(v["ok"])
        self.assertEqual([r["event_ticker"] for r in v["rows"]], ["KXNVDACEO-26NOV20", "KXNVDACEO-26NOV30", "KXNVDACEO-26DEC31"])
        self.assertEqual((v["factor"], v["agreement"], v["match"]), (1.0, "auto_matched", "auto"))
        self.assertEqual(v["rows"][2]["p_yes"], 0.22)
        self.assertNotIn("KXHUANGSENATE-27", [r["event_ticker"] for r in v["rows"]])   # only 2 of 5 subject words

    def test_vetted_topic_point_in_time_and_factor(self):
        rows, as_of = universe(NOV9)
        v = M.market_view(rows, "fed_cut", "yes", date(2026, 12, 9), as_of)
        self.assertEqual((v["rows"][0]["p_yes"], v["agreement"], v["factor"]), (0.5, "split", 1.0))
        v = M.market_view(rows, "government_shutdown", "no", date(2027, 1, 30), as_of)
        self.assertEqual((v["agreement"], v["factor"]), ("agrees", 1.06))

    def test_unconfigured_topic_skips_or_falls_back_to_subject(self):
        rows, as_of = universe(NOV9)
        self.assertFalse(M.market_view(rows, "debt_limit_breach", "yes", date(2027, 1, 15), as_of)["ok"])
        v = M.market_view(rows, "recession", "yes", None, as_of, "Jensen Huang return as Nvidia CEO")
        self.assertEqual((v["ok"], v["factor"]), (True, 1.0))

    def test_attach_writes_one_box_per_card(self):
        with tempfile.TemporaryDirectory() as t:
            res = A.main(["--week", "2026-11-09", "--candidates", str(SAMPLE), "--offline", "--out-dir", t,
                          "--kalshi-root", str(Path(t) / "kalshi")])
            saved = json.loads((Path(t) / "market_views_2026-11-09.json").read_text())
            self.assertTrue((Path(t) / "kalshi" / "2026-11-09" / "kalshi_candidates.csv").exists())
        self.assertEqual(saved["as_of"], "2026-11-16T05:00+00:00")
        cards = res["cards"]
        self.assertEqual(set(cards), {"FICC-GSD-01", "RDS-02", "XE-SHUTDOWN-01", "ECS-NSCC-LIQ", "AS-02"})
        self.assertEqual(cards["AS-02"]["match"], "auto")
        self.assertLessEqual(len(cards["ECS-NSCC-LIQ"]["rows"]), 3)
        self.assertEqual(cards["ECS-NSCC-LIQ"]["rows"][0]["question"], "Will there be a government shutdown?")   # vetted leads
        self.assertEqual([s["candidate_id"] for s in res["skipped"]], ["CAND-TEST-5"])


if __name__ == "__main__":
    unittest.main()
