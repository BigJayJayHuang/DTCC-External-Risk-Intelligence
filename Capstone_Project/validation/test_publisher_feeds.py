"""Offline tests for validation/publisher_feeds.py and the classifier's full-text input path (no network)."""
import csv, json, tempfile, unittest
from unittest import mock
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
        self.assertEqual(P.keyword_hits("Banking services improve", index), {})    # word boundary: no 'bank' in 'Banking'
        self.assertEqual(P.keyword_hits("SOFR edges up", index), {"sofr": ["FICC-GSD-02"]})

    def test_phrase_components_and_plurals_are_retrieval_hints(self):
        queries = [('XE-SETTLEBANK', '"settlement bank"'), ('FICC-GSD-03', '"central clearing" Treasury SEC')]
        index = P.keyword_index(queries)
        self.assertEqual(index['settlement bank'], {'XE-SETTLEBANK'})
        self.assertEqual(index['settlement'], {'XE-SETTLEBANK'})
        self.assertEqual(P.keyword_hits('Daily settlements update', index), {'settlement': ['XE-SETTLEBANK']})
        self.assertEqual(P.keyword_hits('Clearing notice', index), {'clearing': ['FICC-GSD-03']})
        self.assertEqual(G.matched_queries('Clearing notice', queries), {})


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
            self.assertTrue(r["text_truncated"])
            self.assertEqual(r["original_text_words"], 1500)
            raw = (P.PROJECT / r["raw_file"]).read_bytes()
            self.assertEqual(P.sha(raw), r["raw_sha256"])
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

    def test_explicit_robots_access_denial_does_not_trigger_article_fetch(self):
        for status in (401,403,429):
            c = FakeClient({})
            c.get = lambda url, max_bytes=None, kind='page': (status,b'',url,'')
            self.assertFalse(c.allowed('https://example.com/article'))

    def test_hidden_script_inside_paragraph_is_not_evidence(self):
        text, _ = P.extract('<article><p>' + ('Visible article content ' * 40) + '<script>INJECTED SECRET SCRIPT</script></p></article>')
        self.assertNotIn('INJECTED', text)

    def test_oversize_article_is_not_called_full_text(self):
        with tempfile.TemporaryDirectory(dir=P.PROJECT / "data") as tmp:
            url = 'https://example.com/article'
            config = {**CONFIG, 'max_article_bytes': 40}
            client = FakeClient({url: (200, b'x' * 41, 'text/html')})
            self.assertEqual(P.fetch_fulltext({'url': url}, client, config, Path(tmp)), {'fulltext_status': 'article_byte_limit_exceeded'})

    def test_allowed_pdf_notice_is_extracted_and_hashed(self):
        with tempfile.TemporaryDirectory(dir=P.PROJECT / "data") as tmp:
            url = 'https://files.dtcc.com/notice.pdf'
            raw = b'%PDF fake public notice'
            text = ('Official notice on settlement capacity. ' * 20).encode()
            client = FakeClient({url: (200, raw, 'application/pdf')})
            with mock.patch.object(P.shutil, 'which', return_value='/bin/pdftotext'), mock.patch.object(P.subprocess, 'check_output', return_value=text):
                item = P.fetch_fulltext({'url': url}, client, CONFIG, Path(tmp))
            self.assertEqual(item['fulltext_status'], 'ok_pdf')
            self.assertFalse(item['text_truncated'])
            self.assertEqual(item['raw_sha256'], P.sha(raw))


