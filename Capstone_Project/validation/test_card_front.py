"""Offline tests for the card front layer: playbook and front checks, the drafting runs with a fake Bedrock session,
recheck, the dashboard export gate and the validator. No AWS."""
import copy, csv, hashlib, json, subprocess, sys, tempfile, unittest
from decimal import Decimal
from pathlib import Path

from . import card_front as CF
from . import card_front_checks as F
from .paths import PROJECT
from .test_narratives import FakeSession, module

REPO = PROJECT.parent
WEEK = "2026-11-02"
SCORES = json.loads((CF.N.SCORES / f"weekly_scores_v1.3_{WEEK}.json").read_text())
PB = {"card_id": "ECS-NSCC-LIQ", "chain_short_1": "Prices swing", "chain_short_2": "Daily margin payments jump",
      "chain_short_3": "NSCC clearing fund calls", "action_1_id": "ECS-NSCC-LIQ.a1", "action_1_kind": "communicate",
      "action_1_text": "Alert relationship teams that members may face larger margin calls.", "action_2_id": "ECS-NSCC-LIQ.a2",
      "action_2_kind": "prepare", "action_2_text": "Confirm with treasury operations that liquidity coverage is ready.",
      "action_3_id": "", "action_3_kind": "", "action_3_text": ""}
ACTIONS = {"ECS-NSCC-LIQ.a1": PB["action_1_text"], "ECS-NSCC-LIQ.a2": PB["action_2_text"]}
INPUT = {"card_id": "ECS-NSCC-LIQ", "S": 5, "V": 3, "transmission_chain": {"mechanism": "Daily mark-to-market payments change sharply.",
                                                                           "dtcc_process": "NSCC variation margin."},
         "signal": {"plain_name": "VIX relative to its 20-day average (ratio)", "scope": "market-wide", "value": 1.5409, "percentile": 0.9672,
                    "daily_values": [{"date": "2026-11-05", "value": 1.5409}]},
         "S_set_by": "VIX relative to its 20-day average (ratio)", "driving_event": None,
         "related_news": {"top_items": [{"title": "Tech stocks log worst day since 2020 as carnage comes to the AI trade", "outlet": "MarketWatch"}]},
         "playbook": {"chain_short": ["Prices swing", "Daily margin payments jump", "NSCC clearing fund calls"],
                      "actions": [{"action_id": k, "text": v} for k, v in ACTIONS.items()]}}
FRONT = {"headline": "Tech stocks log worst day: larger margin payments", "headline_source": "related_news:0",
         "what_happened": "VIX rose to 1.54 times its 20-day average on Nov 5.",
         "so_what_front": "Larger daily price moves can raise the cash members pay to NSCC in variation margin.",
         "action_id": "ECS-NSCC-LIQ.a1", "so_now_what_front": ACTIONS["ECS-NSCC-LIQ.a1"]}


class PlaybookChecks(unittest.TestCase):
    def test_good_row_passes(self):
        self.assertEqual(F.playbook_flags(PB, {"a1": "communicate", "a2": "prepare"}), [])

    def test_rules(self):
        flags = lambda **kw: F.playbook_flags({**PB, **kw})
        self.assertIn("chain_short_1: 7 words > 6", flags(chain_short_1="Sharp equity selloff or large price swings"))
        self.assertTrue(any("does not start with a verb" in f for f in flags(action_1_text="Relationship teams get an alert.")))
        self.assertTrue(any("risk-parameter or policy" in f for f in flags(action_1_text="Raise margin requirements for affected members.")))
        self.assertTrue(any("policy" in f for f in flags(action_1_text="Ask risk to tighten haircuts on collateral.")))
        self.assertTrue(any("legal or regulatory" in f for f in flags(action_1_text="Ask counsel to seek regulatory relief from the SEC.")))
        self.assertTrue(any("possible firm or proper name: Goldman" in f for f in flags(action_1_text="Alert coverage of Goldman Sachs now.")))
        self.assertTrue(any("contains a number" in f for f in flags(action_1_text="Check liquidity within 2 hours.")))
        self.assertTrue(any("15" in f for f in flags(action_1_text="Alert " + "the " * 15 + "teams.")))
        self.assertIn("1 actions (2-3 expected)", flags(action_2_text=""))
        self.assertIn("all actions of one kind", F.playbook_flags(PB, {"a1": "monitor", "a2": "monitor"}))
        self.assertEqual(F.action_flags("Alert FICC and ECS operations teams; check the Agent Clearing Member list."), [])


