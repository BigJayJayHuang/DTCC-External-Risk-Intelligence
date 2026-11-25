"""Offline tests: python3 -m unittest test_prediction_markets -v  (no network needed)."""
import io
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kalshi_client as K  # noqa: E402
import signals as S  # noqa: E402
import test1 as T1  # noqa: E402
from fixture_client import FixtureClient  # noqa: E402

NOW = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)
CFG = json.loads((HERE / "config" / "series.json").read_text())


class Parsing(unittest.TestCase):
    def test_to_float(self):
        self.assertEqual(K.to_float("0.6800"), 0.68)
        self.assertIsNone(K.to_float(""))
        self.assertEqual(K.to_float(None, 0.0), 0.0)

    def test_market_prob_mid_then_fallback(self):
        self.assertEqual(K.market_prob({"yes_bid_dollars": "0.60", "yes_ask_dollars": "0.64"}), 0.62)
        self.assertEqual(K.market_prob({"yes_bid_dollars": "", "yes_ask_dollars": "", "last_price_dollars": "0.33"}), 0.33)
        self.assertIsNone(K.market_prob({}))

    def test_candle_close_uses_bid_ask_when_no_trade(self):
        c = {"price": {}, "yes_bid": {"close_dollars": "0.40"}, "yes_ask": {"close_dollars": "0.44"}}
        self.assertAlmostEqual(K.candle_close(c), 0.42)


class Helpers(unittest.TestCase):
    def test_pick_event_nearest_unresolved(self):
        ms = [{"event_ticker": "A", "close_time": "2026-12-09T19:00:00Z"}, {"event_ticker": "B", "close_time": "2027-01-28T19:00:00Z"},
              {"event_ticker": "OLD", "close_time": "2026-10-28T19:00:00Z"}]
        ev, mk = S.pick_event(ms, NOW)
        self.assertEqual(ev, "A")

    def test_repricing(self):
        self.assertEqual(S.repricing_pp({"x": 0.68}, {"x": 0.33}), 35.0)
        self.assertEqual(S.repricing_pp({"h": 0.62, "c": 0.34, "b": 0.04}, {"h": 0.41, "c": 0.54, "b": 0.05}), 21.0)
        self.assertIsNone(S.repricing_pp({"x": 0.5}, {}))

    def test_certainty_thresholds(self):
        self.assertEqual([S.certainty_from_prob(p) for p in (0.1, 0.3, 0.69, 0.7, 0.95)], [0, 1, 1, 2, 2])


class Build(unittest.TestCase):
    def setUp(self):
        self.res = S.build(FixtureClient(HERE / "fixtures"), CFG, date(2026, 11, 23), NOW)
        self.by = {s.get("series"): s for s in self.res["signals"]}

    def test_fed_repricing_signal(self):
        f = self.by["KXFEDDECISION"]
        self.assertTrue(f["ok"])
        self.assertEqual(f["event_ticker"], "KXFEDDECISION-26DEC")      # settled Oct market ignored
        self.assertGreaterEqual(f["repricing_pp"], 20)
        self.assertTrue(f["jump"])
        self.assertEqual(f["top_outcomes"][0]["outcome"], "Hold")

    def test_thin_market_not_used(self):
        self.assertFalse(self.by["KXCPI"]["ok"])
        self.assertIn("thin", self.by["KXCPI"]["reason"])

    def test_shutdown_feeds_rubric(self):
        g = self.by["KXGOVSHUT"]
        self.assertTrue(g["ok"])
        self.assertAlmostEqual(g["prob"], 0.68)
        self.assertEqual(g["rubric"]["certainty"], 1)                    # 68% < 70% -> certainty 1
        self.assertEqual(g["rubric"]["effect_date"], "2026-12-12")
        if g["rubric"].get("S") is not None:                            # only when validation/event_scoring.py is importable
            self.assertIn(g["rubric"]["S"], (1, 2, 3, 4, 5))
            self.assertTrue(g["rubric"]["needs_review"])

    def test_by_chain_index(self):
        self.assertIn("KXFEDDECISION", self.res["by_chain"]["FICC-GSD-01"])
        self.assertIn("KXGOVSHUT", self.res["by_chain"]["XE-SHUTDOWN-01"])
        self.assertNotIn("FICC-DEBT-01", self.res["by_chain"])             # no ticker yet

    def test_missing_ticker_is_skipped_not_crashed(self):
        skipped = [s for s in self.res["signals"] if not s.get("series")]
        self.assertTrue(all(not s["ok"] for s in skipped))


class Client(unittest.TestCase):
    def test_pagination_and_retry(self):
        pages = [HTTPError("u", 429, "too many", {}, io.BytesIO(b"{}")),
                 io.BytesIO(json.dumps({"markets": [{"ticker": "A"}], "cursor": "c1"}).encode()),
                 io.BytesIO(json.dumps({"markets": [{"ticker": "B"}], "cursor": ""}).encode())]

        def opener(req, timeout=None):
            p = pages.pop(0)
            if isinstance(p, Exception):
                raise p
            return p
        c = K.KalshiClient(opener=opener, min_interval=0)
        with mock.patch.object(K.time, "sleep"):
            ms = c.markets(series_ticker="X")
        self.assertEqual([m["ticker"] for m in ms], ["A", "B"])


class Test1(unittest.TestCase):
    def test_pass_when_spikes_sit_in_windows(self):
        start = date(2024, 1, 1)
        series = []
        for i in range(500):
            d = start + timedelta(days=i)
            v = 1.0 + (i % 7) * 0.1
            if date(2024, 8, 1) <= d <= date(2024, 8, 9) or date(2025, 4, 2) <= d <= date(2025, 4, 11):
                v = 15.0
            series.append((d, v))
        w = json.loads((HERE / "config" / "windows.json").read_text())["KXFEDDECISION"]
        r = T1.test1(series, w)
        self.assertEqual(r["hits"], 2)
        self.assertEqual(r["result"], "PASS")

    def test_daily_repricing_from_history_rows(self):
        rows = [{"date": "2026-11-20", "event_ticker": "E", "ticker": "h", "prob": "0.40", "event_close": "2026-12-09"},
                {"date": "2026-11-20", "event_ticker": "E", "ticker": "c", "prob": "0.60", "event_close": "2026-12-09"},
                {"date": "2026-11-21", "event_ticker": "E", "ticker": "h", "prob": "0.50", "event_close": "2026-12-09"},
                {"date": "2026-11-21", "event_ticker": "E", "ticker": "c", "prob": "0.50", "event_close": "2026-12-09"}]
        self.assertEqual(T1.daily_repricing(rows), [(date(2026, 11, 21), 10.0)])


class Collect(unittest.TestCase):
    def test_history_offline_writes_csv(self):
        import collect as C
        with tempfile.TemporaryDirectory() as d, mock.patch.object(C, "OUT", Path(d)):
            rows = C.main(["history", "--series", "KXGOVSHUT", "--days", "3650", "--offline"])
            self.assertTrue((Path(d) / "history" / "KXGOVSHUT.csv").exists())
            self.assertGreater(len(rows), 0)

    def test_discover_offline(self):
        import collect as C
        hits = C.main(["discover", "--search", "debt", "--offline"])
        self.assertEqual(hits[0]["ticker"], "KXDEBTLIMIT")


if __name__ == "__main__":
    unittest.main()
