"""Offline tests: Alpha Vantage source, its pre-filter and dedup, the non-US official filter, summary blanking and the
classifier's cached-summary input. No network, no AWS; the key used here is a fake test value."""
import csv, json, tempfile, unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from . import alpha_vantage_news as AV
from . import llm_classifier as C
from . import publisher_feeds as P
from . import weekly_news_run as W

FAKE_KEY = "TESTKEY123456789"
MONDAY = date(2026, 11, 2)


def article(title, url, summary, when="20261105T143000", source="Reuters", topics=("Financial Markets",)):
    return {"title": title, "url": url, "time_published": when, "summary": summary, "source": source, "source_domain": "www.reuters.com",
            "topics": [{"topic": t, "relevance_score": "0.9"} for t in topics], "overall_sentiment_score": 0.1,
            "overall_sentiment_label": "Neutral", "ticker_sentiment": []}


class FakeAPI:
    def __init__(self, feeds):
        self.feeds, self.calls = feeds, []

    def __call__(self, params, key):
        self.calls.append((dict(params), key))
        value = self.feeds[params["topics"]]
        return (200, json.dumps(value).encode()) if not isinstance(value, tuple) else value


class Collector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=C.PROJECT / "data"); self.root = Path(self.tmp.name)
        self.cache, self.out = self.root / "cache", self.root / "run"
        self.sleeps, self.t = [], [0.0]

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, api, **kw):
        def sleep(s): self.sleeps.append(s); self.t[0] += s
        return AV.collect(MONDAY, self.out, fetch=api, key=FAKE_KEY, cache=self.cache, sleep=sleep, clock=lambda: self.t[0],
                          now=datetime(2026, 11, 9, 22, tzinfo=timezone.utc), **kw)

    def files_text(self):
        return "".join(p.read_text(errors="ignore") for p in self.root.rglob("*") if p.is_file())

    def test_four_topic_requests_with_week_window_and_rate_limit(self):
        summary = "Treasury repo rates jumped as funding tightened across dealers."
        feed = {"feed": [article("Repo rates spike", "https://www.reuters.com/a", summary)]}
        api = FakeAPI({t: feed for t in AV.TOPICS})
        res = self.collect(api)
        self.assertEqual([c[0]["topics"] for c in api.calls], AV.TOPICS)
        p0 = api.calls[0][0]
        self.assertEqual((p0["function"], p0["time_from"], p0["time_to"], p0["sort"], p0["limit"]),
                         ("NEWS_SENTIMENT", "20261102T0000", "20261108T2359", "LATEST", "1000"))
        self.assertTrue(all(s >= AV.MIN_INTERVAL_SECONDS - 1e-9 for s in self.sleeps) and len(self.sleeps) == 3)   # <= 5 per minute
        self.assertEqual((res["stats"]["requests_this_run"], res["stats"]["requests_used_today_utc"], res["stats"]["unique_articles"]), (4, 4, 1))
        row = res["rows"][0]
        self.assertEqual((row["request_topics"], row["topics"]), (AV.TOPICS, ["Financial Markets"]))
        with (self.out / "alphavantage_items.csv").open() as f:
            item = next(csv.DictReader(f))
        self.assertNotIn("summary", item)                                   # repo file: hash only
        self.assertEqual(item["summary_sha256"], AV.sha(summary.encode()))
        self.assertNotIn(summary, (self.out / "alphavantage_items.csv").read_text() + (self.out / "alphavantage_requests.json").read_text())
        self.assertEqual((C.PROJECT / item["text_file"]).read_text(), summary)
        self.assertTrue(str(C.PROJECT / item["text_file"]).startswith(str(self.cache)))
        self.assertNotIn(FAKE_KEY, self.files_text())                      # key never written anywhere

    def test_message_instead_of_feed_stops_remaining_topics_and_scrubs_key(self):
        api = FakeAPI({t: {"Information": f"premium endpoint; your key {FAKE_KEY} is free"} for t in AV.TOPICS})
        res = self.collect(api)
        self.assertEqual(len(api.calls), 1)
        log = json.loads((self.out / "alphavantage_requests.json").read_text())["requests"]
        self.assertEqual([e["status"] for e in log], ["no_feed"] + ["not_requested"] * 3)
        self.assertIn("[key]", log[0]["message"])
        self.assertNotIn(FAKE_KEY, self.files_text())
        self.assertEqual((res["rows"], res["stats"]["requests_this_run"]), ([], 1))

    def test_daily_limit_is_enforced(self):
        self.cache.mkdir(parents=True); (self.cache / "usage.json").write_text(json.dumps({"2026-11-09": 24}))
        api = FakeAPI({t: {"feed": []} for t in AV.TOPICS})
        with self.assertRaises(SystemExit):
            self.collect(api)
        self.assertEqual(len(api.calls), 1)                                 # request 25 allowed, 26 refused

    def test_missing_key_stops(self):
        with mock.patch.dict("os.environ", {AV.KEY_ENV: ""}):
            with self.assertRaises(AV.KeyMissing):
                AV.api_key()


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=C.PROJECT / "data"); self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def av_csv(self, articles):
        api = FakeAPI({t: {"feed": articles} for t in AV.TOPICS})
        return AV.collect(MONDAY, self.root / "av", fetch=api, key=FAKE_KEY, cache=self.root / "cache", sleep=lambda s: None,
                          clock=lambda: 0.0, now=datetime(2026, 11, 9, tzinfo=timezone.utc))["items_csv"]

    def test_recall_filter_strict_broad_and_dropped(self):
        rows = [{"document_id": "1", "source_id": AV.SOURCE_ID, "title": "Hedge funds unwind basis trade", "summary": "Treasury basis trade unwinds", "url": "u1"},
                {"document_id": "2", "source_id": AV.SOURCE_ID, "title": "Stocks slide", "summary": "Equity selloff deepens with margin calls", "url": "u2"},
                {"document_id": "3", "source_id": AV.SOURCE_ID, "title": "New phone launched", "summary": "A gadget review", "url": "u3"}]
        kept, dropped = P.recall_filter(rows, P.G.load_queries())
        self.assertEqual([r["document_id"] for r in dropped], ["3"])
        self.assertTrue(all(r["keep_rule"] in ("all_terms_title_summary_match", "broad_keyword_match") for r in kept))

    def test_dedup_prefers_more_text_and_records_matches(self):
        g = {"document_id": "g", "source_id": "google_news_rss", "feed_id": "google_news_existing", "title": "Hedge Funds Dump Positions and Cut Staff as Selloff Deepens",
             "url": "https://news.google.com/x", "summary": "", "published_at_utc": "2026-11-06T02:10:00+00:00"}
        a = {"document_id": "a", "source_id": AV.SOURCE_ID, "feed_id": "alphavantage:finance", "title": "Hedge funds dump positions and cut staff as selloff deepens",
             "url": "https://www.wsj.com/x", "summary": "Long-short equity funds cut gross exposure.", "published_at_utc": "2026-11-06T03:00:00+00:00"}
        o = {"document_id": "o", "source_id": "sec_press", "feed_id": "official:sec_press", "title": "SEC approves 24-hour trading plan",
             "url": "https://www.sec.gov/p", "summary": "x" * 500, "published_at_utc": "2026-11-04T12:00:00+00:00"}
        a2 = {**a, "document_id": "a2", "title": "SEC approves 24 hour trading plan", "url": "https://www.reuters.com/y", "summary": "short"}
        rows, matches = P.av_dedupe([g, o, a, a2], 0.9)
        self.assertEqual(sorted(r["document_id"] for r in rows), ["a", "o"])
        self.assertEqual({(m["av_document_id"], m["other_document_id"], m["kept"]) for m in matches}, {("a", "g", "alphavantage"), ("a2", "o", "other")})

    def test_non_us_official_filter(self):
        self.assertTrue(P.us_link("ECB and the Federal Reserve swap lines"))
        self.assertTrue(P.us_link("FCA view on U.S. listings"))
        self.assertFalse(P.us_link("FCA warns about loans to contractors; thus us"))           # lower-case "us" is not the US
        self.assertFalse(P.us_link("ESMA consults on securities lending"))
        for uk in ("FCA and HM Treasury set out new rules", "His Majesty's Treasury consults", "His Majesty’s Treasury update",
                   "hm treasury response"):
            self.assertFalse(P.us_link(uk), uk)                                           # UK Treasury is not a US link
        self.assertTrue(P.us_link("HM Treasury and the US Treasury agree a swap"))       # a separate US term still counts
        self.assertTrue(P.us_link("Treasury yields rose"))

    def test_classifier_input_has_no_bodies_and_classifier_reads_cache(self):
        summary = "Treasury repo rates jumped as funding tightened across dealers and margin calls rose."
        items = self.av_csv([article("Repo rates spike as funding tightens", "https://www.reuters.com/repo", summary)])
        out = self.root / "feeds"
        with mock.patch.object(P, "fetch_fulltext", side_effect=AssertionError("Alpha Vantage pages are never fetched")), \
             mock.patch.object(P.Client, "allowed", return_value=False):
            P.main(["--out-dir", str(out), "--google", str(self.root / "none.csv"), "--alphavantage", str(items),
                    "--week-start", "2026-11-02", "--week-end", "2026-11-08"])
        with (out / "classifier_input.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([(r["source_id"], r["content_scope"], r["summary"]) for r in rows], [(AV.SOURCE_ID, "summary", "")])
        self.assertNotIn(summary, (out / "classifier_input.csv").read_text())
        arts, _ = C.load_news(out / "classifier_input.csv", MONDAY, date(2026, 11, 8), None)
        self.assertEqual((arts[0]["content_scope"], arts[0]["outlet"], arts[0]["source_tier"]), ("summary", "Reuters", "major_media"))
        self.assertTrue(arts[0]["text"].endswith(summary))

    def test_tampered_cache_is_refused(self):
        items = self.av_csv([article("Repo rates spike", "https://www.reuters.com/repo", "original summary about repo")])
        with items.open() as f:
            path = C.PROJECT / next(csv.DictReader(f))["text_file"]
        path.write_text("changed")
        with self.assertRaises(ValueError):
            AV.load_items(items)


class WeeklyRunKey(unittest.TestCase):
    def test_alphavantage_is_off_by_default_on_the_cli(self):
        seen = {}
        with mock.patch.object(W, "run_week", side_effect=lambda *a, **k: seen.update(k) or {}):
            W.main(["--week-start", "2026-11-02", "--cap", "1", "--dry-run"])
            self.assertIsNone(seen["collect_alphavantage"])
            W.main(["--week-start", "2026-11-02", "--cap", "1", "--dry-run", "--alphavantage"])
            self.assertIs(seen["collect_alphavantage"], AV.collect)

    def test_missing_key_stops_before_classification(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            official = root / "news.csv"; official.write_text("source_id,document_id,title,url,summary,publication_date\n")
            def google(config, queries, monday, out, **kw):
                out.mkdir(parents=True, exist_ok=True); return [], [], {}, []
            def missing(monday, out):
                raise AV.KeyMissing("ALPHAVANTAGE_API_KEY is not set")
            boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run"))
            res = W.run_week(MONDAY, W.Decimal("1"), today=date(2026, 11, 9), run_id="k", weekly_dir=root / "w", review_dir=root / "r",
                             context_path=root / "c.csv", collect_google=google, collect_feeds=boom, classify=boom,
                             official_news=official, collect_alphavantage=missing)
            self.assertEqual(res["status"], "stopped_alphavantage_key_missing")


if __name__ == "__main__":
    unittest.main()
