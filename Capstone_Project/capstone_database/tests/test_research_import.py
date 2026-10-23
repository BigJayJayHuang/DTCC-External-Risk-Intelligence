"""Research import checks: missingness, shared identity and atomicity."""
import json, tempfile, unittest
from pathlib import Path
import db
import import_chain_research as research

class ResearchImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.c=db.connect(Path(self.tmp.name)/'test.sqlite3')
        self.c.execute("INSERT INTO datasets VALUES('ofr_repo_observations','test','series/date','native units')")
        self.rid=db.start_run(self.c,'test')
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def row(self,value,stamp='2026-10-21T20:00:00+00:00'):
        return ('ofr_repo_observations','["GCF","2026-06-30"]',{'mnemonic':'GCF','observation_date':'2026-06-30','value':value},None,None,stamp,'public response')
    def test_repeat_import_keeps_one_record_and_version(self):
        with self.c:self.assertEqual(research.store_rows(self.c,self.rid,[self.row(None),self.row(None)]),{'new':1})
        with self.c:self.assertEqual(research.store_rows(self.c,self.rid,[self.row(None,'2026-10-22T00:00:00+00:00')]),{'unchanged':1})
        self.assertEqual(self.c.execute('SELECT count(*) FROM record_versions').fetchone()[0],1)
        self.assertIsNone(json.loads(self.c.execute('SELECT payload FROM records').fetchone()[0])['value'])
    def test_conflicting_duplicate_rolls_back_whole_batch(self):
        with self.assertRaisesRegex(ValueError,'Conflicting batch'):
            with self.c:research.store_rows(self.c,self.rid,[self.row(1),self.row(2)])
        self.assertEqual(self.c.execute('SELECT count(*) FROM records').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT count(*) FROM record_versions').fetchone()[0],0)
    def test_source_identity_does_not_depend_on_business_or_filename(self):
        self.assertEqual(research.source_id({'url':'https://example.org/data','name':'FICC'}),research.source_id({'url':'https://example.org/data','name':'ECS'}))
    def test_nonfinite_rejected_without_replacing_missing_with_zero(self):
        self.assertIsNone(research.number(''));self.assertIsNone(research.number(None));self.assertEqual(research.number('0'),0)
        with self.assertRaises(ValueError):research.number('NaN')
