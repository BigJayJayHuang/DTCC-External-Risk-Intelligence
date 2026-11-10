"""Offline tests for review_sheet.py, promote_reviewed.py and the unreviewed-AI flags in scoring_v1_3 (temp files only)."""
import csv, io, json, tempfile, unittest
from datetime import date
from pathlib import Path

from . import promote_reviewed as PR
from . import review_sheet as RS
from . import scoring_v1_3 as S13
from .llm_classifier import PROJECT
from .test_scoring_v1_3 import CARDS, NO_EVENT, event, mkt, run

WEEK = date(2026, 11, 2)
CAND_FIELDS = ["geography", "new_information", "published_date", "event_type", "event_id", "title", "summary", "card_ids", "certainty", "original_certainty", "reach", "original_reach", "reach_basis",
               "named_participants", "announced_date", "effect_date", "stage", "source_tier", "outlet", "url", "content_scope",
               "same_as_event_id", "evidence_quotes", "llm_confidence", "validation_reasons", "prompt_version", "model_id", "article_file"]


def cand(cid, title, cards, outlet, day="2026-11-05", conf=0.55, cert=2, reach=2, quote=None, same_as="", tier="other", summary=None, etype="",
         geo="", new_info="", pub=""):
    return {"geography": geo, "new_information": new_info, "published_date": pub, "event_type": etype, "event_id": cid, "title": title, "summary": summary or title, "card_ids": cards, "certainty": 1, "original_certainty": cert,
            "reach": reach, "original_reach": reach, "reach_basis": "market_wide", "named_participants": "", "announced_date": day,
            "effect_date": day, "stage": "", "source_tier": tier, "outlet": outlet, "url": f"https://{outlet.lower().replace(' ', '')}.example/{cid}",
            "content_scope": "headline_only", "same_as_event_id": same_as, "evidence_quotes": json.dumps([quote or title]),
            "llm_confidence": conf, "validation_reasons": json.dumps(["certainty capped at 1: no primary source and fewer than 2 independent outlets"]),
            "prompt_version": "classifier-prompt-v1.4:test", "model_id": "test-model"}


class Grouping(unittest.TestCase):
    def sheet(self, cands):
        return self.sheet_ctx(cands)[0]

    def sheet_ctx(self, cands):
        with tempfile.TemporaryDirectory(dir=PROJECT / "data") as tmp:
            root = Path(tmp)
            for c in cands:
                (root / f"{c['event_id']}.txt").write_text(c["title"])
                c["article_file"] = str((root / f"{c['event_id']}.txt").relative_to(PROJECT))
            path = root / "c.csv"
            with path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=CAND_FIELDS); w.writeheader(); w.writerows(cands)
            return RS.build(path, WEEK)

    def test_same_occurrence_merged_and_certainty_lifted(self):
        rows = self.sheet([cand("A", "Tech stocks log worst day since 2020 in AI selloff", "ECS-NSCC-LIQ", "MarketWatch", conf=0.55),
                           cand("B", "Tech stocks suffer worst day since 2020 as AI selloff deepens", "ECS-NSCC-LIQ", "CNBC", day="2026-11-06", conf=0.5),
                           cand("C", "Hedge funds cut staff after repo losses", "FICC-GSD-11", "WSJ")])
        self.assertEqual(len(rows), 2)
        merged = next(r for r in rows if "|" in r["candidate_ids"])
        self.assertEqual((merged["candidate_ids"], merged["independent_outlets"]), ("A|B", 2))
        self.assertEqual((merged["certainty_before_grouping"], merged["certainty"]), (1, 2))   # two independent outlets lift the cap
        self.assertEqual(rows[0]["confidence"], 0.55)                                         # sorted by confidence, high to low

    def test_not_merged_when_cards_or_dates_differ(self):
        title = "Tech stocks log worst day since 2020 in AI selloff"
        rows = self.sheet([cand("A", title, "ECS-NSCC-LIQ", "MarketWatch"), cand("B", title, "XE-CYBER", "CNBC"),
                           cand("C", title, "ECS-NSCC-LIQ", "Reuters", day="2026-11-01")])
        self.assertEqual(len(rows), 3)

    def test_review_tier_and_would_be_scores(self):
        rows = self.sheet([cand("A", "Tech stocks log worst day since 2020", "ECS-NSCC-LIQ", "MarketWatch", reach=2),
                           cand("B", "Explainer on SOFR", "FICC-GSD-02", "Blog", cert=0, reach=0, day="2026-11-03")])
        hi = next(r for r in rows if r["candidate_ids"] == "A")
        lo = next(r for r in rows if r["candidate_ids"] == "B")
        sev = json.loads(hi["would_be_severity"])["ECS-NSCC-LIQ"]
        self.assertEqual(sev["severity"], hi["would_be_S"] * sev["V"])
        self.assertEqual(hi["review_tier"], "required" if hi["would_be_S"] >= 4 or sev["severity"] >= 6 else "auto")
        self.assertEqual((lo["would_be_S"], lo["review_tier"]), (1, "auto"))                   # 0 + 0 + timing 2 = 2 -> S 1, x V 4 < 6