class FrontChecks(unittest.TestCase):
    def test_good_front_passes(self):
        self.assertEqual(F.publication_flags(FRONT, INPUT, ACTIONS), [])
        self.assertEqual(F.drafting_flags(FRONT, INPUT), [])

    def test_publication_rules(self):
        flags = lambda **kw: F.publication_flags({**FRONT, **kw}, INPUT, ACTIONS)
        self.assertIn("headline: 11 words > 10", flags(headline=" ".join(["word"] * 11)))
        self.assertIn("so_what_front: 2 sentences > 1", flags(so_what_front="Margin may rise. Cash may move."))
        self.assertTrue(any("numbers not in the input: 2.1" in f for f in flags(what_happened="VIX rose to 2.1 times its average.")))
        self.assertTrue(any("jargon" in f and "percentile" in f for f in flags(so_what_front="VIX at the 97th percentile may raise margin.")))
        self.assertTrue(any("V 3" in f for f in flags(so_what_front="With V 3 of 5 NSCC margin may rise.")))
        self.assertEqual(flags(what_happened="The spread rose to 1.54 bp on Nov 5."), [])          # units allowed in what_happened
        self.assertTrue(any("score terms: 97th" in f for f in flags(what_happened="VIX hit its 97th percentile on Nov 5.")))
        self.assertTrue(any("banned phrase 'must'" in f for f in flags(so_what_front="Members must pay more cash to NSCC.")))
        self.assertTrue(any("specific firms" in f for f in flags(so_what_front="Weaker members may struggle with NSCC margin calls.")))
        self.assertIn("action_id 'X.a9' is not a playbook action of this card", flags(action_id="X.a9"))
        self.assertIn("so_now_what_front is not the playbook action text, word for word", flags(so_now_what_front="Alert relationship teams."))

    def test_drafting_hints(self):
        d = lambda **kw: F.drafting_flags({**FRONT, **kw}, INPUT)
        self.assertTrue(any("not the signal" in f for f in d(headline_source="related_news:7")))
        self.assertTrue(any("possible new event" in f and "tarif" in f for f in d(headline="Tariff shock: larger margin payments")))
        self.assertIn("so_what_front does not follow chain steps 2/3", d(so_what_front="Investors may feel uneasy about the outlook."))
        self.assertTrue(any("weaker than this week's signal" in f for f in d(so_what_front="A modest move; NSCC variation margin may change.")))
        low = {**INPUT, "S": 2}
        self.assertTrue(any("stronger than" in f for f in F.drafting_flags({**FRONT, "headline": "Tech stocks surge: margin jumps"}, low)))
        self.assertTrue(any("superlative" in f for f in d(what_happened="Tech stocks logged their worst day since 2020 on Nov 5.")))
        self.assertTrue(any("restates related-news headline 0" in f for f in d(what_happened="Tech stocks log worst day since 2020 as carnage hits.")))
        self.assertTrue(any("prediction ('likely')" in f for f in d(headline="Tech stocks log worst day: margin calls likely")))

    def test_sources_line(self):
        r = next(x for x in SCORES["records"] if x["record_id"] == "ecs-nscc-liq")
        ex = CF.N.export_module()
        self.assertEqual(F.sources_line(r, ex.SIGNAL_SERIES, "MarketWatch"), "FRED (VIX, SOFR, EFFR) · DTCC quarterly disclosures · MarketWatch")
        g3 = next(x for x in SCORES["records"] if x["record_id"] == "ficc-gsd-03")
        self.assertEqual(F.sources_line(g3, ex.SIGNAL_SERIES), "Federal Register (SEC) · DTCC quarterly disclosures")


