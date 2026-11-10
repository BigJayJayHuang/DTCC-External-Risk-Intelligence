"""Recovery checks for retired RSS and independent weekly public reports."""
import contextlib
from datetime import date
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import db
import parsers
import update


CFTC=dict(id='cftc_press',name='CFTC',url='https://www.cftc.gov/PressRoom/PressReleases',kind='official_press_index',business_lines=['FICC','RDS'])


class PressIndexTests(unittest.TestCase):
    def test_publisher_time_and_publication_identity_preserved(self):
        body=b'''<table><tbody><tr><td><time datetime="2026-11-05T22:00:03Z">11/05/2026</time></td>
        <td><a href="/PressRoom/PressReleases/9323-26">Access requirements</a></td></tr></tbody></table>'''
        dataset,rows=parsers.parse(CFTC,body,date(2026,11,9),CFTC['url'])
        self.assertEqual(dataset,'news');self.assertEqual(len(rows),1)
        row=rows[0];self.assertEqual(row['publication_date'],'2026-11-05')
        self.assertEqual(row['published_at_utc'],'2026-11-05T22:00:03+00:00')
        self.assertEqual(row['document_id'],db.sha('https://www.cftc.gov/PressRoom/PressReleases/9323-26'))
        self.assertEqual(row['content_scope'],'headline_only');self.assertEqual(row['source_summary'],'')
        self.assertIsNone(row['event_time'])

    def test_no_publication_date_invented_from_collection_time(self):
        body=b'<table><tbody><tr><td><a href="/PressRoom/PressReleases/9323-26">Release</a></td></tr></tbody></table>'
        with self.assertRaisesRegex(ValueError,'publisher date'):
            parsers.parse(CFTC,body,date(2026,11,9),CFTC['url'])

    def test_official_link_host_required(self):
        body=b'<table><tbody><tr><td><time datetime="2026-11-05"/></td><td><a href="https://example.org/PressRoom/PressReleases/9323-26">Release</a></td></tr></tbody></table>'
        with self.assertRaisesRegex(ValueError,'host'):
            parsers.parse(CFTC,body,date(2026,11,9),CFTC['url'])


class RepositoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=self.root/'data.sqlite3'
        self.source=dict(id='rds_esma_table1',name='RDS',url='https://cms-prod.dtcc.com/PublicReports/reports/esma/ESMA_Table_1_OTC_Agg_{report_date}.csv',
                         kind='repository_weekly',enabled=True,refresh_hours=20,business_lines=[])
        (self.root/'schema.sql').write_text((db.ROOT/'schema.sql').read_text())
        (self.root/'sources.json').write_text(json.dumps([self.source]));(self.root/'businesses.json').write_text('[]')
        self.c=db.connect(self.path);self.c.execute("INSERT INTO datasets VALUES('rds_reports','test','report/row','public activity')");self.c.commit()

    def tearDown(self):self.c.close();self.tmp.cleanup()

    def response(self,day,status='downloaded',body=b'Asset,Amount\nRates,10\n'):
        return dict(url=self.source['url'].format(report_date=day),status=status,http_status=200 if status=='downloaded' else 404,
                    checked_at=db.now(),data=body,error='HTTP404' if status=='failed' else None)

    def run_update(self,responses):
        with patch.object(db,'ROOT',self.root),patch.object(update,'collect',return_value=responses),contextlib.redirect_stdout(io.StringIO()):
            return update.update(self.path,date(2026,11,9),force=True)

    def test_missing_latest_does_not_discard_available_earlier_reports(self):
        report=self.run_update([self.response('20261023'),self.response('20261030'),self.response('20261106','failed')])
        self.assertEqual(report['status'],'partial_failure')
        self.assertEqual(report['partially_successful_sources'],[self.source['id']])
        self.assertEqual(report['failed_sources'][0]['http_status'],404)
        self.assertEqual(self.c.execute('SELECT count(*) FROM records').fetchone()[0],4)
        state=self.c.execute('SELECT last_success,last_status FROM sources').fetchone()
        self.assertIsNotNone(state[0]);self.assertEqual(state[1],'partial_failure')
        self.assertEqual(len(report['source_results'][0]['requests']),3)

    def test_bad_one_period_does_not_discard_valid_other_period(self):
        report=self.run_update([self.response('20261030'),self.response('20261106',body=b'<html>not csv</html>')])
        self.assertEqual(report['status'],'partial_failure')
        self.assertEqual(self.c.execute('SELECT max(measurement_date) FROM records').fetchone()[0],'2026-10-30')
        self.assertEqual(self.c.execute('SELECT count(*) FROM records').fetchone()[0],2)

    def test_bom_prefixed_html_is_not_accepted_as_a_csv_report(self):
        with self.assertRaisesRegex(ValueError,'Not a repository CSV'):
            parsers.parse(self.source,b'\xef\xbb\xbf  <html>not csv</html>',date(2026,11,9),self.source['url'].format(report_date='20261106'))

    def test_latest_period_included_after_long_backlog(self):
        rid=db.start_run(self.c,'test')
        db.upsert(self.c,'rds_reports','older',dict(source_id=self.source['id'],report_date='2025-01-03',source_row=1),rid,self.source['id']);self.c.commit()
        planned=update.urls(self.c,self.source,date(2026,11,9))
        self.assertEqual(len(planned),8)
        self.assertIn('20261106',planned[-1])
        self.assertEqual(len(planned),len(set(planned)))

    def test_recent_missing_gap_retried_after_newer_period_succeeds(self):
        self.run_update([self.response('20261023','failed'),self.response('20261106')])
        planned=update.urls(self.c,self.source,date(2026,11,9))
        self.assertIn(self.source['url'].format(report_date='20261023'),planned)
        self.assertIn(self.source['url'].format(report_date='20261106'),planned)

    def test_initial_planner_checks_bounded_recent_published_periods(self):
        planned=update.urls(self.c,self.source,date(2026,11,9))
        self.assertEqual(len(planned),4)
        self.assertTrue(all(int(u[-12:-4])<=20261106 for u in planned))

    def test_304_reads_exact_report_period_even_when_latest_blob_is_newer(self):
        self.run_update([self.response('20261030',body=b'Asset,Amount\nRates,10\n'),
                         self.response('20261106',body=b'Asset,Amount\nRates,99\n')])
        cached=update.response_body(self.c,self.source['id'],dict(status='not_modified',url=self.source['url'].format(report_date='20261030')))
        self.assertEqual(cached,b'Asset,Amount\nRates,10\n')

    def test_304_cannot_borrow_another_report_period_body(self):
        self.run_update([self.response('20261030')])
        with self.assertRaisesRegex(ValueError,'exact-URL'):
            update.response_body(self.c,self.source['id'],dict(status='not_modified',url=self.source['url'].format(report_date='20261106')))

    def test_304_rejects_a_public_snapshot_without_bundled_raw_body(self):
        self.run_update([self.response('20261030')])
        with self.c:self.c.execute("UPDATE evidence_blobs SET compression='not_bundled',content=X''")
        with self.assertRaisesRegex(ValueError,'not bundled'):
            update.response_body(self.c,self.source['id'],dict(status='not_modified',url=self.source['url'].format(report_date='20261030')))


if __name__=='__main__':unittest.main()
