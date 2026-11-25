"""Offline tests for the market box (market_view.py, attach_market_views.py). python3 -m unittest test_market_view -v"""
import csv
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import attach_market_views as A  # noqa: E402
import market_view as M  # noqa: E402
from fixture_client import FixtureClient  # noqa: E402

NOW = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)
FX = FixtureClient(HERE / "fixtures")


class Factor(unittest.TestCase):
    def test_factor_mapping(self):
        self.assertEqual(M.factor_for(0.5, "yes"), 1.0)
        self.assertEqual(M.factor_for(0.8, "yes"), 1.15)
        self.assertEqual(M.factor_for(0.2, "no"), 0.85)
        self.assertEqual(M.factor_for(1.0, "yes"), 1.25)
        self.assertEqual(M.factor_for(0.0, "yes"), 0.75)
        self.assertEqual(M.factor_for(0.9, "neutral"), 1.0)          # no lean -> box only

    def test_combined_with_hype_stays_in_band(self):
        self.assertEqual(M.combine(1.25, 1.2), 1.25)
        self.assertEqual(M.combine(0.75, 0.8), 0.75)
        self.assertEqual(M.combine(1.1, 0.9), 0.99)

    def test_adjusted_shock_capped(self):
        self.assertEqual(M.adjusted_shock(4, 1.25), 5.0)
        self.assertEqual(M.adjusted_shock(3, 1.09), 3.3)
        self.assertIsNone(M.adjusted_shock(None, 1.1))


class View(unittest.TestCase):
    def test_fed_cut_sums_cut_outcomes_and_disagrees(self):
        v = M.market_view(FX, "fed_cut", "yes", date(2026, 12, 9), NOW)
        self.assertTrue(v["ok"])
        self.assertAlmostEqual(v["p_yes"], 0.365, places=3)          # Cut 25bp 34% + Cut >25bp 2.5%
        self.assertEqual(v["agreement"], "disagrees")
        self.assertEqual(v["factor"], 0.93)
        self.assertLess(v["change_pp"], 0)                            # cut odds fell over the week

    def test_shutdown_agrees(self):
        v = M.market_view(FX, "government_shutdown", "yes", date(2026, 12, 12), NOW)
        self.assertEqual((v["agreement"], v["factor"]), ("agrees", 1.09))
        self.assertEqual(v["p_yes_week_ago"], 0.33)

    def test_neutral_gets_box_without_factor(self):
        v = M.market_view(FX, "government_shutdown", "neutral", date(2026, 12, 12), NOW)
        self.assertTrue(v["ok"])
        self.assertEqual((v["agreement"], v["factor"]), ("no_lean", 1.0))

    def test_date_mismatch_and_missing_series(self):
        self.assertFalse(M.market_view(FX, "government_shutdown", "yes", date(2027, 3, 1), NOW)["ok"])
        self.assertIn("no Kalshi series", M.market_view(FX, "debt_limit_breach", "yes", date(2027, 1, 15), NOW)["reason"])


class Attach(unittest.TestCase):
    def test_attach_from_classifier_rows(self):
        with (HERE / "fixtures" / "candidates_v17_sample.csv").open() as f:
            rows = list(csv.DictReader(f))
        res = A.build(rows, FX, "2026-11-23", NOW)
        self.assertEqual(set(res["cards"]), {"FICC-GSD-01", "RDS-02", "XE-SHUTDOWN-01", "ECS-NSCC-LIQ"})
        self.assertEqual(res["cards"]["XE-SHUTDOWN-01"]["factor"], 1.09)
        self.assertEqual(res["cards"]["ECS-NSCC-LIQ"]["factor"], 1.0)
        self.assertEqual(res["cards"]["FICC-GSD-01"]["forward_quote"], "bets on a December Fed cut")
        self.assertEqual([s["candidate_id"] for s in res["skipped"]], ["CAND-TEST-5"])   # debt limit: no ticker yet

    def test_cli_offline_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            A.main(["--week", "2026-11-23", "--candidates", str(HERE / "fixtures" / "candidates_v17_sample.csv"), "--offline", "--out-dir", d])
            self.assertTrue((Path(d) / "market_views_2026-11-23_offline.json").exists())


if __name__ == "__main__":
    unittest.main()