class FakeRuntime:
    def __init__(self, bad_front=False):
        self.requests, self.bad_front = [], bad_front

    def converse(self, **req):
        self.requests.append(req)
        tool = req["toolConfig"]["toolChoice"]["tool"]["name"]
        if tool == CF.PLAYBOOK_TOOL:
            v = {k: PB[k] for k in CF.PLAYBOOK_SCHEMA["required"]}
        else:
            inp = json.loads(req["messages"][0]["content"][0]["text"].split("Input:", 1)[1])
            a = inp["playbook"]["actions"][0]
            v = {"headline": "Signal moves: margin may change", "headline_source": "signal", "what_happened": "The signal moved this week.",
                 "so_what_front": "Daily margin payments may change.", "action_id": a["action_id"],
                 "so_now_what_front": a["text"] if not self.bad_front else "Do something else.", "action_reason": "test"}
        return {"stopReason": "tool_use", "usage": {"inputTokens": 900, "outputTokens": 200, "cacheReadInputTokens": 1300, "cacheWriteInputTokens": 0},
                "output": {"message": {"content": [{"toolUse": {"name": tool, "input": v}}]}}}


class Runs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, rel):
        with (self.out / Path(rel).name).open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_playbook_then_front(self):
        rt = FakeRuntime()
        res = CF.run_playbook(Decimal("0.50"), session=FakeSession(rt), out=self.out, run_id="p1")
        self.assertEqual((res["status"], len(rt.requests), res["cards"]), ("complete", 16, 16))
        req = rt.requests[0]
        self.assertEqual((req["inferenceConfig"]["temperature"], req["system"][1], req["toolConfig"]["toolChoice"]),
                         (0, {"cachePoint": {"type": "default"}}, {"tool": {"name": CF.PLAYBOOK_TOOL}}))
        rows = self.read(res["playbook_sheet"])
        self.assertEqual(len(rows), 16)
        xe = next(r for r in rows if r["card_id"] == "XE-MEMBER")
        self.assertEqual((xe["action_1_id"], xe["action_2_id"], xe["action_3_id"], xe["business_lines"]), ("XE-MEMBER.a1", "XE-MEMBER.a2", "", "FICC|ECS"))
        self.assertTrue(all(r[k] == "" for r in rows for k in ("decision", "reviewer", "corrected_chain_short_1", "corrected_action_1_text")))
        again = CF.run_playbook(Decimal("0.50"), session=FakeSession(FakeRuntime()), out=self.out, run_id="p2")
        self.assertTrue(again["playbook_sheet"].endswith("card_playbook_p2.csv"))                 # never overwritten

        rt = FakeRuntime()
        res = CF.run_front(WEEK, Decimal("0.50"), session=FakeSession(rt), out=self.out, run_id="f1", playbook_path=self.out / "card_playbook.csv")
        scored = [r for r in SCORES["records"] if r["status"] == "scored"]
        self.assertEqual((res["status"], len(rt.requests)), ("complete", len({r["card_id"] for r in scored})))   # XE pair: one call
        rows = self.read(res["review_sheet"])
        self.assertEqual([r["record_id"] for r in rows], [r["record_id"] for r in scored])            # scored records only
        pair = [r for r in rows if r["card_id"] == "XE-MEMBER"]
        self.assertEqual(pair[0]["headline"], pair[1]["headline"])
        self.assertTrue(all(json.loads(r["check_flags"]) == [] and r["so_now_what_front"] == PB["action_1_text"] for r in rows))
        inp = F.NC.load_input(Path(rows[0]["input_file"]), rows[0]["record_id"])          # a temp folder: absolute path
        self.assertIn("playbook", inp); self.assertIn("watch_sources", inp)                            # v3.1 input plus the playbook
        self.assertTrue(all(r["sources_line"] for r in rows))

    def test_front_flags_and_cap(self):
        CF.run_playbook(Decimal("0.50"), session=FakeSession(FakeRuntime()), out=self.out, run_id="p1")
        res = CF.run_front(WEEK, Decimal("0.50"), session=FakeSession(FakeRuntime(bad_front=True)), out=self.out, run_id="f2",
                           playbook_path=self.out / "card_playbook.csv")
        self.assertTrue(all("not the playbook action text" in r["check_flags"] for r in self.read(res["review_sheet"])))
        rt = FakeRuntime()
        res = CF.run_front(WEEK, Decimal("0.001"), session=FakeSession(rt), out=self.out, run_id="f3", playbook_path=self.out / "card_playbook.csv",
                           sheet_path=self.out / "capped.csv")
        self.assertEqual((res["status"], len(rt.requests)), ("budget_limit", 0))
        self.assertTrue(all("not generated" in r["check_flags"] for r in self.read("capped.csv")))
        self.assertEqual(CF.run_front(WEEK, Decimal("0.5"), dry_run=True, session=FakeSession(None), out=self.out, run_id="f4",
                                      playbook_path=self.out / "card_playbook.csv")["status"], "dry_run")


