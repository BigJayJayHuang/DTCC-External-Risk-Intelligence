"""Dashboard polish: related-news display order (ranking, exclusions, labels, dates), the member-notices source, the
validator check, and the page itself (collapsed unscored cards, top 5 / "Show all"). No AWS, no model.

The page tests drive a real browser and run only when Playwright and a local Chrome are available (they are skipped
otherwise); everything else is standard library."""
import functools, http.server, json, re, socket, subprocess, sys, tempfile, threading, unittest
from pathlib import Path

from . import card_front_checks as F
from . import google_news as G
from . import related_news_rank as R
from .paths import PROJECT

REPO = PROJECT.parent
WEEK = "2026-11-02"
CFG = R.load_config()
PUBLISHED = json.loads((REPO / "docs/data/risk_output.json").read_text())


def item(id_, week=WEEK):
    return next(i for i in PUBLISHED["items"] if i["id"] == id_ and i["snapshot"] == week)


def news(title, outlet="Other", url=None, label=None):
    return {"title": title, "outlet": outlet, "url": url or "u:" + title, **({"label": label} if label else {})}


class Ranking(unittest.TestCase):
    def test_keyword_then_priority_outlet_then_newest(self):
        rel = [news("Quiet day", "Other", "a"), news("Stocks slide", "Reuters", "b"), news("VIX jumps", "Other", "c"),
               news("Stocks drift", "Reuters", "d"), news("Late item", "Other", "e"), news("Undated", "Other", "f")]
        dates = {"a": "2026-11-06T10:00:00+00:00", "b": "2026-11-03T10:00:00+00:00", "c": "2026-11-02T10:00:00+00:00",
                 "d": "2026-11-05T10:00:00+00:00", "e": "2026-11-07T10:00:00+00:00"}
        out = R.rank(rel, ["VIX"], dates, CFG)
        self.assertEqual([e["index"] for e in out], [2, 3, 1, 4, 0, 5])     # keyword; Reuters newest first; then newest; undated last
        self.assertEqual([e["top"] for e in out], [True] * 5 + [False])
        self.assertEqual(out[0]["reason"], "card keyword “VIX”; not a priority outlet; published 2026-11-02")
        self.assertEqual(out[1]["reason"], "no card keyword; priority outlet (Reuters); published 2026-11-05")
        self.assertEqual(out[-1]["reason"], "no card keyword; not a priority outlet; publication date unknown")

    def test_ties_keep_the_original_order_and_aliases_match(self):
        rel = [news("One", "Bloomberg.com", "a"), news("Two", "The Wall Street Journal", "b"), news("Three", "AP News", "c")]
        out = R.rank(rel, [], {u: "2026-11-05T00:00:00+00:00" for u in "abc"}, CFG)
        self.assertEqual([(e["index"], e["priority_outlet"]) for e in out], [(0, "Bloomberg"), (1, "WSJ"), (2, "AP")])

    def test_keywords_follow_the_google_query_rules(self):
        kws = R.card_keywords()
        self.assertEqual(kws["ECS-NSCC-LIQ"], ["stock market selloff", "VIX", "spike", "broker", "margin calls"])
        import csv
        with (PROJECT / "validation/news_queries.csv").open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.assertEqual(R.query_terms(row["query"]), G.query_terms(row["query"]))
        for term, text in (("spike", "VIX spiked 70%"), ("margin calls", "Margin call season"), ("broker", "brokerage")):
            self.assertEqual(bool(R.term_regex(term).search(text)), bool(G._term_regex(term).search(text)), term)

    def test_dates_come_from_the_committed_week_files(self):
        dates = R.week_dates(WEEK)
        for it in (i for i in PUBLISHED["items"] if i["snapshot"] == WEEK):
            for n in it["related_news"]:
                self.assertIn(n["url"], dates)
        self.assertEqual(dates[item("ecs-nscc-liq")["related_news"][1]["url"]][:10], "2026-11-05")


