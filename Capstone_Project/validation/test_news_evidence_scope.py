"""Protect evidence scope and local paths before any article reaches a model."""
import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import llm_classifier as C


class ArticleEvidenceScope(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.body=self.root/'data/events/fulltext_cache/article.txt'
        self.body.parent.mkdir(parents=True)
        self.body.write_text('Public article evidence with a limited excerpt.')
        self.path=self.root/'input.csv'
    def tearDown(self):self.tmp.cleanup()
    def row(self,**kw):
        row=dict(document_id='fixture',title='Official fixture',url='https://www.cftc.gov/fixture',
                 publication_date='2026-11-06',published_at_utc='',summary='Public feed summary.',source_id='cftc_press',
                 content_scope='article_excerpt',text_file=str(self.body.relative_to(self.root)),text_sha256=C.sha(self.body.read_bytes()))
        return dict(row,**kw)
    def load(self,row):
        with self.path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
        with patch.object(C,'PROJECT',self.root):return C.load_news(self.path,date(2026,11,2),date(2026,11,8),None)
    def test_excerpt_keeps_scope_body_and_source_authority(self):
        rows,_=self.load(self.row())
        self.assertEqual(rows[0]['content_scope'],'article_excerpt')
        self.assertIn(self.body.read_text(),rows[0]['text'])
        self.assertEqual((rows[0]['outlet'],rows[0]['source_tier']),('CFTC','regulator'))
    def test_changed_evidence_is_rejected(self):
        row=self.row();self.body.write_text('This is different evidence.')
        with self.assertRaisesRegex(ValueError,'sha256'):self.load(row)
    def test_external_local_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            p=Path(external)/'private.txt';p.write_text('Must not reach model.')
            with self.assertRaisesRegex(ValueError,'inside the project'):
                self.load(self.row(text_file=str(p),text_sha256=C.sha(p.read_bytes())))
    def test_unresolved_google_headline_remains_a_headline(self):
        rows,_=self.load(self.row(source_id='google_news_rss',content_scope='headline_only',outlet='Fixture outlet',source_tier='other'))
        self.assertEqual(rows[0]['text'],'Official fixture')
        self.assertEqual(rows[0]['content_scope'],'headline_only')

if __name__=='__main__':unittest.main()