class AmendmentD(Grouping):
    def test_market_moves_on_same_card_group_whatever_the_wording(self):
        rows = self.sheet([cand("A", "Tech stocks log worst day since 2020", "ECS-NSCC-LIQ", "MarketWatch", etype="market_move"),
                           cand("B", "VIX volatility index spikes 70 percent", "ECS-NSCC-LIQ", "Yahoo", day="2026-11-06", etype="market_move"),
                           cand("C", "Gold falls below $4,000", "FICC-GSD-01", "Equiti", etype="market_move")])
        self.assertEqual(sorted(r["candidate_ids"] for r in rows), ["A|B", "C"])

    def test_syndicated_copies_count_as_one_source(self):
        rows = self.sheet([cand("A", "French bank loses 100 million euros in cyberattack", "XE-CYBER", "BankInfoSecurity", etype="cyber"),
                           cand("B", "French Bank Loses 100 Million Euros in Cyberattack", "XE-CYBER", "Inshorts", conf=0.5, etype="cyber")])
        r = rows[0]
        self.assertEqual((r["candidate_ids"], r["independent_outlets"], r["syndication_collapsed"]), ("A|B", 1, 1))
        self.assertEqual(r["certainty"], 1)                                                      # no lift from a copy

    def test_context_rule_and_tiers(self):
        rows, ctx = self.sheet_ctx([
            cand("A", "Tech stocks log worst day since 2020", "ECS-NSCC-LIQ", "MarketWatch", etype="market_move"),
            cand("B", "Hedge funds dump Treasury positions as selloff deepens", "ECS-NSCC-LIQ|FICC-GSD-11", "WSJ", day="2026-11-02", etype="market_move"),  # 3 days from A
            cand("C", "Arini offloads debt amid margin calls", "ECS-NSCC-LIQ|XE-MEMBER", "WSJ", day="2026-11-03", etype="firm_specific")])
        by = {(r["candidate_ids"], r["card_ids"]): r for r in rows}
        self.assertEqual(sorted(by), [("A", "ECS-NSCC-LIQ"), ("B", "ECS-NSCC-LIQ"), ("B", "FICC-GSD-11"), ("C", "ECS-NSCC-LIQ|XE-MEMBER")])
        a = by[("A", "ECS-NSCC-LIQ")]
        self.assertEqual((a["review_tier"], a["scored_card_ids"], a["context_card_ids"], a["would_be_severity"]), ("context", "", "ECS-NSCC-LIQ", "{}"))
        self.assertEqual(by[("B", "ECS-NSCC-LIQ")]["review_tier"], "context")
        b11 = by[("B", "FICC-GSD-11")]
        self.assertEqual((b11["scored_card_ids"], b11["context_card_ids"]), ("FICC-GSD-11", ""))       # market move on a non-indicator card is scored
        self.assertIn(b11["review_tier"], ("required", "auto"))
        c = by[("C", "ECS-NSCC-LIQ|XE-MEMBER")]
        self.assertEqual((c["scored_card_ids"], c["context_card_ids"]), ("ECS-NSCC-LIQ|XE-MEMBER", ""))   # firm_specific is scored
        self.assertEqual(sorted((x["card_id"], x["url"].split("/")[-1]) for x in ctx), [("ECS-NSCC-LIQ", "A"), ("ECS-NSCC-LIQ", "B")])
        self.assertTrue(all(x["event_type"] == "market_move" and x["week"] == "2026-11-02" for x in ctx))

    def test_multi_card_market_move_does_not_merge_cards(self):
        rows, ctx = self.sheet_ctx([
            cand("A", "Tech stocks log worst day since 2020", "ECS-NSCC-LIQ", "MarketWatch", etype="market_move"),
            cand("B", "Selloff deepens, traders flee to Treasuries", "ECS-NSCC-LIQ|FICC-GSD-01", "MarketWatch2", etype="market_move"),
            cand("C", "Treasury yields rise on jobs data", "FICC-GSD-01", "GuruFocus", day="2026-11-06", etype="market_move")])
        self.assertEqual(sorted((r["card_ids"], r["candidate_ids"]) for r in rows), [("ECS-NSCC-LIQ", "A|B"), ("FICC-GSD-01", "B|C")])
        self.assertEqual(sorted((x["card_id"], x["url"].split("/")[-1]) for x in ctx),
                         [("ECS-NSCC-LIQ", "A"), ("ECS-NSCC-LIQ", "B"), ("FICC-GSD-01", "B"), ("FICC-GSD-01", "C")])

    def test_append_context_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "context_news.csv"
            row = {"week": "2026-11-02", "card_id": "ECS-NSCC-LIQ", "title": "t", "outlet": "o", "url": "u", "event_type": "market_move", "proposed_event_id": "PE"}
            self.assertEqual((RS.append_context(path, [row, row]), RS.append_context(path, [row])), (1, 0))
            with path.open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)


