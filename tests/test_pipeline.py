import contextlib, datetime, io, json, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import db, parsers, update
from query import readonly

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite3'
        self.c=db.connect(self.path)
        self.c.execute("INSERT INTO datasets VALUES('market_observations','test','series/date','public proxy')")
        self.rid=db.start_run(self.c,'test')
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def put(self,value,stamp='2026-10-14T00:00:00+00:00'):
        return db.upsert(self.c,'market_observations','SOFR:2026-10-13',{'series_id':'SOFR','observation_date':'2026-10-13','value':value,'collected_at_utc':stamp},self.rid)
    def test_idempotency_and_reversions(self):
        self.assertEqual(self.put(4),'new');self.assertEqual(self.put(4,'2026-10-15T00:00:00+00:00'),'unchanged')
        self.assertEqual(self.put(5),'revised');self.assertEqual(self.put(4),'revised')
        self.assertEqual(self.c.execute('SELECT count(*) FROM records').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM record_versions').fetchone()[0],3)
    def test_failed_transaction_retains_previous_value(self):
        self.put(4);self.c.commit()
        with self.assertRaises(ValueError):
            with self.c:self.put(5);raise ValueError('source schema changed')
        self.assertEqual(json.loads(self.c.execute('SELECT payload FROM records').fetchone()[0])['value'],4)
    def test_null_is_not_zero(self):
        self.put(None);self.c.commit()
        self.assertIsNone(self.c.execute('SELECT value FROM market_daily').fetchone()[0])
    def test_readonly_query_rejects_write(self):
        self.c.commit()
        with readonly(self.path) as reader:
            with self.assertRaises(sqlite3.OperationalError):reader.execute('DELETE FROM records')
    def test_snapshot_restores_and_evidence_verifies(self):
        h=db.put_blob(self.c,b'public raw response');self.put(4);self.c.commit()
        self.assertEqual(db.blob(self.c,h),b'public raw response')
        db.snapshot(self.c,self.path,public=False);self.c.close();self.path.unlink();db.restore(self.path)
        self.c=db.connect(self.path)
        self.assertEqual(self.c.execute('SELECT count(*) FROM records').fetchone()[0],1)
    def test_shared_snapshot_excludes_raw_bodies(self):
        h=db.put_blob(self.c,b'public raw response');self.put(4);self.c.commit()
        db.snapshot(self.c,self.path);self.c.close();self.path.unlink();db.restore(self.path)
        self.c=db.connect(self.path)
        self.assertEqual(self.c.execute('SELECT compression FROM evidence_blobs WHERE sha256=?',(h,)).fetchone()[0],'not_bundled')
        self.assertEqual(db.put_blob(self.c,b'public raw response'),h)
        self.assertEqual(db.blob(self.c,h),b'public raw response')
    def test_overlapping_writers_rejected(self):
        with db.writer_lock(self.path):
            with self.assertRaises(RuntimeError):
                with db.writer_lock(self.path):pass

class ParserTests(unittest.TestCase):
    as_of=datetime.date(2026,10,14)
    def test_fred_missing_and_future_dates(self):
        s={'id':'fred_SOFR','kind':'market_series','series_id':'SOFR','frequency':'daily','units':'percent'}
        dataset,rows=parsers.parse(s,b'observation_date,SOFR\n2026-10-13,.\n2026-10-14,4.1\n2026-10-15,4.2\n',self.as_of,'https://fred.stlouisfed.org')
        self.assertEqual(len(rows),2);self.assertIsNone(rows[0]['value']);self.assertEqual(rows[1]['value'],4.1)
    def test_ficc_trailer_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'trailer'):
            parsers.parse({'id':'fails','kind':'ficc_daily_series'},b'Date,Amount\n10/13/2026,3\nTRAILER,2\n',self.as_of,'https://cms-prod.dtcc.com')
    def test_date_only_is_not_invented_utc_time(self):
        s={'id':'x','name':'Test','url':'https://example.org','business_lines':['FICC']}
        row=parsers.news_record(s,'Title','/story','Summary','2026-10-14')
        self.assertIsNone(row['published_at_utc']);self.assertEqual(row['publication_date'],'2026-10-14')
    def test_duplicate_notice_variants_preserved(self):
        s={'id':'x','name':'Test','url':'https://example.org','business_lines':['FICC']}
        a=parsers.news_record(s,'24700','/same','First','2026-10-14')
        b=parsers.news_record(s,'B24700','/same','Second','2026-10-14')
        rows,n=parsers.deduplicate('news',[a,b]);self.assertEqual(n,1)
        self.assertEqual(len(rows[0]['publisher_feed_variants']),2)
    def test_identical_declarations_collapsed_but_conflicts_rejected(self):
        a={'source_id':'fema','event_id':'fema:1:NY:DR','observation_date':'2026-10-14'}
        rows,n=parsers.deduplicate('external_events',[a,dict(a)])
        self.assertEqual((len(rows),n),(1,1))
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            parsers.deduplicate('external_events',[a,dict(a,observation_date='2026-10-13')])
    def test_shared_active_urls_unique(self):
        sources=json.loads((db.ROOT/'sources.json').read_text());active=[x['url'] for x in sources if x['enabled']]
        self.assertEqual(len(active),len(set(active)))
        self.assertFalse(any(x.get('series_id') in ['WIMFSL','WRMFSL'] and x['enabled'] for x in sources))

class UpdateFailureTests(unittest.TestCase):
    def test_multi_page_failure_rolls_back_all_rows_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'test.sqlite3'
            source={'id':'fred_SOFR','name':'SOFR','kind':'market_series','series_id':'SOFR','url':'https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR','units':'percent','frequency':'daily','enabled':True,'refresh_hours':20,'business_lines':[]}
            (root/'sources.json').write_text(json.dumps([source]));(root/'businesses.json').write_text('[]')
            (root/'schema.sql').write_text((db.ROOT/'schema.sql').read_text())
            c=db.connect(path);c.execute("INSERT INTO datasets VALUES('market_observations','test','series/date','public proxy')");c.commit();c.close()
            responses=[{'url':source['url'],'status':'downloaded','http_status':200,'checked_at':db.now(),'data':b'observation_date,SOFR\n2026-10-13,4.1\n'},
                       {'url':source['url']+'&page=2','status':'downloaded','http_status':200,'checked_at':db.now(),'data':b'wrong,columns\n'}]
            with patch.object(db,'ROOT',root),patch.object(update,'collect',return_value=responses),contextlib.redirect_stdout(io.StringIO()):
                report=update.update(path,datetime.date(2026,10,14),force=True)
            self.assertEqual(report['status'],'partial_failure')
            with sqlite3.connect(path) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],0)
                self.assertIsNone(c.execute('SELECT last_success FROM sources').fetchone()[0])

if __name__=='__main__':unittest.main()
