"""Offline tests for the flat response schema (strict mode off, validated in code). No AWS calls."""
import argparse, csv, json, tempfile, unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from jsonschema import ValidationError

from . import llm_classifier as C
from .test_llm_classifier import FakeSession
from .test_llm_prompt_v13 import headline_article

_, _, CARDS, _ = C.prompt_parts_v13(C.PROMPT_V14, "v1.4")
NULLS = {k: None for k in C.output_schema_flat(CARDS)["properties"]}


def flat_relevant(**kw):
    return {**NULLS, "is_relevant": True, "title": "Tech stocks log worst day since 2020", "summary": "Sharp equity selloff.",
            "card_ids": ["ECS-NSCC-LIQ"], "certainty": 2, "reach": 2, "reach_basis": "market_wide", "named_participants": [],
            "announced_date": "2026-11-05", "effect_date": "2026-11-05", "source_tier": "major_media", "outlet": "MarketWatch",
            "url": "https://news.google.com/rss/articles/X", "evidence_quotes": ["Tech stocks log worst day since 2020"],
            "confidence": 0.5, "notes": "headline_only", **kw}


def flat_irrelevant(**kw):
    return {**NULLS, "is_relevant": False, "notes": "explainer", **kw}


def tool_response(value, out_tokens=100):
    return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t", "name": C.TOOL, "input": value}}]}},
            "stopReason": "tool_use", "usage": {"inputTokens": 100, "outputTokens": out_tokens}, "ResponseMetadata": {"RetryAttempts": 0}}


def keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k; yield from keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys(v)


class FlatSchema(unittest.TestCase):
    def test_no_branching_or_const(self):
        schema = C.output_schema_flat(CARDS)
        self.assertFalse({"anyOf", "oneOf", "allOf", "if", "then", "else", "const"} & set(keys(schema)))
        self.assertEqual(schema["required"], list(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])

    def test_request_is_forced_tool_with_strict_off(self):
        system, user_t, cards, _ = C.prompt_parts_v13(C.PROMPT_V14, "v1.4")
        req = C.build_request_v13(system, C.render_user_v13(user_t, [], headline_article())[0], C.output_schema_flat(cards),
                                  json.loads(C.CONFIG.read_text()), cache=True, strict=False)
        spec = req["toolConfig"]["tools"][0]["toolSpec"]
        self.assertEqual((spec["strict"], req["toolConfig"]["toolChoice"]), (False, {"tool": {"name": C.TOOL}}))
        self.assertIn("set every field except notes to null", spec["description"])
        self.assertEqual(req["system"][-1], {"cachePoint": {"type": "default"}})

    def test_relevant_and_irrelevant_parse(self):
        rel, mode, _ = C.parse_response(tool_response(flat_relevant()), flat=True)
        checked = C.validate_flat(rel, CARDS)
        self.assertEqual((mode, checked["is_relevant"], checked["card_ids"]), ("tool", True, ["ECS-NSCC-LIQ"]))
        _, reasons = C.check_classification(checked, headline_article(), C.output_schema(CARDS), CARDS, set(), set(), headline_rules=True)
        self.assertFalse([r for r in reasons if "schema" in r])
        irr, _, _ = C.parse_response(tool_response(flat_irrelevant()), flat=True)
        self.assertEqual(C.validate_flat(irr, CARDS), {"is_relevant": False, "notes": "explainer"})

    def test_text_fence_fallback_still_works(self):
        resp = {"output": {"message": {"content": [{"text": "```json\n" + json.dumps(flat_irrelevant()) + "\n```"}]}}, "stopReason": "end_turn"}
        value, mode, fence = C.parse_response(resp, flat=True)
        self.assertEqual((mode, fence, C.validate_flat(value, CARDS)["is_relevant"]), ("text", True, False))

    def test_malformed_rejected(self):
        bad = [
            {"is_relevant": False, "notes": "two-field answer"},                       # fields missing
            flat_relevant(card_ids=None),                                                # relevant with null field
            flat_relevant(confidence=1.5),                                               # confidence outside 0-1
            flat_relevant(card_ids=["NOT-A-CARD"]),                                      # card not in catalog
            flat_relevant(effect_date="05/11/2026"),                                     # not an ISO date
            flat_relevant(is_relevant="yes"),                                            # wrong type
            flat_relevant(extra="x"),                                                    # unknown field
            flat_relevant(card_ids=[]),                                                  # no card
        ]
        for b in bad:
            with self.assertRaises((ValidationError, ValueError), msg=str(b)[:80]):
                C.validate_flat(b, CARDS)