class CodeChecks(Grouping):
    def test_non_us_filtered_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "filtered_non_us.csv"
            cands = [cand("A", "French banking group hit by supply chain cyberattack", "XE-CYBER", "CSO Online", etype="cyber", geo="non_us"),
                     cand("B", "SEC sets new compliance date for Treasury repo clearing", "FICC-GSD-03", "SEC", etype="regulatory", geo="us", tier="regulator")]
            with tempfile.TemporaryDirectory(dir=PROJECT / "data") as d:
                root = Path(d)
                for c in cands:
                    (root / f"{c['event_id']}.txt").write_text(c["title"]); c["article_file"] = str((root / f"{c['event_id']}.txt").relative_to(PROJECT))
                path = root / "c.csv"
                with path.open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=CAND_FIELDS); w.writeheader(); w.writerows(cands)
                rows, _ = RS.build(path, WEEK, log)
            self.assertEqual([r["candidate_ids"] for r in rows], ["B"])
            with log.open() as f:
                logged = list(csv.DictReader(f))
            self.assertEqual([(r["candidate_id"], r["geography"], r["card_ids"]) for r in logged], [("A", "non_us", "XE-CYBER")])

    def test_duplicate_without_new_information(self):
        rows, ctx = self.sheet_ctx([cand("A", "DTCC highlights final implementation steps for Treasury clearing mandate", "FICC-GSD-03", "Traders Union",
                                         etype="regulatory", same_as="EV0006", new_info="False", geo="us"),
                                    cand("B", "SEC sets new compliance date for Treasury repo clearing", "FICC-GSD-03", "SEC", day="2026-11-03",
                                         etype="regulatory", same_as="EV0007", new_info="True", geo="us", tier="regulator")])
        by = {r["candidate_ids"]: r for r in rows}
        self.assertEqual((by["A"]["review_tier"], by["A"]["new_information"]), ("duplicate", "false"))
        self.assertNotEqual(by["B"]["review_tier"], "duplicate")
        self.assertEqual(by["B"]["new_information"], "true")
        self.assertEqual([(c["card_id"], c["proposed_event_id"]) for c in ctx], [("FICC-GSD-03", by["A"]["proposed_event_id"])])   # related news

    def test_date_flags(self):
        rows = self.sheet([cand("A", "Thinkorswim outage today: users report trading platform issues", "XE-CYBER", "The Sunday Guardian",
                                etype="operational", geo="us", pub="2026-11-06"),
                           cand("B", "Exchange outage halts trading for an hour", "XE-DISRUPT", "Reuters", day="2026-07-16",
                                etype="operational", geo="us", pub="2026-11-06")])
        by = {r["candidate_ids"]: r for r in rows}
        self.assertEqual((by["A"]["date_flags"], by["A"]["review_tier"] in ("required", "auto")), ("date_unverified", True))
        self.assertEqual((by["B"]["date_flags"], by["B"]["review_tier"]), ("date_unverified|date_mismatch", "date_review"))
        self.assertEqual(by["A"]["geography"], "us")


