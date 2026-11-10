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
        listed = {**INPUT, "related_news": {"top_titles": []}, "S_signals": [{"plain_name": "VIX", "percentile": 0.97}]}
        self.assertEqual(NC.check("Shared with FICC-GSD-02.", "Watch it.", listed,
                                  ["related_news.top_titles", "S_signals[0].plain_name", "S_signals[1].percentile", "shared_signal"]), [])


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
        res = N.run(WEEK, Decimal("0.50"), session=FakeSession(rt), run_id="t1", out=self.out, transmission=self.t, prompt="v1")
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
        res2 = N.run(WEEK, Decimal("0.50"), session=FakeSession(FakeRuntime(answer)), run_id="t2", out=self.out, transmission=self.t, prompt="v1")
        self.assertTrue(res2["review_sheet"].endswith(f"review_narratives_{WEEK}_t2.csv"))                # never overwritten

    def test_cap_stops_before_a_call_that_could_exceed_it(self):
        rt = FakeRuntime(answer)
        res = N.run(WEEK, Decimal("0.001"), session=FakeSession(rt), run_id="t3", out=self.out, transmission=self.t, prompt="v1")
        self.assertEqual((res["status"], len(rt.requests)), ("budget_limit", 0))
        self.assertTrue(all("not generated" in r["check_flags"] for r in self.rows(res).values() if r["status"] == "scored"))

    def test_invalid_output_is_flagged_not_published(self):
        rt = FakeRuntime(lambda card: {"so_what": "x", "facts_used": [], "caveats": []})              # so_now_what missing
        res = N.run(WEEK, Decimal("0.50"), session=FakeSession(rt), run_id="t4", out=self.out, transmission=self.t, prompt="v1")
        self.assertTrue(all("invalid output" in r["check_flags"] for r in self.rows(res).values() if r["status"] == "scored"))

    def test_dry_run_makes_no_call(self):
        res = N.run(WEEK, Decimal("0.50"), dry_run=True, session=FakeSession(None), run_id="t5", out=self.out, transmission=self.t, prompt="v1")
        self.assertEqual(res["status"], "dry_run")
        self.assertFalse((self.out / f"review_narratives_{WEEK}.csv").exists())


