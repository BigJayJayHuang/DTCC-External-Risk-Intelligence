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
NOV16, NOV23 = date(2026, 11, 16), date(2026, 11, 23)
AS_OF = K.as_of_for(NOV16)


def read(p):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Select(unittest.TestCase):
    def setUp(self):
        self.s = K.Selector(CFG)

    def keep(self, title, cat="Economics", ticker="KXTEST-1", close="2027-03-01T00:00:00Z", opened="2026-10-01T00:00:00Z"):
        return self.s.check({"event_ticker": ticker, "category": cat, "title": title},
                            {"ticker": ticker, "status": "active", "close_time": close, "open_time": opened}, AS_OF, False)[0]

    def test_as_of_is_sunday_close_eastern(self):
        self.assertEqual(AS_OF, datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc))

    def test_whole_words_only(self):
        self.assertFalse(self.keep("Corporate earnings in the second quarter", "Financials"))
        self.assertFalse(self.keep("Will Spain win the cup?"))
        self.assertTrue(self.keep("Will the SEC approve the rule?", "Financials"))
        self.assertTrue(self.keep("New AI model released", "Science and Technology"))
        self.assertTrue(self.keep("Nvidia market cap above $5T", "Companies"))
        self.assertTrue(self.keep("VIX above 30 on Friday", "Financials"))

    def test_politics_and_crypto_rules(self):
        self.assertTrue(self.keep("Government shutdown by January?", "Politics"))
        self.assertFalse(self.keep("Will the speech mention the unemployment rate?", "Politics"))
        self.assertTrue(self.keep("Stablecoin bill signed into law", "Crypto"))
        self.assertFalse(self.keep("Bitcoin price above $150,000 on Dec 31", "Crypto"))

    def test_point_in_time_and_excludes(self):
        self.assertFalse(self.keep("Fed decision", opened="2026-11-24T00:00:00Z"))      # opened after the snapshot
        self.assertFalse(self.keep("Fed decision", close="2026-11-20T00:00:00Z"))       # closed before it
        self.assertFalse(self.keep("Fed cuts and Chiefs win", ticker="KXMVECROSS-1"))
        self.assertFalse(self.keep("Fed decision", "Sports"))
        self.assertFalse(self.keep("CPI in 2029", close="2029-01-01T00:00:00Z"))


class Snapshot(unittest.TestCase):
    def test_columns_and_mapping_blank(self):
        with tempfile.TemporaryDirectory() as t:
            out, rows, log = K.run(NOV16, FX, CFG, Path(t), K.OFFLINE_NOW)
            got = read(out / "kalshi_candidates.csv")
            self.assertEqual(list(got[0].keys()), K.COLUMNS)
            self.assertTrue(all(r[k] == "" for r in got for k in K.MAPPING))
            self.assertTrue((out / "raw" / "markets_closed_since.json").exists())
            self.assertEqual(log["mode"].split()[0], "candle_close")
            self.assertLessEqual(max(len(r["rules_short"]) for r in got), 200)
            ai = next(r for r in got if r["market_ticker"] == "KXAILAW-27")
            self.assertEqual((ai["prob_7d_before"], ai["change_7d_pts"]), ("", ""))        # opened Nov 18

    def test_current_week_uses_live_quotes(self):
        with tempfile.TemporaryDirectory() as t:
            out, rows, log = K.run(NOV23, FX, CFG, Path(t), K.OFFLINE_NOW)
            h0 = next(r for r in rows if r["market_ticker"].endswith("H0"))
            self.assertEqual((h0["prob_source"], h0["prob_as_of"], h0["result"]), ("live_quote", 0.62, "open"))

    def test_rerun_keeps_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            out, *_ = K.run(NOV16, FX, CFG, Path(t), K.OFFLINE_NOW)
            rows = read(out / "kalshi_candidates.csv")
            for r in rows:
                if r["market_ticker"] == "KXGOVSHUT-27JAN30":
                    r.update(risk_family="Regulatory", business_lines="All", approved="Y")
            with (out / "kalshi_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=K.COLUMNS); w.writeheader(); w.writerows(rows)
            out, _, log = K.run(NOV16, FX, CFG, Path(t), K.OFFLINE_NOW)
            r = next(x for x in read(out / "kalshi_candidates.csv") if x["market_ticker"] == "KXGOVSHUT-27JAN30")
            self.assertEqual((r["risk_family"], r["approved"], log["mapping_rows_kept"]), ("Regulatory", "Y", 1))

    def test_failure_keeps_previous_snapshot(self):
        class Broken(FixtureClient):
            def candles(self, *a, **k):
                raise RuntimeError("HTTP 503")
        with tempfile.TemporaryDirectory() as t:
            out, *_ = K.run(NOV16, FX, CFG, Path(t), K.OFFLINE_NOW)
            before = (out / "kalshi_candidates.csv").read_bytes()
            with self.assertRaises(SystemExit):
                K.run(NOV16, Broken(HERE / "fixtures" / "candidates"), CFG, Path(t), K.OFFLINE_NOW)
            self.assertEqual((out / "kalshi_candidates.csv").read_bytes(), before)
            self.assertEqual(len(list((Path(t) / "_errors").glob("*.json"))), 1)
            self.assertFalse(any(p.name.endswith(".tmp") for p in Path(t).iterdir()))


if __name__ == "__main__":
    unittest.main()
