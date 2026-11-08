"""Offline contract, billing-guard and register-protection tests; no AWS calls."""
import argparse
import copy
import csv
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError
from jsonschema import Draft202012Validator, ValidationError

from . import llm_classifier as C


def relevant():
    return {"is_relevant": True, "same_as_event_id": None, "title": "Treasury clearing deadline extended",
            "summary": "A test-only regulator announcement.", "card_ids": ["FICC-GSD-03"], "certainty": 2,
            "reach": 2, "reach_basis": "market_wide", "named_participants": [], "announced_date": "2026-11-04",
            "effect_date": "2026-12-31", "stage": None, "source_tier": "regulator", "outlet": "SEC",
            "url": "https://www.sec.gov/test-only", "evidence_quotes": ["The SEC extended the deadline."],
            "confidence": 0.9, "notes": "Offline fixture; not a model prediction."}


def article():
    return {"document_id": "test-only", "title": "Test announcement", "url": "https://www.sec.gov/test-only",
            "published_date": "2026-11-04", "source_id": "sec_press", "outlet": "SEC", "source_tier": "regulator",
            "content_scope": "publisher_feed_summary", "text": "The SEC extended the deadline."}


def response(value=None, text=None, stop=None):
    content = [{"text": text}] if text is not None else [{"toolUse": {"toolUseId": "offline-test",
               "name": C.TOOL, "input": {"classification": value}}}]
    return {"output": {"message": {"role": "assistant", "content": content}},
            "stopReason": stop or ("end_turn" if text is not None else "tool_use"),
            "usage": {"inputTokens": 100, "outputTokens": 50}, "ResponseMetadata": {"RetryAttempts": 0}}


class FakeRuntime:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def converse(self, **request):
        self.calls.append(request)
        item = self.values.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeSession:
    def __init__(self, values):
        self.runtime = FakeRuntime(values)
        self.availability_calls = 0

    def client(self, name):
        return self.runtime if name == "bedrock-runtime" else self

    def get_caller_identity(self):
        return {"Account": "888840134592"}

    def get_foundation_model_availability(self, **kwargs):
        self.availability_calls += 1
        return {"agreementAvailability": {"status": "NOT_AVAILABLE"}}


