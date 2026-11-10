"""Offline tests for narratives (so_what / so_now_what): checks, inputs, the run with a fake Bedrock session, the review
sheet, and the dashboard export / validator gates. No AWS."""
import copy, csv, hashlib, importlib.util, json, subprocess, sys, tempfile, unittest
from decimal import Decimal
from pathlib import Path

from . import narrative_checks as NC
from . import narratives as N
from .paths import PROJECT

REPO = PROJECT.parent
WEEK = "2026-11-02"
SCORES = json.loads((N.SCORES / f"weekly_scores_v1.3_{WEEK}.json").read_text())
INPUT = {"card_id": "ECS-NSCC-LIQ", "card_name": "NSCC liquidity", "S": 5, "V": 3, "V_tier": "pqd", "severity": 15, "chain_confidence": "Medium",
         "signal": {"value": 1.5409, "percentile": 0.9672, "prior_weeks": 457,
                    "daily_values": [{"date": "2026-11-05", "value": 28015313200.6438}, {"date": "2026-11-06", "value": 1.3618}]},
         "driving_event": {"effect_date": "2026-12-31"}, "shared_signal": [{"card_id": "FICC-GSD-02", "card_name": "Repo funding and GSD liquidity"}],
         "transmission_chain": {"dtcc_process": "NSCC variation margin."}}


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class Checks(unittest.TestCase):
    def test_numbers_must_come_from_the_input(self):
        ok = ("VIX reached 1.54×, the 97th percentile of 457 prior weeks; 28.0 billion shares on Nov 5, 2026 and 1.36 on "
              "2026-11-06, shared with FICC-GSD-02 before the Dec 31, 2026 date; 97% share")
        self.assertEqual(NC.unsupported_numbers(ok, INPUT), [])
        bad = NC.unsupported_numbers("Peak 1.6× on Nov 7; 99th percentile; 31 billion; 2026-12-30; FICC-GSD-02 ok", INPUT)
        self.assertEqual(bad, ["Nov 7", "2026-12-30", "1.6×", "99th", "31 billion"])

    def test_limits_banned_and_required_mentions(self):
        long = " ".join(["word"] * 46) + "."
        flags = NC.check(long, "We recommend that DTCC acts. It will cause stress. It is guaranteed.", INPUT)
        self.assertIn("so_what: 46 words > 45", flags)
        self.assertIn("so_now_what: 3 sentences > 2", flags)
        self.assertTrue(any("recommend that dtcc" in f for f in flags) and any("'will cause'" in f for f in flags) and any("'guaranteed'" in f for f in flags))
        self.assertIn("shared signal with FICC-GSD-02 not mentioned", flags)
        proxy_low = {**INPUT, "V_tier": "public_proxy", "chain_confidence": "Low", "shared_signal": []}
        self.assertEqual(set(NC.check("VIX at 1.54×.", "Watch the daily ratio.", proxy_low)),
                         {"public-proxy V not mentioned", "Low chain confidence not mentioned"})
        self.assertEqual(NC.check("VIX at 1.54× with V from a public proxy and low chain confidence.", "Watch the U.S. data, e.g. the daily ratio.",
                                  proxy_low), [])
        self.assertEqual(NC.check("Shared with FICC-GSD-02.", "Watch it.", INPUT, ["signal.value", "nope"]), ["facts_used names unknown fields: nope"])


class Inputs(unittest.TestCase):
    def setUp(self):
        self.t = lambda r: {"event": "E", "mechanism": "M", "dtcc_process": "P " + r["business_line"]}

    def test_cross_entity_pair_is_one_input_and_floats_are_tidy(self):
        xe = [r for r in SCORES["records"] if r["card_id"] == "XE-MEMBER"]
        inp = N.build_input(xe, SCORES["records"], self.t)
        self.assertEqual(inp["business_lines"], ["FICC", "ECS"])
        self.assertEqual(inp["transmission_chain"]["dtcc_process"], "FICC: P FICC; ECS: P ECS")    # lines differ here
        self.assertTrue(all(len(repr(d["value"]).split(".")[-1]) <= 4 for d in inp["signal"]["daily_values"]))
        liq = [r for r in SCORES["records"] if r["record_id"] == "ecs-nscc-liq"]
        inp = N.build_input(liq, SCORES["records"], self.t)
        self.assertEqual(inp["S_signal_fields"], ["sofr_effr_adjusted", "vix_jump"])
        self.assertEqual(inp["shared_signal"][0]["card_id"], "FICC-GSD-02")