class PromptV2(unittest.TestCase):
    """The 2026-11-02 review fixes, as v2 input fields and v2 style checks."""
    def setUp(self):
        self.t = lambda r: {"event": "E", "mechanism": "M", "dtcc_process": "P"}
        self.rec = lambda rid: [r for r in SCORES["records"] if r["record_id"] == rid]

    def test_inputs_list_tied_signals_latest_pqd_v_meaning_and_plain_names(self):
        liq = N.build_input_v2(self.rec("ecs-nscc-liq"), SCORES["records"], self.t)
        self.assertEqual([x["field"] for x in liq["S_signals"]], ["vix_jump", "sofr_effr_adjusted"])          # both tie at S 5
        self.assertTrue(all(x["scope"] == "market-wide" for x in liq["S_signals"]))
        self.assertEqual((liq["latest_available_pqd_quarter"], liq["signal"]["plain_name"], liq["signal"]["scope"]),
                         ("2026Q2", "VIX relative to its 20-day average (ratio)", "market-wide"))
        self.assertEqual(liq["V_meaning"], "V 3 = this buffer measure (largest payment obligation to qualifying liquid resources for NSCC) "
                                           "sits at level 3 of 5 versus its own history")
        vol = N.build_input_v2(self.rec("ecs-nscc-03"), SCORES["records"], self.t)
        self.assertNotIn("latest_available_pqd_quarter", vol)                                                   # public proxy
        self.assertTrue(vol["V_source"].startswith("public proxy"))
        prompt = N.prompt_parts(N.PROMPTS["v2"])[0]
        for rule in ("never call it the next release", "Never describe it as stress at specific firms", "S_signals",
                     "instead of series codes", "V_meaning"):
            self.assertIn(rule, prompt)

    def test_style_flags_catch_the_reviewed_problems(self):
        xe = N.build_input_v2(self.rec("xe-member-ficc"), SCORES["records"], self.t)
        v1_text = ("The Baa−10Y spread signals elevated member credit stress; watch |ΔDGS10| and stress_loss_to_im.",
                   "Track the next PQD release (2026Q2).")
        flags = NC.style_flags(*v1_text, xe)
        self.assertEqual(len(flags), 4, flags)
        self.assertTrue(any("series codes" in f for f in flags) and any("next release" in f for f in flags)
                        and any("specific firms" in f for f in flags) and any("V meaning" in f for f in flags))
        edited = ("Baa corporate spreads widened 11 bp, a broad credit signal, not a firm-specific one. V is 1: the top-five "
                  "open-position share is at level 1 of 5 versus its own history.",
                  "Watch for any rating actions or stress at US member firms; check the next quarterly PQD release (latest PQD, 2026Q2).")
        self.assertEqual(NC.style_flags(*edited, xe), [])
        ok_last = ("Spreads widened; V is 1, level 1 of 5 versus its own history.", "Monitor the next DTCC PQD release (last reflected 2026Q2).")
        self.assertEqual(NC.style_flags(*ok_last, xe), [])

    def test_comparison_mode_never_writes_the_review_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            sheet = out / "reviewed.csv"
            with sheet.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=N.SHEET_FIELDS); w.writeheader()
                w.writerow({k: "" for k in N.SHEET_FIELDS} | {"record_id": "ecs-nscc-liq", "card_id": "ECS-NSCC-LIQ", "generated_by": "ai",
                                                               "corrected_so_what": "Edited.", "so_what": "Draft."})
            v2 = lambda card: {"so_what": "The VIX relative to its 20-day average reached 1.54. V is 3: level 3 of 5 versus its own history.",
                               "so_now_what": "S is also set by the SOFR−EFFR spread shared with FICC-GSD-02; watch the next quarterly PQD release.",
                               "facts_used": ["signal.plain_name"], "caveats": []}
            res = N.run(WEEK, Decimal("0.20"), session=FakeSession(FakeRuntime(v2)), run_id="c1", out=out, transmission=self.t,
                        prompt="v2", compare_with=sheet)
            self.assertFalse(any(out.glob("review_narratives_*.csv")))
            with (out / f"comparison_narratives_v2_{WEEK}.csv").open() as f:
                rows = {r["card_id"]: r for r in csv.DictReader(f)}
            liq = rows["ECS-NSCC-LIQ"]
            self.assertEqual((liq["edited_so_what"], liq["latest_not_next_pqd"], liq["plain_names"], liq["shared_signal_mentioned"],
                              liq["v_meaning_given"], liq["no_firm_specific_wording"]), ("Edited.", "yes", "yes", "yes", "yes", "yes"))
            self.assertTrue(res["prompt_version"].startswith("narrative-prompt-v2:"))