class CardGate(Grouping):                                                # Amendment E5
    def test_gate_terms(self):
        hit = ["Basis trade unwinds hit Treasuries", "Repo rates jump", "SOFR spikes", "sponsored repo volumes", "Agent-clearing growth",
               "hedge funds unwind basis-trades", "TREASURY market selloff"]
        miss = ["Hedge Funds Dump Positions and Cut Staff as Selloff Deepens", "Quarterly report shows losses", "Repository outage",
                "Sponsorship deal for fund"]
        self.assertTrue(all(RS.GATE_TERMS.search(t) for t in hit))
        self.assertFalse(any(RS.GATE_TERMS.search(t) for t in miss))

    def test_card_removed_and_tier_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate_log = Path(tmp) / "card_gate.csv"
            cands = [cand("A", "Hedge Funds Dump Positions and Cut Staff as Selloff Deepens", "ECS-NSCC-LIQ|FICC-GSD-11", "WSJ",
                          etype="market_move", geo="us", tier="major_media"),
                     cand("B", "Hedge fund basis trade unwind hits Treasury repo", "FICC-GSD-11", "Reuters", day="2026-11-03",
                          etype="firm_specific", geo="us", tier="major_media"),
                     cand("C", "Hedge fund closes after equity losses", "FICC-GSD-11", "Bloomberg", day="2026-11-03",
                          etype="firm_specific", geo="us", tier="major_media")]
            with tempfile.TemporaryDirectory(dir=PROJECT / "data") as d:
                root = Path(d)
                for c in cands:
                    (root / f"{c['event_id']}.txt").write_text(c["title"]); c["article_file"] = str((root / f"{c['event_id']}.txt").relative_to(PROJECT))
                path = root / "c.csv"
                with path.open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=CAND_FIELDS); w.writeheader(); w.writerows(cands)
                rows, ctx = RS.build(path, WEEK, None, gate_log)
            by = {r["candidate_ids"]: r for r in rows}
            self.assertEqual(sorted(by), ["A", "B"])                         # C had only FICC-GSD-11: dropped
            self.assertEqual((by["A"]["card_ids"], by["A"]["review_tier"]), ("ECS-NSCC-LIQ", "context"))   # now context under D
            self.assertIn(RS.GATE_FLAG, json.loads(by["A"]["validate_flags"]))
            self.assertEqual(by["B"]["card_ids"], "FICC-GSD-11")             # term present: kept
            self.assertNotIn(RS.GATE_FLAG, json.loads(by["B"]["validate_flags"]))
            self.assertEqual({c["card_id"] for c in ctx}, {"ECS-NSCC-LIQ"})
            with gate_log.open() as f:
                logged = {r["candidate_id"]: (r["card_ids_after"], r["action"]) for r in csv.DictReader(f)}
            self.assertEqual(logged, {"A": ("ECS-NSCC-LIQ", "card_removed"), "C": ("", "item_dropped")})


