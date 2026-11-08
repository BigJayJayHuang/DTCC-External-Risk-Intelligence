"""Offline tests for validation/publisher_feeds.py and the classifier's full-text input path (no network)."""
import csv, json, tempfile, unittest
from datetime import date
from pathlib import Path

from . import google_news as G
from . import llm_classifier as C
from . import publisher_feeds as P

CONFIG = json.loads(P.CONFIG.read_text())
WORDS = " ".join(f"word{n}" for n in range(1500))

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Tech stocks log worst day since 2020</title><link>https://www.marketwatch.com/story/a</link>
<description>&lt;p&gt;The Nasdaq fell 4% as the AI trade unwound.&lt;/p&gt;</description><pubDate>Thu, 05 Nov 2026 21:00:00 GMT</pubDate></item>
<item><title>Recipe of the week</title><link>https://www.marketwatch.com/story/b</link><description>Soup.</description><pubDate>Thu, 05 Nov 2026 22:00:00 GMT</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fed statement</title>
<link href="https://www.federalreserve.gov/x.htm"/><summary>Rates unchanged.</summary><updated>2026-11-05T18:00:00Z</updated></entry></feed>"""


class FakeClient(P.Client):
    def __init__(self, pages, robots=None):
        super().__init__(CONFIG, limiter=G.RateLimiter(0, clock=lambda: 0, sleep=lambda s: None))
        self.pages, self.robots_txt, self.calls = pages, robots or {}, []

    def get(self, url, max_bytes=None, kind="page"):
        self.calls.append((kind, url))
        if url.endswith("/robots.txt"):
            host = url.split("/")[2]
            return (200, self.robots_txt[host].encode(), url, "text/plain") if host in self.robots_txt else (404, b"", url, "")
        status, body, ctype = self.pages.get(url, (404, b"", ""))
        return status, body, url, ctype


class Feeds(unittest.TestCase):
    def test_rss_and_atom(self):
        items = P.parse_feed(RSS)
        self.assertEqual([i["title"] for i in items], ["Tech stocks log worst day since 2020", "Recipe of the week"])
        self.assertEqual(items[0]["summary"], "The Nasdaq fell 4% as the AI trade unwound.")
        self.assertEqual(items[0]["published"].isoformat(), "2026-11-05T21:00:00+00:00")
        atom = P.parse_feed(ATOM)[0]
        self.assertEqual((atom["url"], atom["summary"]), ("https://www.federalreserve.gov/x.htm", "Rates unchanged."))

    def test_config_honest_and_rate_limited(self):
        self.assertNotIn("Mozilla", CONFIG["user_agent"]); self.assertNotIn("@", CONFIG["user_agent"])
        self.assertEqual(CONFIG["min_request_interval_seconds"], 2.0)
        self.assertEqual({f["outlet"] for f in CONFIG["feeds"]}, {"CNBC", "MarketWatch", "Yahoo Finance", "Nasdaq", "Federal Reserve", "SEC"})


class Prefilter(unittest.TestCase):
    def test_single_keyword_word_boundary(self):
        index = P.keyword_index([("ECS-NSCC-LIQ", '"stock market selloff"'), ("XE-CYBER", "cyberattack bank"), ("FICC-GSD-02", "SOFR spike")])
        self.assertEqual(index["bank"], {"XE-CYBER"})
        hits = P.keyword_hits("Bank hit by cyberattack", index)
        self.assertEqual(hits, {"cyberattack": ["XE-CYBER"], "bank": ["XE-CYBER"]})
        self.assertEqual(P.keyword_hits("Banking stocks rise", index), {})          # word boundary: no 'bank' in 'Banking'
        self.assertEqual(P.keyword_hits("SOFR edges up", index), {"sofr": ["FICC-GSD-02"]})


class FullText(unittest.TestCase):
    def page(self, body_json=None, paras=None, free=True):
        ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": "h"}
        if body_json: ld["articleBody"] = body_json
        if not free: ld["isAccessibleForFree"] = False
        p = "".join(f"<p>{x}</p>" for x in (paras or []))
        return f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body><nav><p>{"menu " * 20}</p></nav><article>{p}</article></body></html>'

    def test_extract_jsonld_paragraphs_and_paywall(self):
        self.assertEqual(P.extract(self.page(body_json=WORDS))[1], "ok_jsonld")
        text, how = P.extract(self.page(paras=[WORDS[:400], WORDS[400:900]]))
        self.assertEqual(how, "ok_paragraphs"); self.assertNotIn("menu", text)
        self.assertEqual(P.extract(self.page(body_json=WORDS, free=False)), ("", "paywalled"))
        self.assertEqual(P.extract("<html><p>short</p></html>"), ("", "extract_failed"))

    def test_fetch_truncates_hashes_and_respects_robots(self):
        with tempfile.TemporaryDirectory(dir=P.PROJECT / "data") as tmp:
            cache = Path(tmp)
            url = "https://www.cnbc.com/2026/11/05/a.html"
            client = FakeClient({url: (200, self.page(body_json=WORDS).encode(), "text/html")})
            r = P.fetch_fulltext({"url": url}, client, CONFIG, cache)
            self.assertEqual((r["fulltext_status"], r["text_words"]), ("ok_jsonld", 1001))     # 1,000 words + ellipsis
            saved = (P.PROJECT / r["text_file"]).read_text()
            self.assertEqual(P.sha(saved.encode()), r["text_sha256"])
            blocked = FakeClient({url: (200, b"x", "text/html")}, robots={"www.cnbc.com": "User-agent: *\nDisallow: /2026/\n"})
            self.assertEqual(P.fetch_fulltext({"url": url}, blocked, CONFIG, cache)["fulltext_status"], "robots_disallowed")
            self.assertNotIn(("article", url), blocked.calls)
            pay = FakeClient({url: (402, b"", "")})
            self.assertTrue(P.fetch_fulltext({"url": url}, pay, CONFIG, cache)["fulltext_status"].startswith("paywalled_or_forbidden"))
            self.assertEqual(P.fetch_fulltext({"url": "https://news.google.com/rss/articles/X"}, client, CONFIG, cache)["fulltext_status"], "no_publisher_url")

    def test_robots_5xx_disallows(self):
        c = FakeClient({})
        c.get = lambda url, max_bytes=None, kind="page": (503, b"", url, "")
        self.assertFalse(c.allowed("https://example.com/a"))


class Dedupe(unittest.TestCase):
    def test_publisher_item_wins_over_google_twin(self):
        rows = [{"title": "Tech stocks log worst day since 2020 as carnage comes to the AI trade", "url": "https://news.google.com/rss/articles/X",
                 "source_id": "google_news_rss", "published_at_utc": "2026-11-05", "google_link": "https://news.google.com/rss/articles/X"},
                {"title": "Tech stocks log worst day since 2020 as carnage comes to the AI trade", "url": "https://www.marketwatch.com/story/a",
                 "source_id": P.SOURCE_ID, "published_at_utc": "2026-11-05"}]
        kept, dups = P.dedupe(rows, 0.9)
        self.assertEqual((len(kept), dups, kept[0]["url"], kept[0]["google_link"]),
                         (1, 1, "https://www.marketwatch.com/story/a", "https://news.google.com/rss/articles/X"))


class ClassifierInput(unittest.TestCase):
    def write(self, root, rows):
        path = root / "in.csv"
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=P.FIELDS); w.writeheader(); w.writerows(rows)
        return path

    def test_full_text_summary_headline_scopes(self):
        with tempfile.TemporaryDirectory(dir=P.PROJECT / "data") as tmp:
            root = Path(tmp)
            body = "Full article body. " * 30
            (root / "t.txt").write_text(body)
            rel = str((root / "t.txt").relative_to(P.PROJECT))
            base = {"published_at_utc": "2026-11-05T21:00:00+00:00", "source_id": P.SOURCE_ID, "outlet": "MarketWatch", "source_tier": "major_media"}
            path = self.write(root, [
                {**base, "document_id": "f", "title": "T1", "url": "u1", "summary": "S1", "content_scope": "full_text", "text_file": rel, "text_sha256": P.sha(body.encode())},
                {**base, "document_id": "s", "title": "T2", "url": "u2", "summary": "S2", "content_scope": "summary"},
                {**base, "document_id": "h", "title": "T3", "url": "u3", "summary": "", "content_scope": "headline_only"}])
            arts = {a["document_id"]: a for a in C.load_news(path, date(2026, 11, 1), date(2026, 11, 8), None)[0]}
            self.assertEqual((arts["f"]["content_scope"], arts["f"]["text"]), ("full_text", "T1\n\n" + body))
            self.assertEqual((arts["s"]["content_scope"], arts["s"]["text"]), ("summary", "T2\n\nS2"))
            self.assertEqual((arts["h"]["content_scope"], arts["h"]["text"]), ("headline_only", "T3"))
            self.assertEqual((arts["f"]["outlet"], arts["f"]["source_tier"]), ("MarketWatch", "major_media"))
            bad = self.write(root, [{**base, "document_id": "f", "title": "T1", "url": "u1", "summary": "", "content_scope": "full_text",
                                     "text_file": rel, "text_sha256": "0" * 64}])
            with self.assertRaises(ValueError):
                C.load_news(bad, date(2026, 11, 1), date(2026, 11, 8), None)

    def test_fulltext_files_are_git_ignored(self):
        import subprocess
        for path in ["Capstone_Project/data/events/fulltext_cache/a.txt", "Capstone_Project/data/events/classifier_runs/r/articles/k.fulltext.txt"]:
            self.assertEqual(subprocess.run(["git", "check-ignore", "-q", path], cwd=P.PROJECT.parent).returncode, 0, path)


if __name__ == "__main__":
    unittest.main()
