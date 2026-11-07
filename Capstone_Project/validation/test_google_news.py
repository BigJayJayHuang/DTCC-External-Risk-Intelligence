"""Offline tests for validation/google_news.py and the classifier's Google News input path (fixtures only, no network)."""
import csv, json, tempfile, unittest
from datetime import date, datetime, timezone
from pathlib import Path

from . import google_news as G
from . import llm_classifier as L

CONFIG = json.loads(G.CONFIG.read_text())
MONDAY = date(2026, 11, 2)


def rss(*items):
    body = "".join(
        f"<item><title>{t} - {o}</title><link>https://news.google.com/rss/articles/{lid}?oc=5</link>"
        f"<guid>{lid}</guid><pubDate>{d}</pubDate>"
        f"<description>&lt;a href=\"https://news.google.com/rss/articles/{lid}\"&gt;{t}&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color=\"#6f6f6f\"&gt;{o}&lt;/font&gt;</description>"
        f"<source url=\"{u}\">{o}</source></item>" for t, o, u, lid, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>q</title>{body}</channel></rss>'.encode()


A = ("Repo rates spike as Treasury settlement drains cash", "Reuters", "https://www.reuters.com", "CBMiAAA1", "Tue, 03 Nov 2026 14:00:00 GMT")
A_DUP = ("Repo rates spike as Treasury settlement drains cash!", "Yahoo Finance", "https://finance.yahoo.com", "CBMiAAA2", "Tue, 03 Nov 2026 15:00:00 GMT")
B = ("Hedge fund basis trade unwind deepens", "Bloomberg.com", "https://www.bloomberg.com", "CBMiAAA3", "Wed, 04 Nov 2026 09:00:00 GMT")
OLD = ("Last week's repo story", "Reuters", "https://www.reuters.com", "CBMiAAA4", "Fri, 30 Oct 2026 09:00:00 GMT")


class Window(unittest.TestCase):
    def test_default_is_last_full_week(self):
        self.assertEqual(G.last_full_week(date(2026, 11, 7)), date(2026, 10, 26))   # Saturday -> previous Mon-Sun
        self.assertEqual(G.last_full_week(date(2026, 11, 9)), date(2026, 11, 2))    # Monday -> week just ended

    def test_query_covers_monday_to_sunday(self):
        self.assertEqual(G.search_query('"repo rates" spike', MONDAY), '"repo rates" spike after:2026-11-01 before:2026-11-09')
        url = G.feed_url(CONFIG, 'SOFR spike', MONDAY)
        self.assertTrue(url.startswith("https://news.google.com/rss/search?q=SOFR+spike+after%3A2026-11-01+before%3A2026-11-09"))
        self.assertIn("hl=en-US&gl=US&ceid=US%3AUS".replace("US%3AUS", "US%3Aen"), url)

    def test_week_start_must_be_monday(self):
        with self.assertRaises(ValueError):
            G.week_window(date(2026, 11, 3))


class Client(unittest.TestCase):
    def test_honest_user_agent(self):
        ua = CONFIG["user_agent"]
        self.assertNotIn("Mozilla", ua)
        self.assertNotIn("@", ua)
        self.assertIn("github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence", ua)

    def test_rate_limit_two_seconds(self):
        t, slept = [0.0], []
        lim = G.RateLimiter(2.0, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
        lim.wait(); t[0] += 0.5; lim.wait(); lim.wait()
        self.assertEqual(slept, [1.5, 2.0])
        self.assertEqual(CONFIG["min_request_interval_seconds"], 2.0)


class Parsing(unittest.TestCase):
    def test_parse_item(self):
        it = G.parse_rss(rss(A), CONFIG)[0]
        self.assertEqual((it["title"], it["outlet"], it["outlet_url"], it["snippet"]),
                         (A[0], "Reuters", "https://www.reuters.com", ""))
        self.assertEqual(it["published_at_utc"], "2026-11-03T14:00:00+00:00")
        self.assertEqual((it["publisher_url"], it["url_resolution"]), ("", "not_resolvable_without_browser"))
        self.assertTrue(it["google_link"].startswith("https://news.google.com/rss/articles/CBMiAAA1"))

    def test_tiers(self):
        self.assertEqual(G.source_tier({"outlet": "Reuters", "outlet_url": "https://www.reuters.com", "publisher_url": ""}, CONFIG), "major_media")
        self.assertEqual(G.source_tier({"outlet": "SEC.gov", "outlet_url": "https://www.sec.gov", "publisher_url": ""}, CONFIG), "regulator")
        self.assertEqual(G.source_tier({"outlet": "Some Blog", "outlet_url": "https://blog.example", "publisher_url": ""}, CONFIG), "other")


class Keywords(unittest.TestCase):
    def test_terms_and_matching(self):
        self.assertEqual(G.query_terms('"hedge fund" "margin call"'), ["hedge fund", "margin call"])
        self.assertTrue(G.query_matches('"repo rates" spike', "Repo rates spiked overnight"))
        self.assertFalse(G.query_matches('"repo rates" spike', "Repo rates were calm"))
        self.assertTrue(G.query_matches('"T+0" settlement', "SEC weighs T+0 settlement"))
        self.assertFalse(G.query_matches("SOFR spike", "SOFRA spike"))          # not inside a longer word

    def test_official_prefilter(self):
        q = [("FICC-GSD-03", '"Treasury clearing" mandate'), ("ECS-SET-01", '"settlement cycle"')]
        rows = [
            {"document_id": "1", "title": "SEC extends Treasury clearing mandate dates", "summary": "", "url": "u1",
             "source_id": "sec_press", "publication_date": "2026-11-03", "published_at_utc": ""},
            {"document_id": "2", "title": "Self-regulatory organization fee filing", "summary": "Routine.", "url": "u2",
             "source_id": "federal_register", "publication_date": "2026-11-04", "published_at_utc": ""},
            {"document_id": "3", "title": "Settlement cycle change", "summary": "", "url": "u3",
             "source_id": "federal_register", "publication_date": "2026-10-30", "published_at_utc": ""},   # outside week
            {"document_id": "4", "title": "Settlement cycle change", "summary": "", "url": "u4",
             "source_id": "not_official", "publication_date": "2026-11-03", "published_at_utc": ""}]
        kept, dropped = G.prefilter_official(rows, q, set(CONFIG["official_source_ids"]), date(2026, 11, 2), date(2026, 11, 8))
        self.assertEqual([r["document_id"] for r in kept], ["1"])
        self.assertEqual(kept[0]["matched_card_ids"], "FICC-GSD-03")
        self.assertEqual([(d["document_id"], d["reason"]) for d in dropped], [("2", "no card query matched title or summary")])


class Collect(unittest.TestCase):
    def run_collect(self, feeds, queries, limit=None):
        cfg = dict(CONFIG, max_items_per_card=limit or CONFIG["max_items_per_card"])
        calls = []
        def fetch(url):
            calls.append(url)
            return 200, feeds[len(calls) - 1]
        with tempfile.TemporaryDirectory() as tmp:
            rows, manifest, stats, merged = G.collect(cfg, queries, MONDAY, Path(tmp), fetch=fetch,
                                                     now=datetime(2026, 11, 7, tzinfo=timezone.utc))
            raw = sorted(p.name for p in (Path(tmp) / "google_news_raw").iterdir())
        return rows, manifest, stats, calls, raw

    def test_dedupe_merge_hints_and_week_filter(self):
        q = [("FICC-GSD-02", '"repo rates" spike'), ("FICC-GSD-11", '"basis trade" unwind'), ("FICC-GSD-02", "SOFR spike")]
        rows, manifest, stats, calls, raw = self.run_collect([rss(A, OLD), rss(B, A_DUP), rss(A)], q)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(raw), 3)
        self.assertEqual(stats["raw_hits_in_week"], 4)                                   # OLD is outside the week
        self.assertEqual(len(rows), 2)                                                     # A_DUP merged into A (title), A repeated (URL)
        a = next(r for r in rows if r["title"] == A[0])
        self.assertEqual(a["matched_card_ids"], "FICC-GSD-02|FICC-GSD-11")
        self.assertEqual(json.loads(a["matched_queries"]), {"FICC-GSD-02": ['"repo rates" spike', "SOFR spike"],
                                                            "FICC-GSD-11": ['"basis trade" unwind']})
        self.assertEqual((a["source_id"], a["content_scope"], a["source_tier"]), ("google_news_rss", "headline_snippet", "major_media"))
        self.assertEqual(a["url"], a["google_link"])

    def test_cap_per_card(self):
        import hashlib
        many = [(f"{hashlib.sha256(str(n).encode()).hexdigest()} repo rates spike", "Outlet", "https://o.example", f"CBMiN{n:03d}",
                 "Wed, 04 Nov 2026 09:00:00 GMT") for n in range(30)]    # 30 genuinely distinct headlines
        rows, *_ = self.run_collect([rss(*many)], [("FICC-GSD-02", '"repo rates" spike')])
        self.assertEqual(len(rows), 25)

    def test_headline_filter_rules(self):
        loose = ("Argentina bonds drop as market flags intervention", "Some Blog", "https://blog.example", "CBMiL001", "Thu, 05 Nov 2026 22:00:00 GMT")
        part = ("Repo desks brace for quarter-end", "Some Blog", "https://blog.example", "CBMiL002", "Thu, 05 Nov 2026 22:00:00 GMT")
        major = ("Sterling dips as stock rout boosts dollar", "Reuters", "https://www.reuters.com", "CBMiL003", "Thu, 05 Nov 2026 22:00:00 GMT")
        rows, manifest, stats, calls, raw = self.run_collect([rss(A, loose, part, major)], [("FICC-GSD-02", '"repo rates" spike')])
        by = {r["title"]: r for r in rows}
        self.assertEqual(set(by), {A[0], major[0]})
        self.assertEqual((by[A[0]]["keep_rule"], by[A[0]]["headline_term_match"]), ("all_terms_headline_match", "full"))
        self.assertEqual((by[major[0]]["keep_rule"], by[major[0]]["headline_term_match"]), ("major_media_outlet", "none"))
        self.assertEqual(stats["headline_filter"], {"passed": 2, "dropped": 2,
                                                    "passed_by_rule": {"all_terms_headline_match": 1, "major_media_outlet": 1},
                                                    "passed_by_headline_term_match": {"full": 1, "none": 1}})

    def test_filtered_items_are_listed(self):
        loose = ("Argentina bonds drop", "Some Blog", "https://blog.example", "CBMiL001", "Thu, 05 Nov 2026 22:00:00 GMT")
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, dropped = G.collect(CONFIG, [("FICC-GSD-02", '"repo rates" spike')], MONDAY, Path(tmp),
                                         fetch=lambda url: (200, rss(loose)))
        self.assertEqual([(d["title"], d["headline_term_match"]) for d in dropped], [("Argentina bonds drop", "none")])
        self.assertIn("major-media", dropped[0]["reason"])

    def test_rate_limited_response_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = iter([(429, b""), (200, rss(A))])
            rows, manifest, stats, _ = G.collect(CONFIG, [("FICC-GSD-02", "a"), ("FICC-GSD-01", "b")], MONDAY, Path(tmp),
                                                 fetch=lambda url: next(out))
        self.assertEqual((len(manifest), rows), (1, []))


class ClassifierInput(unittest.TestCase):
    def test_google_rows_and_hints_reach_the_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.csv"
            fields = G.BASE_FIELDS + G.EXTRA_FIELDS
            with path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
                w.writerow({"document_id": "g1", "title": "Repo rates spike", "url": "https://news.google.com/rss/articles/X",
                            "publication_date": "", "published_at_utc": "2026-11-03T14:00:00+00:00", "summary": "",
                            "source_id": "google_news_rss", "outlet": "Reuters", "source_tier": "major_media",
                            "matched_card_ids": "FICC-GSD-02|ECS-NSCC-09", "content_scope": "headline_snippet"})
                w.writerow({"document_id": "o1", "title": "Routine notice", "url": "https://www.dtcc.com/n",
                            "publication_date": "2026-11-03", "published_at_utc": "", "summary": "Body",
                            "source_id": "dtcc_notice_feed"})
            arts, cov = L.load_news(path, date(2026, 11, 2), date(2026, 11, 8), None)
        g = next(a for a in arts if a["document_id"] == "g1")
        o = next(a for a in arts if a["document_id"] == "o1")
        self.assertEqual((g["outlet"], g["source_tier"], g["content_scope"], g["text"]), ("Reuters", "major_media", "headline_snippet", "Repo rates spike"))
        self.assertEqual(g["query_hint_card_ids"], ["FICC-GSD-02", "ECS-NSCC-09"])
        self.assertIn("hint only", g["query_hint_note"])
        self.assertNotIn("query_hint_card_ids", o)
        self.assertEqual((o["outlet"], o["source_tier"], o["content_scope"]), ("DTCC", "dtcc", "publisher_feed_summary"))

    def test_prompt_file_unchanged_by_hints(self):
        body, catalog, cards, version = L.prompt_parts(L.PROMPT)
        art = {"document_id": "g1", "title": "t", "url": "u", "published_date": "2026-11-03", "text": "t",
               "query_hint_card_ids": ["FICC-GSD-02"], "query_hint_note": L.HINT_NOTE}
        prompt, _ = L.render_prompt(body, catalog, [], art)
        self.assertIn('"query_hint_card_ids": ["FICC-GSD-02"]', prompt)       # travels inside the article JSON only
        self.assertEqual(prompt.replace(json.dumps(art, ensure_ascii=False), "{ARTICLE}").count("{ARTICLE}"), 1)


if __name__ == "__main__":
    unittest.main()