class Committed(unittest.TestCase):
    def test_committed_sheets_recheck_without_changes(self):
        """The committed playbook and front sheet carry the flags of the current checks, and their stored inputs match."""
        with tempfile.TemporaryDirectory() as d:
            pb, fr = Path(d) / "pb.csv", Path(d) / "fr.csv"
            pb.write_bytes((CF.PLAYBOOK).read_bytes()); fr.write_bytes((CF.OUT / f"review_front_{WEEK}.csv").read_bytes())
            CF.recheck(pb, fr)
            self.assertEqual(pb.read_bytes(), CF.PLAYBOOK.read_bytes())
            self.assertEqual(fr.read_bytes(), (CF.OUT / f"review_front_{WEEK}.csv").read_bytes())
        with (CF.OUT / f"review_front_{WEEK}.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len({r["card_id"] for r in rows}), 7)
        with (CF.PLAYBOOK).open(encoding="utf-8") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 16)


class ExportGate(unittest.TestCase):
    def setUp(self):
        self.ex = module(REPO / "docs/data/export_risk_output.py", "export_risk_output")
        self.tmp = tempfile.TemporaryDirectory(dir=PROJECT / "data"); root = Path(self.tmp.name)
        (root / "inputs.jsonl").write_text(json.dumps({"card_id": "ECS-NSCC-LIQ", "record_ids": ["ecs-nscc-liq"], "input": INPUT}) + "\n")
        self.rec = next(x for x in SCORES["records"] if x["record_id"] == "ecs-nscc-liq")
        self.row = {"record_id": "ecs-nscc-liq", **FRONT, "input_file": str((root / "inputs.jsonl").relative_to(PROJECT)),
                    "input_sha256": hashlib.sha256(json.dumps(INPUT, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    "decision": "", "reviewer": "", "corrected_headline": "", "corrected_what_happened": "", "corrected_so_what_front": "",
                    "corrected_action_id": "", "prompt_version": "p", "model": "m"}
        self.pb = F.effective_playbook({**PB, "decision": "approve", "reviewer": "Wenqi Cai"})

    def tearDown(self):
        self.tmp.cleanup()

    def f(self, playbook=None, **kw):
        pb = {"ECS-NSCC-LIQ": self.pb} if playbook is None else playbook
        return self.ex.front_fields(self.rec, {"ecs-nscc-liq": {**self.row, **kw}}, pb)

    def test_gate(self):
        self.assertIsNotNone(self.pb)
        self.assertEqual(self.f()["front_status"], "pending_review")                                   # no decision
        self.assertEqual(self.f(decision="approve")["front_status"], "pending_review")                 # no reviewer
        self.assertEqual(self.f(decision="reject", reviewer="W")["front_status"], "pending_review")
        ok = self.f(decision="approve", reviewer="W")
        self.assertEqual((ok["front_status"], ok["front_headline"], ok["front_so_now_what"], ok["front_review_label"], ok["front_chain_short"]),
                         ("ai_reviewed", FRONT["headline"], PB["action_1_text"], "AI-drafted · analyst-reviewed", self.pb["chain_short"]))
        self.assertTrue(ok["front_sources_line"].endswith("MarketWatch"))
        ed = self.f(decision="edit", reviewer="W", corrected_action_id="ECS-NSCC-LIQ.a2", corrected_headline="Tech stocks log worst day: margin may rise")
        self.assertEqual((ed["front_so_now_what"], ed["front_headline"]), (PB["action_2_text"], "Tech stocks log worst day: margin may rise"))
        edited_pb = F.effective_playbook({**PB, "decision": "edit", "reviewer": "W", "corrected_action_1_text": "Alert relationship teams early."})
        self.assertEqual(self.f(playbook={"ECS-NSCC-LIQ": edited_pb}, decision="approve", reviewer="W")["front_so_now_what"], "Alert relationship teams early.")
        self.assertEqual(self.f(playbook={}, decision="approve", reviewer="W")["front_status"], "pending_review")          # playbook unreviewed
        self.assertEqual(self.f(decision="edit", reviewer="W", corrected_so_what_front="It must rise.")["front_status"], "pending_review")
        self.assertEqual(self.f(decision="approve", reviewer="W", input_sha256="0" * 64)["front_status"], "pending_review")
        self.assertIsNone(F.effective_playbook({**PB, "decision": "approve", "reviewer": "W", "chain_short_1": "one two three four five six seven"}))
        unscored = next(x for x in SCORES["records"] if x["record_id"] == "xe-cyber-ecs")
        t = self.ex.front_fields(unscored, {}, {})
        self.assertEqual((t["front_status"], t["front_headline"], t["front_what_happened"], t["front_so_what"], t["front_ai_fields"]),
                         ("template", unscored["title"], "No market signal or relevant news this week.", None, []))
        self.assertEqual(self.ex.front_fields(self.rec, None, {})["front_status"], "none")

    def test_published_file_is_the_export_of_the_reviewed_sheets(self):
        """docs/data/risk_output.json is exactly what the export builds from the committed (reviewed) sheets."""
        data = json.loads(json.dumps(self.ex.build(self.ex.WEEKS), ensure_ascii=False))
        self.assertEqual(data, json.loads((REPO / "docs/data/risk_output.json").read_text()))
        week = [i for i in data["items"] if i["snapshot"] == WEEK]
        self.assertEqual({i["front_status"] for i in week if i["status"] == "scored"}, {"ai_reviewed"})
        self.assertEqual({i["front_status"] for i in week if i["status"] != "scored"}, {"template"})
        self.assertEqual({i["front_status"] for i in data["items"] if i["snapshot"] != WEEK}, {"none"})


class CheckFixes(unittest.TestCase):
    """Hyphenated words and attributed news in what_happened (review of 2026-11-02)."""
    def test_hyphens_ignored_when_words_are_compared(self):
        inp = {**INPUT, "related_news": {"top_items": [{"title": "Tech-led equity selloff deepens", "outlet": "MarketWatch"}]}}
        flags = F.drafting_flags({**FRONT, "headline": "Equity sell-off: NSCC margin calls may rise", "headline_source": "related_news:0"}, inp)
        self.assertFalse(any("possible new event" in f or "shares no words" in f for f in flags), flags)
        self.assertEqual(F._stems("sell-off mark-to-market"), F._stems("selloff marktomarket"))

    def test_attributed_superlative_and_headline_accepted(self):
        attributed = "MarketWatch reported tech stocks' worst day since 2020; the VIX jumped to 1.54 times its 20-day average."
        self.assertEqual(F.drafting_flags({**FRONT, "what_happened": attributed}, INPUT), [])
        bare = "Tech stocks logged their worst day since 2020 as a sharp selloff hit markets."
        flags = F.drafting_flags({**FRONT, "what_happened": bare}, INPUT)
        self.assertTrue(any("superlative ('worst')" in f for f in flags) and any("restates related-news headline 0" in f for f in flags))
        wrong_outlet = "CNBC reported tech stocks log worst day since 2020."                     # outlet of another headline
        self.assertTrue(any("superlative" in f for f in F.drafting_flags({**FRONT, "what_happened": wrong_outlet}, INPUT)))
        self.assertTrue(any("superlative" in f for f in F.drafting_flags({**FRONT, "so_what_front": "MarketWatch: worst NSCC margin day."}, INPUT)))
        self.assertTrue(F._names_outlet("Bloomberg reported it", "Bloomberg.com") and not F._names_outlet("Bloomberg", ""))


class ReviewerColumns(unittest.TestCase):
    def test_corrected_kind_and_text(self):
        row = {**PB, "decision": "edit", "reviewer": "W", "corrected_action_2_kind": "communicate", "corrected_chain_short_1": "Prices move"}
        self.assertEqual(F.action_kinds(row), {"ECS-NSCC-LIQ.a1": "communicate", "ECS-NSCC-LIQ.a2": "communicate"})
        eff = F.effective_row(row)
        self.assertEqual((eff["chain_short_1"], eff["action_2_kind"]), ("Prices move", "communicate"))
        self.assertIn("all actions of one kind", F.playbook_flags(eff, F.action_kinds(eff)))
        self.assertEqual(F.effective_row({**row, "decision": "approve"})["chain_short_1"], PB["chain_short_1"])   # approve ignores corrections

    def test_corrected_headline_source_drives_the_sources_line(self):
        g = ExportGate(); g.setUp()
        try:
            news = g.f(decision="approve", reviewer="W")
            sig = g.f(decision="edit", reviewer="W", corrected_headline_source="signal")
            self.assertTrue(news["front_sources_line"].endswith("MarketWatch"))
            self.assertEqual(sig["front_sources_line"], "FRED (VIX, SOFR, EFFR) · DTCC quarterly disclosures")
        finally:
            g.tearDown()


class CheckReviewed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        self.pb, self.fr = d / "pb.csv", d / "fr.csv"
        self.pb.write_bytes(CF.PLAYBOOK.read_bytes()); self.fr.write_bytes((CF.OUT / f"review_front_{WEEK}.csv").read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, path, key, value, **cols):
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if value in (r.get("record_id"), r.get("card_id")) and (key == "card_id" or r.get("record_id") == value):
                r.update(cols)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows)

    def test_committed_review_passes_every_check(self):
        self.assertEqual(CF.check_reviewed(self.pb, self.fr), {"playbook_rows": 16, "failures": []})
        with self.assertRaises(SystemExit) as e:
            CF.main(["check-reviewed", "--playbook", str(self.pb), "--front", str(self.fr)])
        self.assertEqual(e.exception.code, 0)

    def test_failures_are_reported(self):
        self.edit(self.fr, "record_id", "ficc-gsd-01", corrected_headline="Treasury yields surge: margin must jump")
        self.edit(self.fr, "record_id", "ficc-gsd-02", decision="")
        self.edit(self.pb, "card_id", "XE-CYBER", corrected_action_1_kind="decide")
        res = CF.check_reviewed(self.pb, self.fr)
        by = {(f["sheet"], f["row"]): f["flags"] for f in res["failures"]}
        self.assertTrue(any("banned phrase 'must'" in f for f in by[("front", "ficc-gsd-01")]))
        self.assertTrue(any("stronger than this week's signal" in f for f in by[("front", "ficc-gsd-01")]))
        self.assertEqual(by[("front", "ficc-gsd-02")], ["not reviewed (decision approve/edit and reviewer)"])
        self.assertIn("unknown action kind: decide", by[("playbook", "XE-CYBER")])
        with self.assertRaises(SystemExit) as e:
            CF.main(["check-reviewed", "--playbook", str(self.pb), "--front", str(self.fr)])
        self.assertEqual(e.exception.code, 1)


class Validator(unittest.TestCase):
    def run_validator(self, items, playbook_rows=None):
        data = json.loads((REPO / "docs/data/risk_output.json").read_text())
        data["items"] = items
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.json"; path.write_text(json.dumps(data))
            args = [sys.executable, str(REPO / "docs/data/validate_output.py"), str(path)]
            if playbook_rows is not None:
                pb = Path(d) / "pb.csv"
                with pb.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(playbook_rows[0].keys())); w.writeheader(); w.writerows(playbook_rows)
                args += ["--playbook", str(pb)]
            return subprocess.run(args, capture_output=True, text=True)

    def test_front_rules(self):
        data = json.loads((REPO / "docs/data/risk_output.json").read_text())
        it = copy.deepcopy(next(i for i in data["items"] if i["id"] == "ecs-nscc-liq" and i["snapshot"] == WEEK))
        reviewed = [{**PB, "decision": "approve", "reviewer": "W"}]
        good = {**it, "front_status": "ai_reviewed", "front_headline": FRONT["headline"], "front_what_happened": FRONT["what_happened"],
                "front_so_what": FRONT["so_what_front"], "front_so_now_what": PB["action_1_text"], "front_action_id": "ECS-NSCC-LIQ.a1",
                "front_ai_fields": ["front_headline", "front_what_happened", "front_so_what", "front_so_now_what"],
                "front_review_label": "AI-drafted · analyst-reviewed", "front_chain_short": INPUT["playbook"]["chain_short"],
                "front_sources_line": "FRED (VIX)", "playbook_reviewer": "W"}
        self.assertEqual(self.run_validator([good], reviewed).returncode, 0, self.run_validator([good], reviewed).stdout)
        for bad in ({**good, "front_status": "pending_review"}, {**good, "front_review_label": "AI-WRITTEN"},
                    {**good, "front_so_what": "Members must pay more."}, {**good, "front_headline": " ".join(["w"] * 11)},
                    {**good, "front_so_what": "At the 97th percentile margin may rise."}, {**good, "front_so_now_what": "Do something else."},
                    {**good, "front_chain_short": ["a", "b", "one two three four five six seven"]}, {**good, "front_status": "draft"},
                    {**good, "front_status": "template"}):
            self.assertEqual(self.run_validator([bad], reviewed).returncode, 1, bad["front_status"])
        self.assertEqual(self.run_validator([good], [{**PB}]).returncode, 1)                       # playbook row not reviewed
        un = copy.deepcopy(next(i for i in data["items"] if i["id"] == "xe-cyber-ecs" and i["snapshot"] == WEEK))
        tpl = {**un, "front_status": "template", "front_headline": un["title"], "front_what_happened": "No market signal or relevant news this week.",
               "front_so_what": None, "front_so_now_what": None, "front_action_id": None, "front_ai_fields": [], "front_review_label": None,
               "front_chain_short": None, "front_sources_line": "NIST vulnerability database"}
        self.assertEqual(self.run_validator([tpl]).returncode, 0)
        for bad in ({**tpl, "front_headline": "Cyber attack hits"}, {**tpl, "front_so_what": "x"}, {**tpl, "front_review_label": "AI-drafted · analyst-reviewed"}):
            self.assertEqual(self.run_validator([bad]).returncode, 1)


if __name__ == "__main__":
    unittest.main()