class AmendmentGAndMissingInfo(Grouping):
    def test_missing_new_information_is_kept_and_required(self):
        c = cand("A", "Self-Regulatory Organizations; MX2 LLC; Notice of Filing To Amend Rule 11.23", "ECS-SET-01", "Federal Register",
                 etype="regulatory", same_as="EV0003", geo="us", tier="official", reach=0, cert=1)
        c["validation_reasons"] = json.dumps(["new_information_missing"])
        row = self.sheet([c])[0]
        self.assertEqual((row["review_tier"], row["new_information"]), ("required", ""))
        self.assertIn("new_information_missing", json.loads(row["validate_flags"]))
        self.assertNotIn("sro_filing_capped_auto", json.loads(row["validate_flags"]))   # the cap never hides a missing answer

    def test_sro_filings_by_others_capped_at_auto(self):
        lt = cand("L", "Self-Regulatory Organizations: Long-Term Stock Exchange, Inc.; Notice of Filing and Immediate Effectiveness",
                  "ECS-SET-01|XE-DISRUPT", "Federal Register", etype="regulatory", geo="us", tier="official")
        ns = cand("N", "Self-Regulatory Organizations; National Securities Clearing Corporation; Notice of Filing Concerning ACATS",
                  "ECS-NSCC-08", "Federal Register", etype="regulatory", geo="us", tier="official")
        by = {r["candidate_ids"]: r for r in self.sheet([lt, ns])}
        self.assertEqual(by["L"]["review_tier"], "auto")
        self.assertIn("sro_filing_capped_auto", json.loads(by["L"]["validate_flags"]))
        self.assertEqual(by["N"]["review_tier"], "required")                     # NSCC filings keep their tier

    def test_new_member_notices_become_membership_context(self):
        m = cand("M", "GOV2286-26", "FICC-GSD-03", "DTCC", etype="regulatory", geo="us", tier="dtcc",
                 summary="New Agent Clearing Member of the Government Securities Division of FICC: Citigroup Global Markets Inc./ACM Omnibus Notice: GOV2286-26 Summary: x")
        s = cand("S", "GOV9999-26", "FICC-GSD-03", "DTCC", etype="regulatory", geo="us", tier="dtcc",
                 summary="New Sponsored Member of GSD placed on watch list Notice: GOV9999-26")       # G1 override: to the model
        with tempfile.TemporaryDirectory(dir=PROJECT / "data") as d:
            root = Path(d)
            for c in (m, s):
                (root / f"{c['event_id']}.txt").write_text(c["title"] + "\n\n" + c["summary"]); c["article_file"] = str((root / f"{c['event_id']}.txt").relative_to(PROJECT))
            path = root / "c.csv"
            with path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=CAND_FIELDS); w.writeheader(); w.writerows([m, s])
            rows, ctx = RS.build(path, WEEK)
        self.assertEqual([r["candidate_ids"] for r in rows], ["S"])
        self.assertEqual([(c["card_id"], c["label"], c["title"][:24]) for c in ctx if c["label"]],
                         [("FICC-GSD-03", "membership/onboarding", "New Agent Clearing Membe")])

    def test_rule_patterns(self):
        from . import official_notice_rules as GR
        self.assertEqual(GR.rule("Additional Account Activation: Mizuho Securities USA LLC, #4446")[0], "skip")
        self.assertEqual(GR.rule("Depositary Fees Notification Security: X")[0], "skip")
        self.assertEqual(GR.rule("Tax Relief Country: IRELAND")[0], "skip")
        self.assertEqual(GR.rule("Additional Account Retirement: firm placed on watch list")[0], "override")
        self.assertEqual(GR.rule("Delete Sponsored Member Notice: GOV2281-26")[0], None)
        self.assertEqual(GR.rule("New NSCC member: Example Clearing LLC")[2], "ECS-NSCC-LIQ")
        self.assertEqual(GR.sro_filer("Self-Regulatory Organizations; Cboe BZX Exchange, Inc.; Notice of Filing"), "Cboe BZX Exchange, Inc.")
        self.assertFalse(GR.capped_sro_filing("Self-Regulatory Organizations; Fixed Income Clearing Corporation; Notice"))
        self.assertFalse(GR.capped_sro_filing("Order Granting Exemptive Relief"))

    def test_context_file_gains_label_column_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ctx.csv"
            p.write_text("week,card_id,title,outlet,url,event_type,proposed_event_id\n2026-11-02,ECS-NSCC-LIQ,T,O,https://a,market_move,PE-1\n")
            n = RS.append_context(p, [{"week": "2026-11-02", "card_id": "FICC-GSD-03", "title": "New member", "outlet": "DTCC",
                                       "url": "https://b", "event_type": "regulatory", "proposed_event_id": "", "label": "membership/onboarding"}])
            rows = list(csv.DictReader(p.open()))
        self.assertEqual((n, [r["label"] for r in rows], rows[0]["proposed_event_id"]), (1, ["", "membership/onboarding"], "PE-1"))


