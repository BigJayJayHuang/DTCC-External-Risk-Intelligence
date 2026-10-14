"""离线合成用例，验证数据正确性；不会访问互联网。"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect

SOURCE = {"id": "test", "name": "Synthetic test feed", "feed_url": "https://example.org/feed"}
STAMP = "2026-09-25T12:00:00+00:00"
RSS = b'''<rss version="2.0"><channel><item><title>Treasury repo update</title>
<link>https://example.org/article?id=1&amp;utm_source=test</link>
<description><![CDATA[<p>Public <b>repo</b> announcement.</p><script>bad()</script>]]></description>
<pubDate>Thu, 24 Sep 2026 14:00:00 -0400</pubDate></item></channel></rss>'''


def document():
    return collect.parse_feed(RSS, SOURCE, STAMP, "raw/test.xml")[0][0]


class CollectionTests(unittest.TestCase):
    def test_clean_parse_provenance_and_timezone(self):
        d = document()
        self.assertEqual(d["published_at_utc"], "2026-09-24T18:00:00+00:00")
        self.assertEqual(d["source_summary"], "Public repo announcement.")
        self.assertEqual(d["url"], "https://example.org/article?id=1")
        self.assertEqual(d["raw_file"], "raw/test.xml")
        self.assertEqual(d["business_lines_candidate"], ["FICC"])
        self.assertIsNone(d["impact_analysis"])

    def test_missing_or_naive_date_is_not_invented(self):
        for raw in ["", "bad-date", "2026-09-24"]:
            value, flag = collect.normalize_date(raw)
            self.assertIsNone(value)
            self.assertIsNotNone(flag)

    def test_atom_published_is_distinct_from_updated(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Sample</title><link href="/item"/><updated>2026-09-24T10:00:00Z</updated>
        <summary>Excerpt</summary></entry></feed>'''
        d = collect.parse_feed(atom, SOURCE, STAMP, "x")[0][0]
        self.assertIsNone(d["published_at_utc"])
        self.assertEqual(d["source_updated_at_raw"], "2026-09-24T10:00:00Z")

    def test_http_200_html_error_is_not_an_empty_feed(self):
        with self.assertRaises(ValueError):
            collect.parse_feed(b"<html><body>Access denied</body></html>", SOURCE, STAMP, "x")

    def test_xml_entities_and_unsafe_link_rejected(self):
        with self.assertRaises(ValueError):
            collect.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss/>', SOURCE, STAMP, "x")
        payload = RSS.replace(b"https://example.org/article?id=1&amp;utm_source=test", b"javascript:alert(1)")
        records, stats = collect.parse_feed(payload, SOURCE, STAMP, "x")
        self.assertEqual(records, [])
        self.assertEqual(len(stats["rejected_entries"]), 1)

    def test_keyword_boundaries_and_review_required(self):
        self.assertEqual(collect.candidate_tags("Annual report", "")[0], [])
        self.assertEqual(collect.candidate_tags("IPOs and blockchain", "")[0], ["Asset Services", "DAS", "DDA"])
        self.assertEqual(document()["review_status"], "unreviewed")

    def test_url_dedup_keeps_meaningful_queries(self):
        self.assertNotEqual(collect.normalize_url("/a?id=1", SOURCE["feed_url"]),
                            collect.normalize_url("/a?id=2", SOURCE["feed_url"]))
        self.assertEqual(collect.normalize_url("/a?utm_source=x#section", SOURCE["feed_url"]), "https://example.org/a")

    def test_repeated_collection_and_revision_history(self):
        con = collect.open_database(":memory:")
        with con:
            first = collect.upsert(con, document())
            again = dict(document(), collected_at_utc="2026-09-26T12:00:00+00:00", raw_file="raw/new.xml")
            second = collect.upsert(con, again)
            changed = collect.parse_feed(RSS.replace(b"announcement.", b"announcement corrected."), SOURCE, STAMP, "x")[0][0]
            third = collect.upsert(con, changed)
        self.assertEqual([first["change_status"], second["change_status"], third["change_status"]], ["new", "unchanged", "updated"])
        self.assertEqual(second["first_seen_at_utc"], STAMP)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM versions").fetchone()[0], 2)
        original = json.loads(con.execute("SELECT payload FROM versions WHERE revision=1").fetchone()[0])
        self.assertEqual(original["source_summary"], "Public repo announcement.")
        con.close()

    def test_partial_failure_and_two_runs_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "sources.json"
            config.write_text(json.dumps([SOURCE, dict(SOURCE, id="blocked")]))
            def fake_fetch(source, *_):
                if source["id"] == "blocked":
                    raise OSError("Synthetic network failure")
                return RSS, {"http_status": 200}
            args = ["--sources", str(config), "--output", str(root / "output")]
            with patch.object(collect, "fetch", side_effect=fake_fetch), patch.object(collect.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(collect.main(args), 2)
                self.assertEqual(collect.main(args), 2)
            report = json.loads((root / "output/latest_run_report.json").read_text())
            self.assertEqual(report["totals"], {"new": 0, "updated": 0, "unchanged": 1})
            self.assertEqual(report["sources"][1]["status"], "error")
            self.assertEqual(report["total_stored_documents"], 1)
            self.assertEqual(len(list((root / "output/runs").glob("*/raw/test.xml"))), 2)


if __name__ == "__main__":
    unittest.main()