class Exclusions(unittest.TestCase):
    def ranked(self, *titles, keywords=("stock market selloff",)):
        return {e["index"]: e for e in R.rank([news(t) for t in titles], list(keywords), {}, CFG)}

    def test_political_and_crypto_never_in_the_top_even_with_a_keyword(self):
        out = self.ranked("Trump blames Democrats for stock market selloff", "Bitcoin falls in stock market selloff",
                          "Republicans react", "Midterms loom", "Tech Stock Rout Raises Bitcoin Selling Risk", "Ethereum tokens slide")
        self.assertTrue(all(not e["top"] and e["excluded"] for e in out.values()))
        self.assertTrue(out[0]["excluded"].startswith("political commentary") and out[1]["excluded"].startswith("crypto"))

    def test_commodity_and_currency_only_with_a_card_keyword(self):
        out = self.ranked("Gold price falls below $4,000 as stock market selloff triggers liquidity pressure",
                          "Sterling dips as stock rout boosts dollar", "Oil jumps", "Yen weakens")
        self.assertTrue(out[0]["top"] and out[0]["excluded"] is None)                     # keyword: allowed
        self.assertTrue(all(out[i]["excluded"] and "without a card keyword" in out[i]["excluded"] for i in (1, 2, 3)))

    def test_whole_words_only(self):
        out = self.ranked("Goldman Sachs trims risk", "Turmoil in repo", "Europe stocks", "Tokenization pilot", keywords=())
        self.assertTrue(all(e["excluded"] is None and e["top"] for e in out.values()))

    def test_config_is_display_only_and_complete(self):
        self.assertIn("Display-only", CFG["_comment"])
        self.assertEqual(set(CFG["priority_outlets"]), {"Reuters", "Bloomberg", "WSJ", "Financial Times", "CNBC", "MarketWatch", "AP", "Barron's"})
        self.assertEqual(CFG["top_n"], 5)


class Labels(unittest.TestCase):
    def test_labelled_items_are_not_ranked_and_name_their_source(self):
        rel = [news("New member A", "DTCC", "a", "membership/onboarding"), news("Clearing deadline", "Other", "b")]
        out = R.rank(rel, [], {}, CFG)
        self.assertEqual([(e["index"], e["top"]) for e in out], [(1, True), (0, False)])
        self.assertTrue(out[1]["reason"].startswith("labelled membership/onboarding"))
        self.assertEqual(R.label_sources(rel, CFG), ["DTCC member notices"])

    def test_member_notices_in_the_sources_line(self):
        it = item("ficc-gsd-03")
        self.assertEqual(it["front_sources_line"], "Federal Register (SEC) · DTCC member notices · DTCC quarterly disclosures")
        others = [i for i in PUBLISHED["items"] if not any(n.get("label") for n in i["related_news"])]
        self.assertTrue(others and all("member notices" not in (i.get("front_sources_line") or "") for i in others))
        self.assertEqual(F.sources_line({"card_id": "X", "related_news": [{"label": "membership/onboarding"}]}, {}), "DTCC member notices")