class PublicURLGuard(unittest.TestCase):
    def test_public_https_urls_are_accepted_without_dns(self):
        for url in ('https://www.sec.gov/newsroom/a', 'https://files.dtcc.com/notice.pdf',
                    'https://www.federalreserve.gov:443/a', 'https://8.8.8.8/a'):
            self.assertTrue(P.public_https_url(url),url)

    def test_private_nonhttps_userinfo_and_ambiguous_hosts_are_rejected(self):
        urls=('http://www.sec.gov/a','https://user:password@www.sec.gov/a','https://www.sec.gov:8443/a',
              'https://127.0.0.1/a','https://10.0.0.1/a','https://169.254.169.254/latest/meta-data/',
              'https://[::1]/a','https://[fc00::1]/a','https://224.0.0.1/a','https://localhost/a','https://localhost./a',
              'https://metadata.google.internal/a','https://localhost.evil.com/a','https://127.1/a',
              'https://0177.0.0.1/a','https://0x7f.0.0.1/a','https://2130706433/a',
              'https://127.0.0.1.nip.io/a','https://127.0.0.1.sslip.io/a','https://www.sec.gov/\nprivate')
        for url in urls:self.assertFalse(P.public_https_url(url),url)

    def test_unsafe_url_never_reaches_robots_or_article_http(self):
        client=FakeClient({})
        with tempfile.TemporaryDirectory(dir=P.PROJECT/'data') as tmp:
            result=P.fetch_fulltext({'url':'http://169.254.169.254/latest/meta-data/'},client,CONFIG,Path(tmp))
        self.assertEqual(result['fulltext_status'],'unsafe_publisher_url')
        self.assertEqual(client.calls,[])

    def test_redirect_is_checked_before_follow_and_robots_is_not_bypassed(self):
        source=P.urllib.request.Request('https://www.sec.gov/original')
        seen=[];handler=P._SafeRedirect(lambda url:seen.append(url) or False)
        with self.assertRaises(P.urllib.error.HTTPError):
            handler.redirect_request(source,None,302,'Found',{},'https://127.0.0.1/private')
        self.assertEqual(seen,[])
        with self.assertRaises(P.urllib.error.HTTPError):
            handler.redirect_request(source,None,302,'Found',{},'https://www.sec.gov/blocked')
        self.assertEqual(seen,['https://www.sec.gov/blocked'])

    def test_safe_robots_redirect_does_not_recursively_fetch_robots(self):
        source=P.urllib.request.Request('https://sec.gov/robots.txt');source._capstone_kind='robots'
        handler=P._SafeRedirect(lambda url: self.fail('Recursive robots lookup'))
        target=handler.redirect_request(source,None,301,'Moved',{},'https://www.sec.gov/robots.txt')
        self.assertEqual(target.full_url,'https://www.sec.gov/robots.txt')
        self.assertEqual(target._capstone_kind,'robots')


