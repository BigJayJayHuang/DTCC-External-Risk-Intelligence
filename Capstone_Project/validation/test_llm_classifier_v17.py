"""Prompt v1.7 (forward_topic / forward_lean / forward_quote for prediction markets). Offline; no AWS calls."""
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from . import llm_classifier as C
from .test_llm_classifier import article, relevant


def flat_v17(**over):
    r = {**relevant(), "event_type": "regulatory", "geography": "us", "new_information": None,
         "forward_topic": "none", "forward_lean": None, "forward_quote": None}
    r.update(over)
    return r


class V17Tests(unittest.TestCase):
    def setUp(self):
        self.system, self.user, self.cards, self.version = C.prompt_parts_v13(C.PROMPT_V17, "v1.7")

    def test_prompt_loads_and_defines_forward_fields(self):
        self.assertTrue(self.version.startswith("classifier-prompt-v1.7:"))
        for k in ("forward_topic", "forward_lean", "forward_quote", "fed_cut", "government_shutdown", "debt_limit_breach"):
            self.assertIn(k, self.system)
        v16_system, v16_user, _, _ = C.prompt_parts_v13(C.PROMPT_V16, "v1.6")
        self.assertEqual(self.user, v16_user)                               # per-item user message unchanged
        self.assertIn(v16_system.split("## Output")[0][:2000], self.system)  # v1.6 rules kept

    def test_flags(self):
        self.assertIn("v1.7", C.MARKET_PROMPTS)
        self.assertNotIn("v1.6", C.MARKET_PROMPTS)                           # v1.6 runs are unchanged
        for s in (C.SPLIT_PROMPTS, C.EVENT_TYPE_PROMPTS, C.GEO_PROMPTS):
            self.assertIn("v1.7", s)

    def test_schemas_include_forward_fields_only_for_market_prompts(self):
        self.assertNotIn("forward_topic", C.output_schema_flat(self.cards, True, True)["properties"])
        flat = C.output_schema_flat(self.cards, True, True, True)
        Draft202012Validator.check_schema(flat)
        self.assertEqual(flat["properties"]["forward_topic"]["enum"][:-1], C.FORWARD_TOPICS)
        strict = C.output_schema(self.cards, True, True, True)
        Draft202012Validator(strict, format_checker=FormatChecker()).validate({"classification": flat_v17()})

    def test_prepare_flat_normalizes_forward_fields(self):
        r = flat_v17(); [r.pop(k) for k in ("forward_topic", "forward_lean", "forward_quote")]
        out, filled = C.prepare_flat(r, self.cards, True, True, True)        # older-style answer without the fields
        self.assertEqual((out["forward_topic"], out["forward_lean"], out["forward_quote"]), ("none", None, None))
        out, _ = C.prepare_flat(flat_v17(forward_topic="fed_cut"), self.cards, True, True, True)
        self.assertEqual(out["forward_lean"], "neutral")
        out, _ = C.prepare_flat(flat_v17(forward_topic="fed_cut", forward_lean="neutral", forward_quote="x"), self.cards, True, True, True)
        self.assertIsNone(out["forward_quote"])

    def test_lean_without_verbatim_quote_is_downgraded(self):
        schema = C.output_schema(self.cards, True, True, True)
        a = article(); a["text"] = "Traders pile into bets on a December Fed cut. The SEC extended the deadline."
        good = flat_v17(forward_topic="fed_cut", forward_lean="yes", forward_quote="bets on a December Fed cut")
        checked, reasons = C.check_classification(good, a, schema, self.cards, set(), set())
        self.assertEqual(checked["forward_lean"], "yes")
        self.assertFalse([x for x in reasons if "forward_quote" in x])
        bad = flat_v17(forward_topic="fed_cut", forward_lean="yes", forward_quote="Fed will surely cut")
        checked, reasons = C.check_classification(bad, a, schema, self.cards, set(), set())
        self.assertEqual(checked["forward_lean"], "neutral")
        self.assertTrue([x for x in reasons if "forward_quote" in x])

    def test_csv_has_forward_columns(self):
        for k in ("forward_topic", "forward_lean", "forward_quote"):
            self.assertIn(k, C.CSV_FIELDS)


if __name__ == "__main__":
    unittest.main()