class FlatRun(unittest.TestCase):
    def test_run_routes_malformed_to_failed_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news.csv"
            with news.open("w", newline="") as h:
                w = csv.DictWriter(h, fieldnames=["document_id", "title", "url", "publication_date", "published_at_utc", "summary",
                                                  "source_id", "outlet", "source_tier"])
                w.writeheader()
                for n, title in enumerate(["Tech stocks log worst day since 2020", "Stock market glossary", "Garbled item"]):
                    w.writerow({"document_id": f"g{n}", "title": title, "url": "https://news.google.com/rss/articles/X" if n == 0 else f"https://n/{n}",
                                "published_at_utc": f"2026-11-05T2{n}:00:00+00:00", "source_id": "google_news_rss",
                                "outlet": "MarketWatch", "source_tier": "major_media"})
            register = root / "register.csv"
            register.write_text("event_id,title,card_ids,announced_date,effect_date\nEV1,old,FICC-GSD-03,2025-01-01,2026-12-31\n")
            major = root / "major.csv"; major.write_text("name\n")
            session = FakeSession([tool_response(flat_relevant(), 400), tool_response(flat_irrelevant()),
                                   tool_response({"is_relevant": True, "notes": "missing everything"})])
            args = argparse.Namespace(config=C.CONFIG, register=register, news=news, major=major, start=date(2026, 11, 2), end=date(2026, 11, 8),
                                      max_articles=None, budget=Decimal("0.5"), dry_run=False, run_date=date(2026, 11, 8), run_id="flat",
                                      output_dir=root, prompt_version="v1.4", prompt_cache="on", response_schema="flat")
            s = C.run(args, session=session)
            # failed_checks counts the malformed answer and the flagged relevant candidate (validate() caps certainty:
            # one major_media outlet is not a primary source); the flagged candidate stays in the candidate CSV.
            self.assertEqual((s["status"], s["relevant"], s["irrelevant"], s["failed_checks"]), ("complete", 1, 1, 2))
            self.assertEqual((s["response_schema"], s["tool_strict"]), ("flat", False))
            self.assertEqual(len(session.runtime.calls), 3)                                   # no retry of the malformed answer
            self.assertTrue(all(c["toolConfig"]["tools"][0]["toolSpec"]["strict"] is False for c in session.runtime.calls))
            with (root / "candidates_2026-11-08.csv").open() as h:
                rows = list(csv.DictReader(h))
            self.assertEqual((len(rows), rows[0]["card_ids"], rows[0]["response_mode"]), (1, "ECS-NSCC-LIQ", "tool"))
            failed = [json.loads(l) for l in (root / "classifier_runs/flat/failed.jsonl").read_text().splitlines()]
            self.assertTrue(any(f["document_id"] == "g2" and "parse_or_schema_error" in f["reasons"][0] for f in failed))
            self.assertTrue(any(f["document_id"] == "g0" and any("certainty capped at 1" in r for r in f["reasons"]) for f in failed))
            self.assertEqual(rows[0]["certainty"], "1")
            irr = json.loads((root / "classifier_runs/flat/irrelevant.jsonl").read_text().splitlines()[0])
            self.assertEqual(irr["response_mode"], "tool")

    def test_cli_default_is_flat_and_v12(self):
        a = C.parser().parse_args(["--start", "2026-11-01", "--end", "2026-11-08"])
        self.assertEqual((a.response_schema, a.prompt_version), ("flat", "v1.2"))


if __name__ == "__main__":
    unittest.main()
