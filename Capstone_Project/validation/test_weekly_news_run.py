"""Offline tests for validation/weekly_news_run.py with fake collectors and a fake classifier (no network, no AWS)."""
import csv, json, tempfile, unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import weekly_news_run as W
from .llm_classifier import PROJECT
from .test_review_promote import CAND_FIELDS, cand

MONDAY = date(2026, 11, 2)


class Fakes:
    def __init__(self, estimate="0.50", cands=None):
        self.estimate, self.cands, self.calls = Decimal(estimate), cands or [], []

    def google(self, config, queries, monday, out):
        out.mkdir(parents=True, exist_ok=True)
        return [], [], {"kept_after_cap": 0}, []

    def feeds(self, argv):
        out = Path(argv[argv.index("--out-dir") + 1]); out.mkdir(parents=True, exist_ok=True)
        (out / "classifier_input.csv").write_text("document_id,title,url,publication_date,published_at_utc,summary,source_id\n")
        return {"items_to_classifier": 3, "scope_totals": {"headline_only": 3}, "published_range": ["2026-11-02", "2026-11-06"]}

    def classify(self, args):
        self.calls.append(args)
        assert (args.prompt_version, args.response_schema, args.prompt_cache, args.budget) == (W.PROMPT_VERSION, "flat", "on", Decimal("1.00"))
        if args.dry_run:
            return {"estimated_full_run_cost_with_cache_usd": str(self.estimate), "estimated_full_run_cost_usd": "9", "coverage": {"selected_articles": 3}}
        with (args.output_dir / f"candidates_{args.run_date.isoformat()}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAND_FIELDS); w.writeheader(); w.writerows(self.cands)
        return {"status": "complete", "relevant": len(self.cands), "irrelevant": 0, "failed_checks": 0, "estimated_cost_usd": "0.40"}


class WeeklyRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_week(self, fakes, **kw):
        return W.run_week(MONDAY, Decimal("1.00"), today=date(2026, 11, 9), run_id="t", weekly_dir=self.root / "weekly",
                          review_dir=self.root / "review", context_path=self.root / "context_news.csv",
                          collect_google=fakes.google, collect_feeds=fakes.feeds, classify=fakes.classify, **kw)

    def test_stops_when_estimate_above_cap(self):
        f = Fakes(estimate="1.01")
        res = self.run_week(f)
        self.assertEqual(res["status"], "stopped_estimate_above_cap")
        self.assertEqual([a.dry_run for a in f.calls], [True])                       # no paid run
        self.assertFalse((self.root / "review").exists())
        self.assertEqual(json.loads((self.root / "weekly/2026-11-02/t/weekly_summary.json").read_text())["status"], "stopped_estimate_above_cap")

    def test_full_run_writes_review_sheet_and_context(self):
        cands = [cand("A", "Tech stocks log worst day since 2020", "ECS-NSCC-LIQ", "MarketWatch", etype="market_move"),
                 cand("C", "SEC sets new compliance date for Treasury repo clearing", "FICC-GSD-03", "SEC", tier="regulator", etype="regulatory")]
        for c in cands:
            c["article_file"] = ""
        f = Fakes(cands=cands)
        res = self.run_week(f)
        self.assertEqual((res["status"], res["proposed_events"], res["tiers"]["context"]), ("complete", 2, 1))
        self.assertEqual([a.dry_run for a in f.calls], [True, False])
        with (self.root / "review/review_2026-11-02.csv").open() as fh:
            tiers = sorted(r["review_tier"] for r in csv.DictReader(fh))
        self.assertEqual(tiers, sorted(t for t, n in res["tiers"].items() for _ in range(n)))
        with (self.root / "context_news.csv").open() as fh:
            self.assertEqual([(r["card_id"], r["event_type"]) for r in csv.DictReader(fh)], [("ECS-NSCC-LIQ", "market_move")])
        self.assertIn("promote_reviewed --sheet", res["next_step"])

    def test_refuses_unfinished_week_and_keeps_existing_sheet(self):
        with self.assertRaises(SystemExit):
            W.run_week(MONDAY, Decimal("1.00"), today=date(2026, 11, 8))             # Sunday 11-08 not over
        (self.root / "review").mkdir()
        (self.root / "review/review_2026-11-02.csv").write_text("existing decisions\n")
        res = self.run_week(Fakes(cands=[]))
        self.assertTrue(res["review_sheet"].endswith("review_2026-11-02_t.csv"))
        self.assertEqual((self.root / "review/review_2026-11-02.csv").read_text(), "existing decisions\n")

    def test_from_inputs_skips_collection(self):
        f = Fakes(cands=[])
        boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("collector called"))
        saved = self.root / "saved.csv"; saved.write_text("document_id,title,url,publication_date,published_at_utc,summary,source_id\n")
        res = W.run_week(MONDAY, Decimal("1.00"), today=date(2026, 11, 9), run_id="r", weekly_dir=self.root / "weekly",
                         review_dir=self.root / "review", context_path=self.root / "c.csv", collect_google=boom, collect_feeds=boom,
                         classify=f.classify, from_inputs=saved)
        self.assertEqual((res["status"], res["inputs_reused"]), ("complete", str(saved)))
        self.assertTrue(all(a.news == saved for a in f.calls))
        self.assertEqual(W.PROMPT_VERSION, "v1.6")

    def test_week_start_must_be_monday(self):
        with self.assertRaises(ValueError):
            W.run_week(date(2026, 11, 3), Decimal("1"), today=date(2026, 11, 20))


if __name__ == "__main__":
    unittest.main()