class FakeRuntime:
    def __init__(self, answers):
        self.answers, self.requests = answers, []

    def converse(self, **request):
        self.requests.append(request)
        card = json.loads(request["messages"][0]["content"][0]["text"].split("Input:", 1)[1])["card_id"]
        return {"stopReason": "tool_use", "usage": {"inputTokens": 900, "outputTokens": 200, "cacheReadInputTokens": 1300, "cacheWriteInputTokens": 0},
                "output": {"message": {"content": [{"toolUse": {"name": N.TOOL, "input": self.answers(card)}}]}}}


class FakeSession:
    def __init__(self, runtime):
        self.runtime = runtime

    def client(self, name, **kw):
        if name == "sts":
            return type("S", (), {"get_caller_identity": lambda self: {"Account": "888840134592"}})()
        return self.runtime


def answer(card):
    if card == "ECS-NSCC-LIQ":
        return {"so_what": "VIX ÷ 20-day average reached 1.54, the 97th percentile.", "so_now_what": "Watch it.", "facts_used": ["signal.value"], "caveats": []}
    return {"so_what": "The signal touches the DTCC process.", "so_now_what": "Watch the next disclosure.", "facts_used": ["V"], "caveats": ["test"]}


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.out = Path(self.tmp.name)
        self.t = lambda r: {"event": "E", "mechanism": "M", "dtcc_process": "P"}

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, res):
        with (self.out / Path(res["review_sheet"]).name).open() as f:
            return {r["record_id"]: r for r in csv.DictReader(f)}

    def test_one_call_per_scored_card_templates_and_flags(self):
        rt = FakeRuntime(answer)
        res = N.run(WEEK, Decimal("0.50"), session=FakeSession(rt), run_id="t1", out=self.out, transmission=self.t)
        scored_cards = {r["card_id"] for r in SCORES["records"] if r["status"] == "scored"}
        self.assertEqual((res["status"], len(rt.requests), res["cards_called"]), ("complete", len(scored_cards), len(scored_cards)))
        req = rt.requests[0]
        self.assertEqual((req["inferenceConfig"]["temperature"], req["system"][1], req["toolConfig"]["toolChoice"]),
                         (0, {"cachePoint": {"type": "default"}}, {"tool": {"name": N.TOOL}}))
        rows = self.rows(res)
        self.assertEqual(len(rows), len(SCORES["records"]))
        self.assertEqual(rows["xe-member-ficc"]["so_what"], rows["xe-member-ecs"]["so_what"])          # one call, reused
        tpl = [r for r in rows.values() if r["status"] != "scored"]
        self.assertTrue(tpl and all((r["generated_by"], r["so_what"], r["so_now_what"], r["model"]) ==
                                    ("template", NC.TEMPLATE_SO_WHAT, NC.TEMPLATE_SO_NOW_WHAT, "") for r in tpl))
        self.assertIn("shared signal with FICC-GSD-02 not mentioned", json.loads(rows["ecs-nscc-liq"]["check_flags"]))
        self.assertTrue(all(r[k] == "" for r in rows.values() for k in ("decision", "reviewer", "corrected_so_what", "corrected_so_now_what")))
        res2 = N.run(WEEK, Decimal("0.50"), session=FakeSession(FakeRuntime(answer)), run_id="t2", out=self.out, transmission=self.t)
        self.assertTrue(res2["review_sheet"].endswith(f"review_narratives_{WEEK}_t2.csv"))                # never overwritten

    def test_cap_stops_before_a_call_that_could_exceed_it(self):
        rt = FakeRuntime(answer)
        res = N.run(WEEK, Decimal("0.001"), session=FakeSession(rt), run_id="t3", out=self.out, transmission=self.t)
        self.assertEqual((res["status"], len(rt.requests)), ("budget_limit", 0))
        self.assertTrue(all("not generated" in r["check_flags"] for r in self.rows(res).values() if r["status"] == "scored"))

    def test_invalid_output_is_flagged_not_published(self):
        rt = FakeRuntime(lambda card: {"so_what": "x", "facts_used": [], "caveats": []})              # so_now_what missing
        res = N.run(WEEK, Decimal("0.50"), session=FakeSession(rt), run_id="t4", out=self.out, transmission=self.t)
        self.assertTrue(all("invalid output" in r["check_flags"] for r in self.rows(res).values() if r["status"] == "scored"))

    def test_dry_run_makes_no_call(self):
        res = N.run(WEEK, Decimal("0.50"), dry_run=True, session=FakeSession(None), run_id="t5", out=self.out, transmission=self.t)
        self.assertEqual(res["status"], "dry_run")
        self.assertFalse((self.out / f"review_narratives_{WEEK}.csv").exists())