class Dedupe(unittest.TestCase):
    def test_publisher_item_wins_over_google_twin(self):
        rows = [{"title": "Tech stocks log worst day since 2020 as carnage comes to the AI trade", "url": "https://news.google.com/rss/articles/X",
                 "source_id": "google_news_rss", "published_at_utc": "2026-11-05", "google_link": "https://news.google.com/rss/articles/X"},
                {"title": "Tech stocks log worst day since 2020 as carnage comes to the AI trade", "url": "https://www.marketwatch.com/story/a",
                 "source_id": P.SOURCE_ID, "published_at_utc": "2026-11-05"}]
        kept, dups = P.dedupe(rows, 0.9)
        self.assertEqual((len(kept), dups, kept[0]["url"], kept[0]["google_link"]),
                         (1, 1, "https://www.marketwatch.com/story/a", "https://news.google.com/rss/articles/X"))

    def test_merged_hint_provenance_survives(self):
        rows = [
            {'title': 'Clearing bank outage', 'url': 'https://bank.example/a', 'source_id': P.SOURCE_ID,
             'published_at_utc': '2026-11-05', 'matched_card_ids': 'XE-SETTLEBANK',
             'matched_queries': json.dumps({'XE-SETTLEBANK': ['clearing bank outage']})},
            {'title': 'Clearing bank outage', 'url': 'https://news.google.com/a', 'google_link': 'https://news.google.com/a',
             'source_id': 'google_news_rss', 'published_at_utc': '2026-11-05', 'matched_card_ids': 'XE-CYBER',
             'matched_queries': json.dumps({'XE-CYBER': ['bank outage']})},
        ]
        kept, n = P.dedupe(rows, .9)
        self.assertEqual(n, 1)
        self.assertEqual(kept[0]['matched_card_ids'], 'XE-CYBER|XE-SETTLEBANK')
        self.assertEqual(set(json.loads(kept[0]['matched_queries'])), {'XE-CYBER', 'XE-SETTLEBANK'})
        self.assertEqual(json.loads(kept[0]['duplicate_evidence'])[0]['url'], 'https://news.google.com/a')

    def test_repeated_title_in_different_weeks_is_not_dropped(self):
        rows = [{'title': 'Fed leaves policy rate unchanged', 'url': f'https://example.com/{n}', 'source_id': P.SOURCE_ID,
                 'published_at_utc': date} for n, date in enumerate(('2026-10-01', '2026-11-05'))]
        self.assertEqual(P.dedupe(rows, .9)[1], 0)

    def test_official_source_id_wins_but_retains_google_hints(self):
        rows = [{'title': 'DTC settlement rule amendment', 'url': 'https://files.dtcc.com/a.pdf', 'source_id': 'dtcc_notice_feed',
                 'published_at_utc': '2026-11-05', 'matched_card_ids': 'ECS-SET-01'},
                {'title': 'DTC settlement rule amendment', 'url': 'https://news.google.com/a', 'source_id': 'google_news_rss',
                 'published_at_utc': '2026-11-05', 'matched_card_ids': 'XE-SETTLEBANK'}]
        row = P.dedupe(rows, .9)[0][0]
        self.assertEqual(row['source_id'], 'dtcc_notice_feed')
        self.assertEqual(row['matched_card_ids'], 'ECS-SET-01|XE-SETTLEBANK')

    def test_distinct_gov_notice_ids_do_not_merge_by_title_but_same_url_does(self):
        rows=[{'document_id':f'gov{n}','title':f'GOV{n}-26',
               'url':f'https://files.dtcc.com/download/assets/GOV{n}-26/original',
               'source_id':'dtcc_notice_feed','publication_date':'2026-11-03'}
              for n in range(2281,2286)]
        same_url={**rows[0],'document_id':'same-url-copy','matched_card_ids':'XE-MEMBER'}
        kept,duplicates=P.dedupe(rows+[same_url],.9)
        self.assertEqual((len(kept),duplicates),(5,1))
        self.assertEqual({row['title'] for row in kept},{f'GOV{n}-26' for n in range(2281,2286)})
        merged=next(row for row in kept if row['document_id']=='gov2281')
        self.assertEqual(json.loads(merged['duplicate_evidence'])[0]['document_id'],'same-url-copy')
        self.assertEqual(merged['matched_card_ids'],'XE-MEMBER')

    def test_regulator_template_notices_with_distinct_urls_stay_separate(self):
        cboe='Self-Regulatory Organizations; Cboe {} Exchange, Inc.; Notice of Filing and Immediate Effectiveness of a Proposed Rule Change To Introduce Enhancements to the Missed Liquidity Report Offered as Part of the Cboe Timestamping Service'
        bank='Formations of, Acquisitions by, and Mergers of Bank Holding Companies'
        rows=[{'document_id':ident,'title':title,'source_id':source,'publication_date':when,'url':url}
              for ident,title,source,when,url in [
                  ('cboe-c2',cboe.format('C2'),'federal_register','2026-11-04','https://www.federalregister.gov/documents/2026-22459'),
                  ('cboe-edgx',cboe.format('EDGX'),'federal_register','2026-11-04','https://www.federalregister.gov/documents/2026-22461'),
                  ('bank-nov3',bank,'federal_register','2026-11-03','https://www.federalregister.gov/documents/2026-22398'),
                  ('bank-nov4',bank,'federal_register','2026-11-04','https://www.federalregister.gov/documents/2026-22502'),
                  ('bank-fed',bank,'fed_press','2026-11-04','https://www.federalreserve.gov/newsevents/bank-announcement.htm')]]
        kept,duplicates=P.dedupe(rows,.9)
        self.assertEqual((len(kept),duplicates),(5,0))
        self.assertEqual({row['url'] for row in kept},{row['url'] for row in rows})
        self.assertTrue(all(not row.get('duplicate_evidence') for row in kept))