class Published(unittest.TestCase):
    def test_week_top_five(self):
        top = lambda id_: [item(id_)["related_news"][e["index"]]["outlet"] for e in item(id_)["related_news_display"] if e["top"]]
        self.assertEqual(top("ecs-nscc-liq"), ["Benzinga", "Yahoo Finance", "Equiti Global", "Bloomberg.com", "WSJ"])
        self.assertEqual(top("ficc-gsd-01"), ["GuruFocus", "MarketWatch"])
        self.assertEqual(top("ficc-gsd-03"), ["Traders Union"])
        self.assertEqual(top("ecs-nscc-03"), ["Crypto Briefing"])

    def test_related_news_itself_is_unchanged(self):
        scores = json.loads((PROJECT / f"results/scoring/v1.3_indicator/weekly_scores_v1.3_{WEEK}.json").read_text())
        for r in scores["records"]:
            self.assertEqual(item(r["record_id"])["related_news"], r.get("related_news") or [])

    def test_validator_check(self):
        it = item("ecs-nscc-liq")
        bad = [dict(it, related_news_display=it["related_news_display"][1:]),
               dict(it, related_news_display=[dict(e, top=True) for e in it["related_news_display"]]),
               dict(it, related_news_display=[dict(e, top=True) if e["excluded"] else e for e in it["related_news_display"]])]
        for b in bad:
            data = dict(PUBLISHED, items=[b])
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(data, f)
            res = subprocess.run([sys.executable, str(REPO / "docs/data/validate_output.py"), f.name], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("related_news_display", res.stdout)


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright if Path("/Applications/Google Chrome.app").exists() or Path("/usr/bin/google-chrome").exists() else None


@unittest.skipUnless(_browser(), "needs Playwright and a local Chrome")
class Page(unittest.TestCase):
    """docs/index.html with the published risk_output.json, in a real browser."""
    @classmethod
    def setUpClass(cls):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        handler = functools.partial(Quiet, directory=str(REPO / "docs"))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{port}/index.html"
        cls.pw = _browser()().start()
        cls.browser = cls.pw.chromium.launch(channel="chrome", headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown()

    def open(self, hash_, n=[0]):
        n[0] += 1
        page = self.browser.new_page()
        page.goto(f"{self.base}?t={n[0]}#{hash_}"); page.wait_for_selector(".tabs, .dhead")
        return page

    def test_unscored_cards_collapse_under_the_scored_ones(self):
        page = self.open("ficc")
        scored = [i for i in PUBLISHED["items"] if i["snapshot"] == WEEK and i["business_line"] == "FICC" and i["status"] == "scored"]
        self.assertEqual(sorted(page.locator(".card .ctitle").all_inner_texts()), sorted(i["front_headline"] for i in scored))
        block = page.locator("details#others")
        self.assertFalse(block.evaluate("e => e.open"))
        self.assertIn("5 other cards: no market signal or relevant news this week", block.locator("summary").inner_text())
        self.assertIn("5 no relevant news found", page.locator(".summary").inner_text())          # summary counts unchanged
        block.locator("summary").click()
        rows = block.locator(".orow")
        self.assertEqual(rows.count(), 5)
        first = rows.nth(0).inner_text()
        self.assertTrue("FICC" in first and "Confidence:" in first and re.search(r"V \d · (PQD|public proxy)", first), first)
        rows.nth(0).locator(".olink").click(); page.wait_for_selector(".dhead")
        self.assertIn("#item/", page.url)
        page.close()

    def test_no_relevant_news_filter_shows_full_cards(self):
        page = self.open("ecs")
        page.locator('[data-sev="NoNews"]').click()
        n = sum(1 for i in PUBLISHED["items"] if i["snapshot"] == WEEK and i["business_line"] == "ECS" and i["status"] == "no_relevant_news")
        self.assertEqual(page.locator("details#others").count(), 0)
        self.assertEqual((page.locator(".card").count(), page.locator(".card .sev.NoNews").count()), (n, n))
        page.close()

    def test_older_weeks_say_news_not_scanned(self):
        page = self.open("ficc")
        page.select_option("#snap", "2026-10-26"); page.wait_for_timeout(100)
        self.assertRegex(page.locator("details#others summary").inner_text(), r"^\d+ other cards?: news not scanned")
        page.close()

    def test_related_news_top_five_and_show_all(self):
        page = self.open(f"item/ecs-nscc-liq/{WEEK}")
        self.assertEqual(page.locator(".related ul.rtop li").count(), 5)
        more = page.locator(".related details.morenews")
        self.assertEqual(more.locator("summary").inner_text(), "Show all 15")
        more.locator("summary").click()
        self.assertEqual(more.locator("li").count(), 15)
        page.close()
        page = self.open(f"item/ficc-gsd-03/{WEEK}")
        self.assertIn("7 new FICC members this week", page.locator(".related").inner_text())
        self.assertEqual(page.locator(".related details.morenews summary").inner_text(), "Show all 8")
        page.close()


if __name__ == "__main__":
    unittest.main()