class Promote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.register = self.root / "register.csv"
        src = PROJECT / "data/events/event_register.csv"
        self.register.write_text(src.read_text())                      # a copy; the real register is never written
        self.spec_ok = self.root / "spec_ok.md"
        self.spec_ok.write_text("# s\n\n## Amendment C — x\n\nApproved: Test Reviewer, 2026-11-08T00:00Z\n")
        self.spec_no = self.root / "spec_no.md"
        self.spec_no.write_text("# s\n\n## Amendment C — x\n\nStatus: PROPOSED\n")

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, pid, tier, decision="", reviewer="", same_as="", **kw):
        base = {"proposed_event_id": pid, "title": "Tech stocks log worst day since 2020", "card_ids": "ECS-NSCC-LIQ", "certainty": "1",
                "certainty_before_grouping": "1", "reach": "2", "reach_basis": "market_wide", "announced_date": "2026-11-05",
                "effect_date": "2026-11-05", "would_be_S": "4" if tier == "required" else "2", "would_be_severity": "{}", "review_tier": tier,
                "same_as_event_id": same_as, "stage": "", "named_participants": "", "independent_outlets": "1",
                "sources": json.dumps([{"outlet": "MarketWatch", "url": "https://mw.example/a", "content_scope": "headline_only", "source_tier": "major_media"}]),
                "evidence_quotes": json.dumps(["Tech stocks log worst day since 2020"]), "confidence": "0.55", "validate_flags": "[]",
                "candidate_ids": "CAND-x", "prompt_version": "p", "model": "m", "decision": decision, "reviewer": reviewer,
                "corrected_card_ids": "", "corrected_certainty": "", "corrected_reach": "", "reviewer_notes": ""}
        return {**base, **kw}

    def write_sheet(self, rows):
        path = self.root / "sheet.csv"
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=RS.FIELDS); w.writeheader(); w.writerows(rows)
        return path

    def reg_rows(self):
        with self.register.open() as f:
            return list(csv.DictReader(f))

    def test_edit_with_corrected_fields_and_recomputed_s(self):
        src = [{"url": "https://www.sec.gov/files/rules/exorders/2026/34-106789.pdf", "outlet": "SEC", "source_tier": "regulator"},
               {"url": "https://www.federalregister.gov/d/2026-22493", "outlet": "Federal Register", "source_tier": "official"}]
        sheet = self.write_sheet([self.row("PE-2026-11-02-aaaa0001", "required", "edit", "Wenqi Cai", card_ids="FICC-GSD-03", would_be_S="5",
                                           corrected_title="SEC exempts certain repo transactions", corrected_certainty="2", corrected_reach="2",
                                           corrected_reach_basis="market_wide", corrected_announced_date="2026-10-30",
                                           corrected_effect_date="2027-06-30", corrected_sources=json.dumps(src),
                                           reviewer_notes="Narrows the scope of the repo clearing mandate.")])
        res = PR.promote(sheet, self.register, today="2026-11-10", spec=self.spec_ok)
        row = self.reg_rows()[-1]
        self.assertEqual((row["title"], row["announced_date"], row["effect_date"], row["certainty"], row["reach"], row["reach_basis"]),
                         ("SEC exempts certain repo transactions", "2026-10-30", "2027-06-30", "2", "2", "market_wide"))
        self.assertEqual((row["source_url"].split(" ; ")[0], row["source_tier"], row["outlet"]), (src[0]["url"], "regulator", "SEC; Federal Register"))
        self.assertEqual((row["entered_by"], row["review_status"], row["needs_review"]), ("Wenqi Cai", "reviewed", "N"))
        self.assertEqual(res["inserted"][0]["S_in_week"], 2)                    # effect far off: timing 0 caps S at 2
        self.assertEqual(res["needs_signoff_for_S_ge_4"], [])                   # the model's would_be_S 5 no longer counts
        self.assertIn("Narrows the scope", row["notes"])

    def test_bad_corrections_and_routing_refused(self):
        for kw in ({"corrected_effect_date": "30/06/2027"}, {"corrected_reach_basis": "global"},
                   {"corrected_sources": json.dumps([{"url": "ftp://x", "outlet": "SEC", "source_tier": "regulator"}])}):
            with self.assertRaises(PR.PromotionError):
                PR.promote(self.write_sheet([self.row("P1", "required", "edit", "Wenqi Cai", **kw)]), self.register, spec=self.spec_ok)
        with self.assertRaises(PR.PromotionError):
            PR.promote(self.write_sheet([self.row("P1", "required", "approve", "Wenqi Cai", route_context_card_ids="FICC-GSD-03")]),
                       self.register, spec=self.spec_ok)

    def test_rejected_rows_routed_to_context(self):
        rows = [self.row("PE-2026-11-02-r1", "required", "reject", "Wenqi Cai", route_context_card_ids="FICC-GSD-03",
                         route_context_label="membership/onboarding", event_type="regulatory", context_card_ids=""),
                self.row("PE-2026-11-02-r2", "required", "reject", "Wenqi Cai", event_type="regulatory", context_card_ids=""),
                self.row("PE-2026-11-02-c1", "context", event_type="market_move", context_card_ids="ECS-NSCC-LIQ")]
        ctx = RS.reviewed_context_rows(rows, date(2026, 11, 2))
        self.assertEqual([(c["card_id"], c["label"], c["proposed_event_id"][-2:]) for c in ctx],
                         [("FICC-GSD-03", "membership/onboarding", "r1"), ("ECS-NSCC-LIQ", "", "c1")])

    def test_required_without_decision_refused_and_nothing_written(self):
        before = self.register.read_text()
        with self.assertRaises(PR.PromotionError):
            PR.promote(self.write_sheet([self.row("P1", "required"), self.row("P2", "auto")]), self.register, spec=self.spec_ok)
        self.assertEqual(self.register.read_text(), before)

    def test_approve_auto_reject_merge_and_idempotent(self):
        sheet = self.write_sheet([self.row("P1", "required", "approve", "Wenqi Cai"), self.row("P2", "auto"),
                                  self.row("P3", "auto", "reject"), self.row("P4", "required", "approve", "Wenqi Cai", same_as="EV0006"),
                                  self.row("P5", "required", "edit", "Wenqi Cai", corrected_certainty="2", corrected_card_ids="ECS-NSCC-LIQ|FICC-GSD-11")])
        n0 = len(self.reg_rows())
        res = PR.promote(sheet, self.register, today="2026-11-08", spec=self.spec_ok)
        rows = {r["proposal_id"]: r for r in self.reg_rows() if r.get("proposal_id")}
        self.assertEqual(len(self.reg_rows()), n0 + 3)
        self.assertEqual((rows["P1"]["entered_by"], rows["P1"]["review_status"], rows["P1"]["needs_review"]), ("Wenqi Cai", "reviewed", "N"))
        self.assertEqual((rows["P2"]["entered_by"], rows["P2"]["review_status"], rows["P2"]["needs_review"]), ("llm-auto", "unreviewed", "Y"))
        self.assertEqual((rows["P5"]["certainty"], rows["P5"]["card_ids"], rows["P5"]["chain_id"]), ("2", "ECS-NSCC-LIQ|FICC-GSD-11", "ECS-NSCC-LIQ"))
        self.assertEqual(res["rejected"], ["P3"]); self.assertEqual(res["manual_merge"], [{"proposal": "P4", "existing_event": "EV0006"}])
        self.assertEqual(sorted(res["needs_signoff_for_S_ge_4"]), sorted([rows["P1"]["event_id"], rows["P5"]["event_id"]]))
        ids = [r["event_id"] for r in csv.DictReader(io.StringIO((PROJECT / "data/events/event_register.csv").read_text()))]
        ids += [r["event_id"] for r in csv.DictReader(io.StringIO((PROJECT / "data/events/register_changelog.csv").read_text()))]
        nxt = max(int(e[2:]) for e in ids) + 1                                                  # removed ids are never reused
        self.assertEqual([r["event_id"] for r in self.reg_rows()][-3:], [f"EV{n:04d}" for n in range(nxt, nxt + 3)])   # numbering continues
        again = PR.promote(sheet, self.register, today="2026-11-08", spec=self.spec_ok)                # idempotent
        self.assertEqual((len(self.reg_rows()), again["inserted"]), (n0 + 3, []))
        self.assertEqual(sorted(again["skipped_already_promoted"]), ["P1", "P2", "P5"])

    def test_auto_rows_need_approved_amendment_c(self):
        with self.assertRaises(PR.PromotionError):
            PR.promote(self.write_sheet([self.row("P2", "auto")]), self.register, spec=self.spec_no)
        self.assertTrue(PR.amendment_c_approved(PR.SPEC))           # the real spec: Amendment C approved 2026-11-08

    def test_context_rows_skipped_and_only_scored_cards_inserted(self):
        res = PR.promote(self.write_sheet([self.row("P6", "context"), self.row("P7", "auto", card_ids="ECS-NSCC-LIQ|FICC-GSD-11",
                                                                                    scored_card_ids="FICC-GSD-11", context_card_ids="ECS-NSCC-LIQ")]),
                         self.register, spec=self.spec_ok)
        self.assertEqual(res["context_not_promoted"], ["P6"])
        rows = {r["proposal_id"]: r for r in self.reg_rows() if r.get("proposal_id")}
        self.assertNotIn("P6", rows)
        self.assertEqual((rows["P7"]["card_ids"], rows["P7"]["chain_id"]), ("FICC-GSD-11", "FICC-GSD-11"))

    def test_duplicate_skipped_and_date_review_needs_decision(self):
        res = PR.promote(self.write_sheet([self.row("P8", "duplicate", same_as="EV0006")]), self.register, spec=self.spec_ok)
        self.assertEqual((res["duplicate_not_promoted"], res["inserted"]), (["P8"], []))
        with self.assertRaises(PR.PromotionError):
            PR.promote(self.write_sheet([self.row("P9", "date_review")]), self.register, spec=self.spec_ok)

    def test_bad_rows_rejected(self):
        for bad in (self.row("P1", "required", "approve"), self.row("P1", "required", "maybe", "R"),
                    self.row("P1", "required", "edit", "R", corrected_card_ids="NOT-A-CARD"), self.row("P1", "required", "edit", "R", corrected_reach="5")):
            with self.assertRaises(PR.PromotionError):
                PR.promote(self.write_sheet([bad]), self.register, spec=self.spec_ok)

    def test_promoted_rows_load_in_scoring(self):
        from unittest import mock
        from . import scoring as V12
        PR.promote(self.write_sheet([self.row("P2", "auto")]), self.register, spec=self.spec_ok)
        with mock.patch.object(V12, "REGISTER", self.register):
            reg = V12.load_register()
            events = V12.load_events(reg)
        row = reg.iloc[-1]
        self.assertEqual((row["entered_by"], row["review_status"]), ("llm-auto", "unreviewed"))
        promoted = next(e for e in events if e.event_id == row["event_id"])
        self.assertEqual((promoted.certainty, promoted.reach, promoted.card_ids), (1, 2, ["ECS-NSCC-LIQ"]))
        self.assertIn("register needs_review = Y", promoted.review_reasons)


