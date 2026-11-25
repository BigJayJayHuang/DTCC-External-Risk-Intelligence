"""Offline tests for kalshi_candidates.py (simulated fixtures). python3 -m unittest test_kalshi_candidates -v"""
import csv
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kalshi_candidates as K  # noqa: E402
from fixture_client import FixtureClient  # noqa: E402

CFG = json.loads((HERE / "config" / "candidates.json").read_text())
FX = FixtureClient(HERE / "fixtures" / "candidates")
SNAP = date(2026, 11, 30)
LIVE = datetime(2026, 11, 30, 21, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 12, 2, 15, 0, tzinfo=timezone.utc)


def read(p):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Select(unittest.TestCase):
    def setUp(self):
        self.s = K.Selector(CFG)

    def keep(self, title, cat="Economics", ticker="KXTEST-1", close="2027-03-01T00:00:00Z"):
        return self.s.check({"event_ticker": ticker, "category": cat, "title": title},
                            {"ticker": ticker, "status": "active", "close_time": close}, SNAP)[0]

    def test_whole_words_only(self):
        self.assertFalse(self.keep("Corporate earnings in the second quarter", "Financials"))   # not "rate", not "SEC"
        self.assertFalse(self.keep("Will Spain win the cup?"))                                   # not "AI"
        self.assertTrue(self.keep("Will the SEC approve the rule?", "Financials"))
        self.assertTrue(self.keep("Fed funds rate after the meeting"))
        self.assertTrue(self.keep("New AI model released", "Science and Technology"))

    def test_politics_needs_government_keyword(self):
        self.assertTrue(self.keep("Government shutdown by January?", "Politics"))
        self.assertFalse(self.keep("Will the speech mention the unemployment rate?", "Politics"))

    def test_crypto_regulation_kept_price_levels_dropped(self):
        self.assertTrue(self.keep("Stablecoin bill signed into law", "Crypto"))
        self.assertFalse(self.keep("Bitcoin price above $150,000 on Dec 31", "Crypto"))
        self.assertFalse(self.keep("Ethereum ETF approved", "Crypto"))   # no regulation keyword in the list

    def test_excludes(self):
        self.assertFalse(self.keep("Fed cuts and Chiefs win", ticker="KXMVECROSS-1"))
        self.assertFalse(self.keep("Fed decision", "Sports"))
        self.assertFalse(self.keep("CPI in 2029", close="2029-01-01T00:00:00Z"))   # beyond 18 months


class Snapshot(unittest.TestCase):
    def test_live_run(self):
        with tempfile.TemporaryDirectory() as t:
            out, rows, log = K.run(SNAP, FX, CFG, Path(t), LIVE)
            got = read(out / "kalshi_candidates.csv")
            self.assertEqual(list(got[0].keys()), K.COLUMNS)
            ids = {r["market_ticker"] for r in got}
            self.assertEqual(ids, {"KXFEDDECISION-26DEC-H0", "KXFEDDECISION-26DEC-C25", "KXFEDDECISION-26DEC-H25", "KXGOVSHUT-27JAN30",
                                   "KXSTABLE-27", "KXAILAW-27", "KXHURLAND-27"})
            h0 = next(r for r in got if r["market_ticker"].endswith("H0"))
            self.assertEqual((h0["prob_now"], h0["prob_source"], h0["market_title"]), ("0.62", "live_quote", "Hold"))
            self.assertAlmostEqual(float(h0["change_7d_pts"]), (0.62 - float(h0["prob_7d_ago"])) * 100, places=1)
            ai = next(r for r in got if r["market_ticker"] == "KXAILAW-27")
            self.assertEqual((ai["prob_7d_ago"], ai["change_7d_pts"], ai["liquidity_ok"]), ("", "", "N"))   # opened Nov 27
            self.assertTrue(all(r[k] == "" for r in got for k in K.MAPPING))
            self.assertTrue((out / "raw" / "events.json").exists())
            self.assertLessEqual(len(h0["rules_short"]), 200)

    def test_run_after_snapshot_uses_candle_close(self):
        with tempfile.TemporaryDirectory() as t:
            out, rows, log = K.run(SNAP, FX, CFG, Path(t), LATER)
            h0 = next(r for r in read(out / "kalshi_candidates.csv") if r["market_ticker"].endswith("H0"))
            self.assertEqual((h0["prob_source"], h0["snapshot_utc"]), ("candle_close", "2026-11-30T21:00Z"))
            self.assertEqual(h0["prob_now"], "0.62")                  # fixture path reaches 0.62 on Nov 30, then keeps going

    def test_rerun_keeps_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            out, *_ = K.run(SNAP, FX, CFG, Path(t), LIVE)
            rows = read(out / "kalshi_candidates.csv")
            for r in rows:
                if r["market_ticker"] == "KXGOVSHUT-27JAN30":
                    r.update(risk_family="Regulatory", business_lines="All", approved="Y")
            with (out / "kalshi_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=K.COLUMNS); w.writeheader(); w.writerows(rows)
            out, _, log = K.run(SNAP, FX, CFG, Path(t), LIVE)
            r = next(x for x in read(out / "kalshi_candidates.csv") if x["market_ticker"] == "KXGOVSHUT-27JAN30")
            self.assertEqual((r["risk_family"], r["approved"], log["mapping_rows_kept"]), ("Regulatory", "Y", 1))

    def test_failure_keeps_previous_snapshot(self):
        class Broken(FixtureClient):
            def candles(self, *a, **k):
                raise RuntimeError("HTTP 503")
        with tempfile.TemporaryDirectory() as t:
            out, *_ = K.run(SNAP, FX, CFG, Path(t), LIVE)
            before = (out / "kalshi_candidates.csv").read_bytes()
            with self.assertRaises(SystemExit):
                K.run(SNAP, Broken(HERE / "fixtures" / "candidates"), CFG, Path(t), LIVE)
            self.assertEqual((out / "kalshi_candidates.csv").read_bytes(), before)
            self.assertEqual(len(list((Path(t) / "_errors").glob("*.json"))), 1)
            self.assertFalse(any(p.name.endswith(".tmp") for p in Path(t).iterdir()))


if __name__ == "__main__":
    unittest.main()