class OfficialIntake(unittest.TestCase):
    def test_window_exclusions_are_not_irrelevance_and_never_use_ingestion(self):
        rows = [{'document_id':'inside','publication_date':'2026-11-05'},
                {'document_id':'outside','published_at_utc':'2026-10-05T00:00:00Z'},
                {'document_id':'unknown','last_seen':'2026-11-05T00:00:00Z'}]
        kept, excluded = P.window_candidates(rows,date(2026,11,2),date(2026,11,8))
        self.assertEqual([x['document_id'] for x in kept],['inside'])
        self.assertEqual([x['reason'] for x in excluded],['outside_requested_window','unknown_publication_date'])

    def test_official_snapshot_is_prefiltered_with_drop_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'news.csv'
            rows = [{'document_id': 'keep', 'source_id': 'dtcc_notice_feed', 'title': 'Treasury clearing deadline update',
                     'summary': 'Official clearing update.', 'publication_date': '2026-11-05', 'url': 'https://dtcc.com/a'},
                    {'document_id': 'drop', 'source_id': 'federal_register', 'title': 'Routine fishery quota allocation',
                     'summary': 'Administrative notice.', 'publication_date': '2026-11-05', 'url': 'https://federalregister.gov/b'},
                    {'document_id': 'old', 'source_id': 'fed_press', 'title': 'Treasury clearing deadline update',
                     'summary': 'Old item.', 'publication_date': '2026-10-05', 'url': 'https://federalreserve.gov/c'}]
            with path.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            kept, dropped, summary = P.official_rows(path, [('FICC-GSD-01', 'Treasury clearing')], date(2026,11,2), date(2026,11,8))
            self.assertEqual([x['document_id'] for x in kept], ['keep'])
            self.assertEqual(kept[0]['source_id'], 'dtcc_notice_feed')
            self.assertEqual(kept[0]['source_tier'], 'dtcc')
            self.assertEqual(kept[0]['keep_rule'], 'all_terms_official_title_summary_match')
            self.assertEqual((summary['kept_strict_all_terms'],summary['kept_broad_keyword_fallback']),(1,0))
            self.assertEqual([x['document_id'] for x in dropped], ['drop'])
            self.assertEqual(summary['input_sha256'], P.sha(path.read_bytes()))
            self.assertEqual([x['document_id'] for x in summary['scope_exclusions']],['old'])

    def test_actual_official_near_misses_get_broad_hints_without_acceptance(self):
        # Actual Nov2–8 export titles: a strict Google stress-style query misses
        # them, but they warrant review as regulatory/business context.
        titles = [
            ('nscc-etf','federal_register','Self-Regulatory Organizations; National Securities Clearing Corporation; Notice of Filing and Immediate Effectiveness of a Proposed Rule Change To Enhance Automated Reasonability Checks for the Submission of ETF Creation and Exemption Transactions'),
            ('rule17ad22','federal_register','Order Granting Exemptive Relief, Pursuant to Sections 17A and 36(a) of the Securities Exchange Act of 1934, From the Definition of an “Eligible Secondary Market Transaction” in Rule 17ad-22(a)'),
            ('cftc-settlement','cftc_press','CFTC Staff Addresses Use of Trust Companies for Daily Settlements'),
            ('routine','federal_register','Routine fishery quota allocation'),
        ]
        rows = [dict(document_id=ident,source_id=source,title=title,summary='',publication_date='2026-11-05',
                     url='https://www.cftc.gov/'+ident if source=='cftc_press' else 'https://www.federalregister.gov/'+ident)
                for ident,source,title in titles]
        queries = G.load_queries()
        strict,strict_dropped=G.prefilter_official(rows,queries,{r['source_id'] for r in rows},date(2026,11,2),date(2026,11,8))
        self.assertEqual(strict,[])
        self.assertEqual(len(strict_dropped),4)   # historical caller keeps strict behavior
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'news.csv';G.write_csv(path,rows,list(rows[0]))
            kept,dropped,summary=P.official_rows(path,queries,date(2026,11,2),date(2026,11,8))
        by_id={row['document_id']:row for row in kept}
        self.assertEqual(set(by_id),{'nscc-etf','rule17ad22','cftc-settlement'})
        self.assertEqual([row['document_id'] for row in dropped],['routine'])
        self.assertEqual((summary['kept_strict_all_terms'],summary['kept_broad_keyword_fallback']),(0,3))
        for row in kept:
            self.assertEqual(row['keep_rule'],'broad_official_keyword_match')
            self.assertEqual(row['feed_id'],'official:'+row['source_id'])
            self.assertTrue(json.loads(row['matched_keywords']))
            self.assertTrue(json.loads(row['matched_queries']))
            self.assertTrue(row['matched_card_ids'])
            self.assertNotIn('accepted',row)
            self.assertNotIn('risk_score',row)
        self.assertEqual(by_id['cftc-settlement']['source_tier'],'regulator')
        self.assertIn('settlement',json.loads(by_id['cftc-settlement']['matched_keywords']))
        self.assertIn('market',json.loads(by_id['rule17ad22']['matched_keywords']))
        self.assertIn('clearing',json.loads(by_id['nscc-etf']['matched_keywords']))

    def test_existing_strict_keep_rule_survives(self):
        row={'document_id':'strict','source_id':'fed_press','title':'Treasury clearing deadline update',
             'summary':'','publication_date':'2026-11-05','url':'https://www.federalreserve.gov/a',
             'keep_rule':'existing_strict_all_terms'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'news.csv';G.write_csv(path,[row],list(row))
            kept,_,summary=P.official_rows(path,[('FICC-GSD-03','Treasury clearing')],date(2026,11,2),date(2026,11,8))
        self.assertEqual(kept[0]['keep_rule'],'existing_strict_all_terms')
        self.assertEqual(summary['kept_broad_keyword_fallback'],0)

    def test_google_summary_and_resolved_article_are_enriched(self):
        with tempfile.TemporaryDirectory(dir=P.PROJECT / 'data') as tmp:
            root = Path(tmp);google = root / 'google.csv';out = root / 'out'
            row = {'document_id': 'g1', 'title': 'Treasury clearing update', 'url': 'https://example.com/story',
                   'publisher_url': 'https://example.com/story', 'google_link': 'https://news.google.com/a',
                   'source_id': 'google_news_rss', 'published_at_utc': '2026-11-05T12:00:00Z',
                   'summary': 'An actual feed summary.', 'matched_card_ids': 'FICC-GSD-01'}
            G.write_csv(google, [row], list(row))
            seen = []
            def enrich(item, *args):
                seen.append(item.copy());return {'fulltext_status':'robots_disallowed'}
            with mock.patch.object(P, 'CONFIG', root / 'config.json'):
                (root / 'config.json').write_text(json.dumps({**CONFIG,'feeds':[]}))
                with mock.patch.object(P, 'fetch_fulltext', side_effect=enrich):
                    summary = P.main(['--google',str(google),'--out-dir',str(out)])
            self.assertEqual(seen[0]['summary'], 'An actual feed summary.')
            self.assertEqual(seen[0]['publisher_url'], 'https://example.com/story')
            with (out/'classifier_input.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual((rows[0]['summary'],rows[0]['content_scope']),('An actual feed summary.','summary'))
            self.assertEqual(summary['scope_totals'], {'summary':1})

    def test_week_filter_precedes_article_requests(self):
        with tempfile.TemporaryDirectory(dir=P.PROJECT / 'data') as tmp:
            root=Path(tmp);google=root/'google.csv';out=root/'out'
            rows=[{'document_id':ident,'title':'Treasury clearing update','url':'https://example.com/'+ident,
                   'source_id':'google_news_rss','published_at_utc':when,'summary':'Public feed summary.'}
                  for ident,when in [('inside','2026-11-05T12:00:00Z'),('outside','2026-10-05T12:00:00Z'),('unknown','')]]
            G.write_csv(google,rows,list(rows[0]))
            (root/'config.json').write_text(json.dumps({**CONFIG,'feeds':[]}))
            requested=[]
            with mock.patch.object(P,'CONFIG',root/'config.json'),mock.patch.object(P,'fetch_fulltext',side_effect=lambda row,*args: requested.append(row['document_id']) or {'fulltext_status':'robots_disallowed'}):
                summary=P.main(['--google',str(google),'--out-dir',str(out),'--week-start','2026-11-02','--week-end','2026-11-08'])
            self.assertEqual(requested,['inside'])
            with (out/'outside_window.csv').open() as f:exclusions=list(csv.DictReader(f))
            self.assertEqual({r['document_id'] for r in exclusions},{'outside','unknown'})
            self.assertEqual(summary['window_exclusions'],{'outside_requested_window':1,'unknown_publication_date':1})


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