class PromptV3(unittest.TestCase):
    """v3: V short form, only the setting signal in so_what, no added interpretive words, no PQD on proxy cards."""
    def setUp(self):
        self.t = lambda r: {"event": "E", "mechanism": "Members' funding costs rise", "dtcc_process": "P"}
        self.inp = lambda rid: N.build_input_v3([r for r in SCORES["records"] if r["card_id"] == next(
            x["card_id"] for x in SCORES["records"] if x["record_id"] == rid)], SCORES["records"], self.t)

    def test_inputs(self):
        liq, g03, vol = self.inp("ecs-nscc-liq"), self.inp("ficc-gsd-03"), self.inp("ecs-nscc-03")
        self.assertEqual((liq["V_short"], liq["S_set_by"]), ("V 3 of 5 (medium vs own history)", "VIX relative to its 20-day average (ratio)"))
        self.assertTrue(g03["S_set_by"].startswith("event: Treasury clearing compliance date") and g03["V_short"].endswith("(medium vs own history)"))
        self.assertEqual(vol["V_short"], "V 1 of 5 (low vs own history)")
        self.assertEqual([N.v_level(v) for v in (1, 2, 3, 4, 5)], ["low", "low", "medium", "high", "high"])
        prompt = N.prompt_parts(N.PROMPTS["v3"])[0]
        for rule in ("V_short", "in at most 8 words", "interpretive words", "never mention PQD for this card", "at most 45 words"):
            self.assertIn(rule, prompt)

    def test_style_flags(self):
        liq, vol = self.inp("ecs-nscc-liq"), self.inp("ecs-nscc-03")
        good = ("VIX relative to its 20-day average reached the 97th percentile of 457 prior weeks, relevant to NSCC variation "
                "margin; V 3 of 5 (medium vs own history).", "S is also set by the SOFR−EFFR spread, shared with FICC-GSD-02. "
                "Watch the daily VIX ratio and the next quarterly PQD release.")
        self.assertEqual(NC.style_flags(*good, liq, version="v3"), [])
        bad = ("VIX and the SOFR−EFFR spread show funding stress; the largest payment obligation to qualifying liquid resources "
               "sits at level 3 of 5 versus its own history.", "Watch the strain.")
        flags = NC.style_flags(*bad, liq, version="v3")
        for expect in ("short form", "V ratio name", "interpretive words not in the input: strain, stress", "second tied signal", "lacks the percentile"):
            self.assertTrue(any(expect in f for f in flags), (expect, flags))
        proxy = ("US consolidated equity volume reached the 83rd percentile; V 1 of 5 (low vs own history), public proxy.",
                 "Watch the next quarterly PQD release.")
        self.assertIn("PQD mentioned on a public-proxy card", NC.check(*proxy, vol))          # base check since v3.1 (all versions)
        self.assertNotIn("interpretive", " ".join(NC.style_flags("GSD's stress-loss-to-margin ratio; V 1 of 5 (low vs own history).", "",
                                                                  self.inp("ficc-gsd-01"), version="v3")))
        self.assertEqual(NC.style_flags("Funding costs rise for members; V 1 of 5 (low vs own history).", "", self.inp("ficc-gsd-01"),
                                        version="v3")[-1:], ["so_what lacks the percentile of the signal that sets S (42nd)"])

    def test_comparison_file_has_three_texts_and_word_counts(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); sheet = out / "reviewed.csv"
            with sheet.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=N.SHEET_FIELDS); w.writeheader()
                w.writerow({k: "" for k in N.SHEET_FIELDS} | {"record_id": "ecs-nscc-liq", "card_id": "ECS-NSCC-LIQ", "generated_by": "ai",
                                                               "corrected_so_what": "Edited text here.", "corrected_so_now_what": "Watch."})
            with (out / f"comparison_narratives_v2_{WEEK}.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=N.COMPARE_FIELDS); w.writeheader()
                w.writerow({k: "" for k in N.COMPARE_FIELDS} | {"card_id": "ECS-NSCC-LIQ", "v2_so_what": "A b c.", "v2_so_now_what": "D."})
            v3 = lambda card: {"so_what": "VIX relative to its 20-day average reached the 97th percentile; V 3 of 5 (medium vs own history).",
                               "so_now_what": "S is also set by the SOFR−EFFR spread, shared with FICC-GSD-02.", "facts_used": ["S_set_by"], "caveats": []}
            N.run(WEEK, Decimal("0.20"), session=FakeSession(FakeRuntime(v3)), run_id="c3", out=out, transmission=self.t, prompt="v3", compare_with=sheet)
            with (out / f"comparison_narratives_v3_{WEEK}.csv").open() as f:
                liq = {r["card_id"]: r for r in csv.DictReader(f)}["ECS-NSCC-LIQ"]
        self.assertEqual((liq["edited_words"], liq["v2_words"], liq["v3_words"]), ("3/1", "3/1", "18/11"))
        self.assertEqual((liq["within_limits"], liq["v_short_form"], liq["only_setting_signal_in_so_what"], liq["shared_signal_mentioned"],
                          liq["no_pqd_on_proxy"]), ("yes", "yes", "yes", "yes", "n/a"))


class PromptV31(unittest.TestCase):
    """v3.1: proxy cards never mention PQD, short second-signal clause, so_what via the chain mechanism, verbatim headlines."""
    def setUp(self):
        self.t = N.chain_context()
        self.inp = lambda cid: N.build_input_v31([r for r in SCORES["records"] if r["card_id"] == cid], SCORES["records"], self.t)

    def test_default_prompt_inputs_and_proxy_shape(self):
        from . import weekly_news_run as W
        self.assertEqual((N.DEFAULT_PROMPT, W.NARRATIVE_PROMPT_VERSION), ("v3.1", "v3.1"))
        self.assertEqual(set(N.PROMPTS), {"v1", "v2", "v3", "v3.1"})                      # older prompts kept
        vol, liq = self.inp("ECS-NSCC-03"), self.inp("ECS-NSCC-LIQ")
        self.assertEqual(vol["watch_sources"], ["Cboe U.S. equities market volume history"])
        self.assertEqual(liq["watch_sources"], ["VIX index (FRED)", "SOFR (FRED)", "effective fed funds rate (FRED)"])
        self.assertEqual(liq["related_news"]["top_items"][1], {"title": "Tech stocks log worst day since 2020 as carnage comes to the AI trade",
                                                               "outlet": "MarketWatch"})
        prompt = N.prompt_parts(N.PROMPTS["v3.1"])[0]
        for rule in ("Public-proxy cards (never PQD)", "watch_sources", "transmission_chain.mechanism", "at most 8 words", "word for word"):
            self.assertIn(rule, prompt)

    def test_pqd_rejected_on_public_proxy_cards_in_every_check(self):
        vol = self.inp("ECS-NSCC-03")
        self.assertIn("PQD mentioned on a public-proxy card", NC.check("Volume rose; V 1 of 5, public proxy.", "Watch the next PQD release.", vol))
        self.assertNotIn("PQD mentioned on a public-proxy card",
                         NC.check("Volume rose; V 1 of 5, public proxy.", "Watch daily consolidated volume and Cboe volume history.", vol))
        self.assertEqual([f for f in NC.check("Spread rose; V 1 of 5.", "Watch the next PQD release.", self.inp("XE-MEMBER")) if "PQD" in f], [])

    def test_second_signal_clause_at_most_8_words(self):
        liq = self.inp("ECS-NSCC-LIQ")
        long = NC.style_flags("x", "Watch the VIX. S is also set by the SOFR−EFFR repo funding spread, shared with FICC-GSD-02.", liq, version="v3.1")
        self.assertIn("second-signal clause longer than 8 words (10)", long)
        short = NC.style_flags("x", "S also set by the SOFR−EFFR spread; shared with FICC-GSD-02.", liq, version="v3.1")
        self.assertFalse(any("second-signal clause" in f for f in short))

    def test_so_what_uses_the_chain_mechanism(self):
        liq = self.inp("ECS-NSCC-LIQ")           # mechanism: "Daily mark-to-market payments change sharply, requiring members to move more cash that day."
        weak = NC.style_flags("VIX relative to its 20-day average reached the 97th percentile, relevant to NSCC variation margin; "
                              "V 3 of 5 (medium vs own history).", "S also set by the SOFR−EFFR spread.", liq, version="v3.1")
        self.assertIn("so_what does not use the chain mechanism wording ('relevant to' is the only link)", weak)
        good = NC.style_flags("VIX relative to its 20-day average reached the 97th percentile, so daily mark-to-market payments can change "
                              "sharply; V 3 of 5 (medium vs own history).", "S also set by the SOFR−EFFR spread; shared with FICC-GSD-02.",
                              liq, version="v3.1")
        self.assertEqual(good, [])
        g03 = self.inp("FICC-GSD-03")
        self.assertIn("so_what lacks the date of the event that sets S (2026-12-31)",
                      NC.style_flags("The compliance date drives S; firms onboard to meet the rule; V 3 of 5 (medium vs own history).", "",
                                     g03, version="v3.1"))

    def test_interpretive_words_allowed_from_the_mechanism(self):
        g02 = self.inp("FICC-GSD-02")             # mechanism: "Members' funding costs rise, making daily settlement payments harder to fund."
        self.assertIn("interpretive words not in the input: strain", " ".join(
            NC.style_flags("The SOFR−EFFR spread reached the 90th percentile, a strain on funding; V 4 of 5 (high vs own history).", "", g02, "v3.1")))

    def test_related_news_headline_must_be_verbatim_and_attributed(self):
        liq = self.inp("ECS-NSCC-LIQ")
        base = ("VIX relative to its 20-day average reached the 97th percentile, so daily mark-to-market payments change sharply; "
                "V 3 of 5 (medium vs own history).")
        ok = NC.style_flags(base, 'MarketWatch: "Tech stocks log worst day since 2020". S also set by the SOFR−EFFR spread.', liq, "v3.1")
        self.assertFalse(any("headline" in f or "quoted" in f for f in ok), ok)
        altered = NC.style_flags(base, 'MarketWatch: "Tech stocks log their worst day in years".', liq, "v3.1")
        self.assertTrue(any("not a related-news headline" in f for f in altered))
        unattributed = NC.style_flags(base, 'Headlines said "Tech stocks log worst day since 2020".', liq, "v3.1")
        self.assertIn("headline not attributed to its outlet (MarketWatch)", unattributed)


class NamedSheetWithPublishedText(unittest.TestCase):
    def test_named_sheet_carries_published_text_and_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); reviewed = out / "reviewed.csv"
            with reviewed.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=N.SHEET_FIELDS); w.writeheader()
                w.writerow({k: "" for k in N.SHEET_FIELDS} | {"record_id": "ecs-nscc-liq", "generated_by": "ai", "so_what": "Draft.", "so_now_what": "Draft 2.",
                                                               "decision": "edit", "reviewer": "Wenqi Cai", "corrected_so_what": "Published edit."})
                w.writerow({k: "" for k in N.SHEET_FIELDS} | {"record_id": "ficc-gsd-01", "generated_by": "ai", "so_what": "Draft.", "so_now_what": "D."})
                w.writerow({k: "" for k in N.SHEET_FIELDS} | {"record_id": "ecs-set-01", "generated_by": "template"})
            sheet = out / f"review_narratives_{WEEK}_v31.csv"
            t = lambda r: {"event": "E", "mechanism": "M", "dtcc_process": "P"}
            N.run(WEEK, Decimal("0.50"), session=FakeSession(FakeRuntime(answer)), run_id="n1", out=out, transmission=t, prompt="v1",
                  sheet_path=sheet, published_from=reviewed)
            with sheet.open() as f:
                reader = csv.DictReader(f); rows = {r["record_id"]: r for r in reader}
            self.assertEqual(reader.fieldnames[reader.fieldnames.index("so_now_what") + 1:][:2], ["published_so_what", "published_so_now_what"])
            self.assertEqual((rows["ecs-nscc-liq"]["published_so_what"], rows["ecs-nscc-liq"]["published_so_now_what"]), ("Published edit.", "Draft 2."))
            self.assertEqual(rows["ficc-gsd-01"]["published_so_what"], "")                       # undecided: nothing published
            self.assertEqual(rows["ecs-set-01"]["published_so_what"], NC.TEMPLATE_SO_WHAT)
            self.assertTrue(all(r[k] == "" for r in rows.values() for k in ("decision", "reviewer", "corrected_so_what", "corrected_so_now_what")))
            self.assertFalse((out / f"review_narratives_{WEEK}.csv").exists())
            with self.assertRaises(FileExistsError):
                N.run(WEEK, Decimal("0.50"), session=FakeSession(FakeRuntime(answer)), run_id="n2", out=out, transmission=t, prompt="v1",
                      sheet_path=sheet, published_from=reviewed)


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
