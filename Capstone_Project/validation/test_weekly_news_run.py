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
        self.feed_args=[]

    def google(self, config, queries, monday, out):
        out.mkdir(parents=True, exist_ok=True)
        return [], [], {"kept_after_cap": 0}, []

    def feeds(self, argv):
        self.feed_args=argv
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
        self.official=self.root/'official.csv';self.official.write_text('document_id,title,url,publication_date,published_at_utc,summary,source_id\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_week(self, fakes, **kw):
        return W.run_week(MONDAY, Decimal("1.00"), today=date(2026, 11, 9), run_id="t", weekly_dir=self.root / "weekly",
                          review_dir=self.root / "review", context_path=self.root / "context_news.csv",
                          collect_google=fakes.google, collect_feeds=fakes.feeds, classify=fakes.classify,
                          official_news=kw.pop('official_news',self.official), **kw)

    def test_original_official_export_and_window_are_passed_to_collector(self):
        f=Fakes();self.run_week(f,collect_only=True)
        self.assertEqual(f.feed_args[f.feed_args.index('--official')+1],str(self.official))
        self.assertEqual(f.feed_args[f.feed_args.index('--week-start')+1],'2026-11-02')
        self.assertEqual(f.feed_args[f.feed_args.index('--week-end')+1],'2026-11-08')

    def test_collect_only_never_calls_classifier(self):
        f=Fakes();res=self.run_week(f,collect_only=True)
        self.assertEqual(f.calls,[])
        self.assertEqual(res['status'],'collected_for_review_no_model_calls')
        self.assertFalse((self.root/'review').exists())

    def test_dry_run_never_pays_even_when_estimate_exceeds_cap(self):
        f=Fakes(estimate='9');res=self.run_week(f,dry_run=True)
        self.assertEqual([a.dry_run for a in f.calls],[True])
        self.assertEqual(res['status'],'dry_run_no_model_calls')
        self.assertTrue(res['estimate_above_cap'])

    def test_missing_official_export_does_not_silently_drop_it(self):
        f=Fakes();res=self.run_week(f,official_news=self.root/'missing.csv')
        self.assertEqual(res['status'],'stopped_official_export_unavailable')
        self.assertEqual(f.calls,[])

    def test_uncertain_prior_call_is_not_reported_as_complete(self):
        f=Fakes();normal=f.classify
        def classify(args):
            value=normal(args)
            if not args.dry_run:value['unreported_cost_reserve_usd']='0.09'
            return value
        f.classify=classify
        res=self.run_week(f)
        self.assertEqual(res['status'],'stopped_unresolved_cost_reserve')
        self.assertFalse((self.root/'review').exists())

    def test_unresolved_earlier_run_blocks_new_paid_batch(self):
        old=self.root/'weekly/2026-11-02/old/classifier_runs/v15/summary.json'
        old.parent.mkdir(parents=True);old.write_text(json.dumps({'unreported_cost_reserve_usd':'0.092103','status':'invocation_error'}))
        f=Fakes();res=self.run_week(f)
        self.assertEqual(res['status'],'stopped_unresolved_prior_cost_reserve')
        self.assertEqual([a.dry_run for a in f.calls],[True])
        self.assertEqual(res['pending_reservations'][0]['unreported_cost_reserve_usd'],'0.092103')

    def test_bad_run_id_is_rejected_before_collection(self):
        with self.assertRaises(ValueError):
            W.run_week(MONDAY,Decimal('1'),today=date(2026,11,9),run_id='../escape',weekly_dir=self.root/'weekly')

    def test_interrupted_running_receipt_blocks_paid_batch(self):
        old=self.root/'weekly/2026-11-02/old/classifier_runs/v15/summary.json'
        old.parent.mkdir(parents=True);old.write_text(json.dumps({'unreported_cost_reserve_usd':'0','status':'running'}))
        f=Fakes();res=self.run_week(f)
        self.assertEqual(res['status'],'stopped_unresolved_prior_cost_reserve')
        self.assertEqual([a.dry_run for a in f.calls],[True])

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



class CostReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.week = self.root / "2026-11-02"; self.ledger = self.root / "cost_reconciliations.csv"
        self.old = self.week / "run_a/classifier_runs/v15/summary.json"; self.old.parent.mkdir(parents=True)
        self.old.write_text(json.dumps({"unreported_cost_reserve_usd": "0.092103", "status": "invocation_error"}))

    def tearDown(self):
        self.tmp.cleanup()

    def pending(self):
        return W.unresolved_reservations(self.week, self.week / "run_new", ledger=self.ledger)

    def test_recorded_as_charged_unblocks_and_receipt_is_untouched(self):
        from . import weekly_cost_reconcile as R
        before = self.old.read_bytes()
        self.assertEqual(len(self.pending()), 1)
        row = R.reconcile(self.old, "Wenqi Cai", "billing cannot be confirmed per request", ledger=self.ledger, now="2026-11-09T22:00Z")
        self.assertEqual((row["reserved_usd"], row["recorded_charge_usd"], row["basis"]), ("0.092103", "0.092103", "upper_bound_recorded_as_charged"))
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.old.read_bytes(), before)                         # the original receipt is never edited
        with self.assertRaises(SystemExit):
            R.reconcile(self.old, "Wenqi Cai", "again", ledger=self.ledger)     # no duplicate rows

    def test_changed_receipt_or_partial_charge_blocks_again(self):
        from . import weekly_cost_reconcile as R
        R.reconcile(self.old, "Wenqi Cai", "upper bound", ledger=self.ledger)
        self.old.write_text(json.dumps({"unreported_cost_reserve_usd": "0.2", "status": "invocation_error"}))
        self.assertEqual(len(self.pending()), 1)                                # sha256 no longer matches
        rows = list(csv.DictReader(self.ledger.open()))
        rows[0].update(summary_sha256=__import__("hashlib").sha256(self.old.read_bytes()).hexdigest(), recorded_charge_usd="0.1")
        with self.ledger.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=W.RECONCILIATION_FIELDS); w.writeheader(); w.writerows(rows)
        self.assertEqual(len(self.pending()), 1)                                # charge below the reserve

    def test_no_reservation_or_running_refused(self):
        from . import weekly_cost_reconcile as R
        clean = self.week / "run_b/classifier_runs/v15/summary.json"; clean.parent.mkdir(parents=True)
        clean.write_text(json.dumps({"unreported_cost_reserve_usd": "0", "status": "complete"}))
        with self.assertRaises(SystemExit):
            R.reconcile(clean, "Wenqi Cai", "x", ledger=self.ledger)
        self.old.write_text(json.dumps({"unreported_cost_reserve_usd": "0.09", "status": "running"}))
        with self.assertRaises(SystemExit):
            R.reconcile(self.old, "Wenqi Cai", "x", ledger=self.ledger)


if __name__ == "__main__":
    unittest.main()