class ExportGate(unittest.TestCase):
    """docs/data/export_risk_output.py publishes only approved narratives that pass the checks again."""
    def setUp(self):
        self.ex = module(REPO / "docs/data/export_risk_output.py", "export_risk_output")
        self.tmp = tempfile.TemporaryDirectory(dir=PROJECT / "data"); root = Path(self.tmp.name)
        self.inp = {**INPUT, "shared_signal": []}
        (root / "inputs.jsonl").write_text(json.dumps({"card_id": "ECS-NSCC-LIQ", "record_ids": ["ecs-nscc-liq"], "input": self.inp}) + "\n")
        self.base = {"record_id": "ecs-nscc-liq", "generated_by": "ai", "so_what": "VIX reached 1.54, the 97th percentile of 457 weeks.",
                     "so_now_what": "Watch the daily ratio.", "input_file": str((root / "inputs.jsonl").relative_to(PROJECT)),
                     "input_sha256": hashlib.sha256(json.dumps(self.inp, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                     "decision": "", "reviewer": "", "corrected_so_what": "", "corrected_so_now_what": "", "prompt_version": "p", "model": "m"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_gate(self):
        f = lambda **kw: self.ex.narrative_fields("ecs-nscc-liq", {**self.base, **kw})
        self.assertEqual(f()["analysis_status"], "pending_review")                                    # no decision
        self.assertEqual(f(decision="approve")["analysis_status"], "pending_review")                  # no reviewer
        self.assertEqual(f(decision="reject", reviewer="Wenqi Cai")["analysis_status"], "pending_review")
        ok = f(decision="approve", reviewer="Wenqi Cai")
        self.assertEqual((ok["analysis_status"], ok["ai_generated_fields"], ok["narrative_review_label"], ok["so_what"]),
                         ("ai_reviewed", ["so_what", "so_now_what"], "AI-written, reviewed by analyst", self.base["so_what"]))
        ed = f(decision="edit", reviewer="Wenqi Cai", corrected_so_now_what="Watch the 2026-12-31 date.")
        self.assertEqual((ed["analysis_status"], ed["so_now_what"]), ("ai_reviewed", "Watch the 2026-12-31 date."))
        self.assertEqual(f(decision="edit", reviewer="Wenqi Cai", corrected_so_what="It must rise to 2.5×.")["analysis_status"], "pending_review")
        self.assertEqual(f(decision="approve", reviewer="Wenqi Cai", input_sha256="0" * 64)["analysis_status"], "pending_review")
        tpl = self.ex.narrative_fields("ecs-set-01", {"generated_by": "template"})
        self.assertEqual((tpl["analysis_status"], tpl["so_what"], "ai_generated_fields" in tpl), ("template", NC.TEMPLATE_SO_WHAT, False))
        self.assertEqual(self.ex.narrative_fields("x", None)["analysis_status"], "pending_review")


class ValidatorGate(unittest.TestCase):
    def run_validator(self, items):
        data = json.loads((REPO / "docs/data/risk_output.json").read_text())
        data["items"] = items
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
        return subprocess.run([sys.executable, str(REPO / "docs/data/validate_output.py"), f.name], capture_output=True, text=True)

    def test_unreviewed_text_and_bad_labels_rejected(self):
        data = json.loads((REPO / "docs/data/risk_output.json").read_text())
        it = copy.deepcopy(next(i for i in data["items"] if i["id"] == "ecs-nscc-liq" and i["snapshot"] == WEEK))
        good = {**it, "analysis_status": "ai_reviewed", "so_what": "VIX reached 1.54.", "so_now_what": "Watch the ratio.",
                "ai_generated_fields": ["so_what", "so_now_what"], "narrative_review_label": "AI-written, reviewed by analyst"}
        self.assertEqual(self.run_validator([good]).returncode, 0)
        for bad in ({**good, "analysis_status": "pending_review"}, {**good, "narrative_review_label": "AI-WRITTEN"},
                    {**good, "so_what": "It must rise."}, {**good, "analysis_status": "template", "so_what": "Other text."},
                    {**good, "analysis_status": "draft"}):
            self.assertEqual(self.run_validator([bad]).returncode, 1, bad["analysis_status"])


if __name__ == "__main__":
    unittest.main()
