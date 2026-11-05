"""Offline incremental-run, durable-budget and role-authentication contracts."""
import copy
import csv
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import llm_classifier as C
from . import llm_daily as D
from . import llm_daily_release as R
from . import test_llm_classifier as F
from .test_llm_classifier import FakeSession, error, relevant, response


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture = F.ClassifierTests().fixture_args(self.temporary.name)
        self.real_bootstrap = D.BOOTSTRAP
        for target, name, value in [(C, "REGISTER", fixture.register), (C, "MAJOR", fixture.major),
                                    (D, "BOOTSTRAP", self.root / "missing-bootstrap")]:
            context = patch.object(target, name, value)
            context.start(); self.addCleanup(context.stop)
        self.args = D.parser().parse_args(["prepare", "--state-file", str(self.root / "state.json"),
            "--news", str(fixture.news), "--output-dir", str(self.root / "runtime"),
            "--run-id", "daily-one", "--run-date", "2026-11-05"])

    def prepared(self):
        plan = D.prepare(self.args)
        self.args.plan = self.args.output_dir / self.args.run_id / "plan.json"
        return plan

    def state(self):
        return json.loads(self.args.state_file.read_text())

    def execute(self, values):
        session = FakeSession(values)
        with patch("builtins.print"):
            result = D.execute(self.args, session)
        return result, session

    def test_dry_run_builds_without_aws_or_state_changes(self):
        self.args.dry_run = True
        with patch("boto3.Session", side_effect=AssertionError("No AWS in dry run")):
            result = self.prepared()
        self.assertEqual((result["status"], result["selected_articles"]), ("dry_run", 2))
        self.assertFalse(self.args.state_file.exists())
        self.assertFalse(result["invoke"])
        self.assertNotIn(str(self.root), self.args.plan.read_text())

    def test_reserve_then_reconcile_candidates_and_skip_repeat(self):
        before = C.REGISTER.read_bytes()
        self.prepared()
        self.assertEqual(Decimal(self.state()["daily_cost_usd"]["2026-11-05"]), Decimal(10))
        result, session = self.execute([response(relevant()), response({"is_relevant": False, "notes": "fixture"})])
        self.assertEqual((result["relevant"], result["irrelevant"]), (1, 1))
        self.assertEqual(session.availability_calls, 1)
        state = self.state()
        self.assertFalse(state["reservations"])
        self.assertEqual(Decimal(state["daily_cost_usd"]["2026-11-05"]), Decimal(result["estimated_cost_usd"]))
        self.assertEqual(len(state["requests"]), 2)
        with (self.args.plan.parent / "candidates_2026-11-05.csv").open() as source:
            self.assertTrue(all(r["needs_review"] == "Y" for r in csv.DictReader(source)))
        self.args.run_id = "daily-two"
        plan = D.prepare(self.args)
        self.assertEqual((plan["selected_articles"], plan["already_classified"], plan["invoke"]), (0, 2, False))
        with (self.args.output_dir / self.args.run_id / "candidates_2026-11-05.csv").open() as source:
            self.assertEqual(list(csv.DictReader(source)), [])
        self.assertEqual(C.REGISTER.read_bytes(), before)

    def test_cost_cap_is_shared_across_same_day_runs(self):
        self.args.max_articles = 1
        self.prepared()
        first, _ = self.execute([response({"is_relevant": False, "notes": "fixture"})])
        self.args.run_id = "daily-two"
        plan = self.prepared()
        self.assertEqual(Decimal(plan["remaining_daily_budget_usd"]), Decimal(10) - Decimal(first["estimated_cost_usd"]))
        second, _ = self.execute([response({"is_relevant": False, "notes": "fixture"})])
        total = Decimal(first["estimated_cost_usd"]) + Decimal(second["estimated_cost_usd"])
        self.assertEqual(Decimal(self.state()["daily_cost_usd"]["2026-11-05"]), total)

    def test_changed_article_is_a_new_request(self):
        self.prepared()
        self.execute([response({"is_relevant": False, "notes": "fixture"})] * 2)
        self.args.news.write_text(self.args.news.read_text().replace("The SEC extended the deadline.", "Revised public feed text.", 1))
        self.args.run_id = "revision"
        plan = D.prepare(self.args)
        self.assertEqual((plan["selected_articles"], plan["already_classified"]), (1, 1))

    def test_interrupted_reservation_blocks_next_run_even_next_day(self):
        self.prepared()
        self.args.run_id = "another"
        self.args.run_date = self.args.run_date.replace(day=6)
        with self.assertRaisesRegex(ValueError, "Unreconciled"):
            D.prepare(self.args)

    def test_recovery_uses_saved_output_without_another_call(self):
        self.prepared()
        durable_before_invocation = self.args.state_file.read_bytes()
        result, session = self.execute([response({"is_relevant": False, "notes": "fixture"})] * 2)
        self.args.state_file.write_bytes(durable_before_invocation)
        recovered = D.reconcile(self.args)
        self.assertEqual(recovered["estimated_cost_usd"], result["estimated_cost_usd"])
        self.assertEqual(len(session.runtime.calls), 2)
        self.assertFalse(self.state()["reservations"])

    def test_access_error_stops_and_releases_known_unused_reservation(self):
        self.prepared()
        result, session = self.execute([error("AccessDeniedException", 403)])
        self.assertEqual(result["status"], "access_or_subscription_error")
        self.assertEqual(len(session.runtime.calls), 1)
        self.assertFalse(self.state()["reservations"])
        self.assertEqual(Decimal(self.state()["daily_cost_usd"]["2026-11-05"]), 0)

    def test_missing_usage_keeps_hold_and_cannot_be_reconciled_twice(self):
        self.prepared()
        value = response(relevant()); value.pop("usage")
        result, session = self.execute([value])
        self.assertEqual(result["status"], "cost_accounting_error")
        before = copy.deepcopy(self.state())
        self.assertTrue(before["reservations"])
        with self.assertRaisesRegex(ValueError, "already reconciled"):
            D.reconcile(self.args)
        self.assertEqual(self.state(), before)
        self.assertEqual(len(session.runtime.calls), 1)

    def test_bootstrap_is_idempotent_and_reconciles_paid_history(self):
        config = json.loads(C.CONFIG.read_text())
        state = D.read_state(self.args.state_file, config)
        D.bootstrap(state, self.real_bootstrap)
        first = copy.deepcopy(state)
        D.bootstrap(state, self.real_bootstrap)
        self.assertEqual(state, first)
        self.assertEqual(len(state["requests"]), 481)
        self.assertEqual(Decimal(state["daily_cost_usd"]["2026-11-05"]), Decimal("7.5383616"))

    def test_prepared_news_change_stops_before_invocation(self):
        self.prepared()
        news = self.args.plan.parent / "selected_news.csv"
        news.write_text(news.read_text() + "\n")
        session = FakeSession([])
        with self.assertRaisesRegex(ValueError, "news changed"):
            D.execute(self.args, session)
        self.assertEqual(len(session.runtime.calls), 0)

    def test_workload_auth_requires_temporary_credentials(self):
        config = json.loads(C.CONFIG.read_text())
        fake = SimpleNamespace(get_credentials=lambda: SimpleNamespace(token=True))
        with patch.dict(os.environ, {"BEDROCK_AUTH_MODE": "workload"}), patch("boto3.Session", return_value=fake) as factory:
            self.assertIs(C.aws_session(config), fake)
            factory.assert_called_once_with(region_name="us-east-2")
        fake = SimpleNamespace(get_credentials=lambda: SimpleNamespace(token=None))
        with patch.dict(os.environ, {"BEDROCK_AUTH_MODE": "workload"}), patch("boto3.Session", return_value=fake):
            with self.assertRaisesRegex(ValueError, "temporary"):
                C.aws_session(config)

    def test_deleted_release_cannot_reset_state(self):
        with patch.object(R, "gh", side_effect=[None, "existing tag"]):
            with self.assertRaisesRegex(ValueError, "tag remains"):
                R.restore(R.REPOSITORY, self.args.state_file)
        with patch.object(R, "gh", side_effect=[json.dumps({"assets": []})]):
            with self.assertRaisesRegex(ValueError, "asset missing"):
                R.restore(R.REPOSITORY, self.args.state_file)

    def test_evidence_published_before_final_state(self):
        self.prepared()
        calls = []
        def fake_gh(*args, **kwargs):
            calls.append(args)
            return json.dumps({"assets": []}) if args[0] == "api" else ""
        with patch.object(R, "gh", side_effect=fake_gh):
            result = R.publish(R.REPOSITORY, self.args.state_file, self.args.plan.parent)
        uploads = [c for c in calls if c[:2] == ("release", "upload")]
        self.assertTrue(uploads[0][-1].endswith("daily-one.zip"))
        self.assertTrue(uploads[1][-1].endswith(R.ASSET))
        self.assertEqual(result["paid_calls"], 0)

    def test_publication_recovery_reuses_identical_immutable_archive(self):
        self.prepared()
        with patch.object(R, "release", return_value={"assets": []}), patch.object(R, "gh", return_value=""):
            first = R.publish(R.REPOSITORY, self.args.state_file, self.args.plan.parent)
        prior = {"assets": [{"name": first["archive"], "digest": "sha256:" + first["sha256"]}]}
        with patch.object(R, "release", return_value=prior), patch.object(R, "gh", return_value="") as command:
            second = R.publish(R.REPOSITORY, self.args.state_file, self.args.plan.parent)
        self.assertEqual(first["sha256"], second["sha256"])
        uploads = [c.args for c in command.call_args_list if c.args[:2] == ("release", "upload")]
        self.assertEqual(len(uploads), 1)
        self.assertTrue(uploads[0][-1].endswith(R.ASSET))


if __name__ == "__main__":
    unittest.main()