class ScoringFlags(unittest.TestCase):
    def unreviewed(self, S, **kw):
        ev = event(S, card_ids=["FICC-GSD-03"])
        ev["events"][0].update(entered_by="llm-auto", review_status="unreviewed", **kw)
        return ev

    def test_unreviewed_event_kept_off_main_and_labelled(self):
        r = run("FICC-GSD-03", ev=self.unreviewed(4), V=3)               # S 4 x V 3 = 12
        self.assertEqual((r["severity"], r["show_on_main"], r["event_review_label"]), (12, False, "AI-classified, not reviewed"))
        self.assertEqual(r["event_manual"]["events"][0]["entered_by"], "llm-auto")

    def test_market_tie_keeps_main_but_labels(self):
        r = run("FICC-GSD-02", market={"FICC-GSD-02": mkt(4)}, ev=self.unreviewed(4, card_ids=["FICC-GSD-02"]), V=4)
        self.assertEqual((r["S_source"], r["show_on_main"], r["event_review_label"]), ("market+event_manual", True, "AI-classified, not reviewed"))

    def test_related_news_display_only(self):
        news = [{"title": "Tech stocks log worst day since 2020", "outlet": "MarketWatch", "url": "u", "event_type": "market_move", "proposed_event_id": "PE"}]
        card = CARDS["ECS-NSCC-LIQ"]
        from .test_scoring_v1_3 import FULL, FRI, WEEK as W, vrec, days
        cov = S13.coverage([m["field"] for m in card["market_chains"]], FULL, FRI)
        market = {"ECS-NSCC-01": mkt(3), "ECS-NSCC-02": mkt(2)}
        daily = {c: days(r["weekly_peak"]) for c, r in market.items()}
        a = S13.card_week(card, W, market_recs=market, cov=cov, ev=NO_EVENT, v=vrec(3), check={}, daily=daily, related=news)
        b = S13.card_week(card, W, market_recs=market, cov=cov, ev=NO_EVENT, v=vrec(3), check={}, daily=daily)
        self.assertEqual((a["related_news"], b["related_news"]), (news, []))
        self.assertEqual({k: v for k, v in a.items() if k != "related_news"}, {k: v for k, v in b.items() if k != "related_news"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.csv"
            RS.append_context(path, [{"week": "2026-11-02", "card_id": "ECS-NSCC-LIQ", **news[0]}])
            self.assertEqual(S13.load_context_news(path)[("2026-11-02", "ECS-NSCC-LIQ")], news)

    def test_reviewed_event_unchanged(self):
        r = run("FICC-GSD-03", ev=event(4), V=3)
        self.assertEqual((r["show_on_main"], r["event_review_label"]), (True, None))
        self.assertEqual(run("FICC-GSD-01", market={"FICC-GSD-01": mkt(3)}, V=3)["event_review_label"], None)


if __name__ == "__main__":
    unittest.main()