def error(code, status=400):
    return ClientError({"Error": {"Code": code, "Message": "offline error"},
                        "ResponseMetadata": {"HTTPStatusCode": status}}, "Converse")


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.body, self.catalog, self.cards, _ = C.prompt_parts(C.PROMPT)
        self.schema = C.output_schema(self.cards)
        self.config = json.loads(C.CONFIG.read_text())

    def test_forced_strict_schema_supports_both_prompt_shapes(self):
        validator = Draft202012Validator(self.schema)
        validator.validate({"classification": relevant()})
        validator.validate({"classification": {"is_relevant": False, "notes": "unrelated"}})
        invalid = relevant(); invalid["certainty"] = True
        with self.assertRaises(ValidationError):
            validator.validate({"classification": invalid})
        request = C.build_request("original prompt", self.schema, self.config)
        self.assertEqual(request["toolConfig"]["toolChoice"], {"tool": {"name": C.TOOL}})
        self.assertTrue(request["toolConfig"]["tools"][0]["toolSpec"]["strict"])
        self.assertEqual(request["inferenceConfig"], {"temperature": 0, "maxTokens": self.config["max_tokens"]})   # 2000 since 2026-11-08

    def test_prompt_wording_and_literal_article_placeholders(self):
        a = article(); a["text"] += " {ARTICLE}"
        register = [{"event_id": "future", "announced_date": "2026-11-05"},
                    {"event_id": "known", "announced_date": "2026-11-01"}]
        filled, ids = C.render_prompt(self.body, self.catalog, register, a)
        self.assertEqual(ids, {"known"})
        expected = self.body.replace("{CARD_CATALOG}", self.catalog).replace("{RECENT_EVENTS}", json.dumps(register[1:])).replace("{ARTICLE}", json.dumps(a))
        self.assertEqual(filled, expected)
        self.assertIn("{ARTICLE}", filled)

    def test_tool_and_single_fence_fallback(self):
        value = relevant()
        self.assertEqual(C.parse_response(response(value)), (value, "tool", False))
        self.assertEqual(C.parse_response(response(text="```json\n" + json.dumps(value) + "\n```")), (value, "text", True))
        with self.assertRaises(C.ResponseParseError):
            C.parse_response(response(text="prefix ```json\n{}\n```"))
        with self.assertRaises(ValueError):
            C.parse_response(response(value, stop="max_tokens"))
        with self.assertRaises(C.ResponseParseError) as ctx:
            C.parse_response(response(text="```json\nnot JSON\n```"))
        self.assertTrue(ctx.exception.fence_fallback)

    def test_existing_checks_cap_major_firm_and_verify_evidence(self):
        value = relevant(); value.update(reach_basis="major_participant", named_participants=["Unknown Dealer"])
        with patch.object(C.E, "validate", wraps=C.E.validate) as validate:
            checked, reasons = C.check_classification(value, article(), self.schema, self.cards, set(), set())
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(checked["reach"], 1)
        self.assertTrue(any("reach capped" in s for s in reasons))
        value = relevant(); value["evidence_quotes"] = ["invented quote"]
        self.assertTrue(C.check_classification(value, article(), self.schema, self.cards, set(), set())[1])
        value = relevant(); value["effect_date"] = None
        self.assertTrue(any("missing" in s for s in C.check_classification(value, article(), self.schema, self.cards, set(), set())[1]))

    def test_only_throttling_retries_at_most_twice(self):
        runtime = FakeRuntime([error("ThrottlingException", 429), error("ThrottlingException", 429), response({"is_relevant": False, "notes": "x"})])
        delays, errors = [], []
        _, attempts = C.invoke(runtime, {}, lambda *x: errors.append(x), 2, 10, delays.append)
        self.assertEqual((attempts, len(runtime.calls), delays), (3, 3, [10, 20]))
        runtime = FakeRuntime([error("AccessDeniedException", 403)])
        with self.assertRaises(ClientError):
            C.invoke(runtime, {}, lambda *x: None, 2, 10, delays.append)
        self.assertEqual(len(runtime.calls), 1)
        runtime = FakeRuntime([error("ThrottlingException", 429)] * 3)
        with self.assertRaises(ClientError):
            C.invoke(runtime, {}, lambda *x: None, 2, 0, lambda x: None)
        self.assertEqual(len(runtime.calls), 3)

    def test_budget_cost_includes_cache_usage(self):
        usage = {"inputTokens": 1000, "outputTokens": 500, "cacheReadInputTokens": 100, "cacheWriteInputTokens": 100}
        self.assertEqual(C.token_cost(usage, self.config["pricing"]), Decimal("0.0119955"))

    def fixture_args(self, tmp):
        root = Path(tmp)
        news = root / "news.csv"
        with news.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["document_id", "title", "url", "publication_date", "published_at_utc", "summary", "source_id"])
            writer.writeheader()
            for identity, published in [("a", "2026-11-04"), ("b", "2026-11-04"), ("old", "2026-09-01"), ("invalid", "invalid")]:
                writer.writerow({"document_id": identity, "title": "Test announcement", "url": "https://www.sec.gov/" + ("test-only" if identity == "a" else identity),
                                 "publication_date": published, "summary": "The SEC extended the deadline.", "source_id": "sec_press"})
        register = root / "register.csv"
        register.write_text("event_id,title,card_ids,announced_date,effect_date\nEV1,old,FICC-GSD-03,2025-01-01,2026-12-31\n")
        major = root / "major.csv"; major.write_text("name\n")
        return argparse.Namespace(config=C.CONFIG, register=register, news=news, major=major, start=date(2026, 11, 1), end=date(2026, 11, 5),
                                  max_articles=None, budget=Decimal(10), dry_run=False, run_date=date(2026, 11, 5), run_id="offline", output_dir=root)

    def test_batch_records_unavailable_agreement_and_never_writes_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture_args(tmp); before = args.register.read_bytes()
            session = FakeSession([response(relevant()), response({"is_relevant": False, "notes": "unrelated"})])
            with patch("builtins.print"):
                result = C.run(args, session)
            self.assertEqual((result["articles_processed"], result["relevant"], result["irrelevant"]), (2, 1, 1))
            self.assertEqual(session.availability_calls, 1)
            self.assertEqual(args.register.read_bytes(), before)
            with (Path(tmp) / "candidates_2026-11-05.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["needs_review"], "Y")
            self.assertEqual(len(list((Path(tmp) / "classifier_runs/offline/raw").glob("*.json"))), 2)
            self.assertEqual(result["coverage"]["input_rejections"], {"missing_or_invalid_publication_date": 1})

    def test_tiny_budget_blocks_before_paid_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture_args(tmp); args.budget = Decimal("0.0001")
            session = FakeSession([])
            with patch("builtins.print"):
                result = C.run(args, session)
            self.assertEqual(result["status"], "budget_limit")
            self.assertEqual(len(session.runtime.calls), 0)

    def test_dry_run_has_no_aws_calls_and_respects_max_articles(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture_args(tmp); args.dry_run = True; args.max_articles = 1
            with patch("builtins.print"):
                result = C.run(args, object())
            self.assertEqual(result["coverage"]["selected_articles"], 1)
            self.assertFalse((Path(tmp) / "candidates_2026-11-05.csv").exists())

    def test_access_error_stops_without_next_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture_args(tmp)
            session = FakeSession([error("AccessDeniedException", 403)])
            with patch("builtins.print"):
                result = C.run(args, session)
            self.assertEqual(result["status"], "access_or_subscription_error")
            self.assertEqual(len(session.runtime.calls), 1)
            self.assertTrue(result["event_register_unchanged"])

    def test_invalid_text_keeps_raw_and_counts_fallback_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture_args(tmp); args.max_articles = 1
            session = FakeSession([response(text="```json\nnot JSON\n```")])
            with patch("builtins.print"):
                result = C.run(args, session)
            self.assertEqual((result["failed_checks"], result["fence_fallbacks"]), (1, 1))
            self.assertEqual(len(session.runtime.calls), 1)
            raw = list((Path(tmp) / "classifier_runs/offline/raw").glob("*.json"))[0]
            self.assertEqual(json.loads(raw.read_text())["output"]["message"]["content"][0]["text"], "```json\nnot JSON\n```")

    def test_missing_usage_halts_instead_of_spending_with_unknown_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.fixture_args(tmp)
            raw = response(relevant()); raw.pop("usage")
            session = FakeSession([raw])
            with patch("builtins.print"):
                result = C.run(args, session)
            self.assertEqual(result["status"], "cost_accounting_error")
            self.assertGreater(Decimal(result["unreported_cost_reserve_usd"]), 0)
            self.assertEqual(len(session.runtime.calls), 1)


if __name__ == "__main__":
    unittest.main()
