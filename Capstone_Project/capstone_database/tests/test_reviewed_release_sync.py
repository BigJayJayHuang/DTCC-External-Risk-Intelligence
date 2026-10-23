"""Committed research must survive a newer release restore without replaying old data."""
from pathlib import Path
from unittest.mock import patch
import json,tempfile,unittest
import db,github_release

class ReviewedReleaseSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.path=self.root/'data/test.sqlite3';self.bundle=self.root/'reviewed_batch';self.logs=self.root/'logs'
        names=['fetch_manifest.json','input_manifest.json','data/treasury_auction_observations.csv','results/auction_filter_audit.json','data/mmf_repo_flow_million_usd.csv','data/mutual_fund_net_issuance_million_usd.csv','data/financial_guarantee_reconciliation.csv','data/mbsd_cleared_notional_reconciliation.csv','data/new_pqd_cell_evidence.csv','data/new_pqd_fields.csv']
        for name in names:
            p=self.bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}\n')
        c=db.connect(self.path)
        with c:
            c.execute("INSERT INTO datasets VALUES('market_observations','test','series/date','public')")
            rid=db.start_run(c,'new_remote_update')
            db.upsert(c,'market_observations','remote-latest',{'series_id':'SOFR','observation_date':'2026-10-22','value':4.25},rid)
        c.close()
    def tearDown(self):self.tmp.cleanup()
    def sync(self):return github_release.import_reviewed(bundle=self.bundle,database=self.path,log_dir=self.logs)
    def importer(self,*,bundle,path,make_snapshot):
        self.assertEqual(bundle,self.bundle);self.assertFalse(make_snapshot)
        c=db.connect(path)
        with c:
            rid=db.start_run(c,'reviewed_chain_research_import')
            change=db.upsert(c,'market_observations','research-history',{'series_id':'REPO','observation_date':'2019-09-17','value':5.25},rid)
        c.close();return {'changes':{change:1}}
    def values(self):
        c=db.connect(self.path)
        try:return {r['record_key']:json.loads(r['payload'])['value'] for r in c.execute('SELECT record_key,payload FROM records')}
        finally:c.close()
    def test_adds_to_restored_database_and_does_not_replay_over_newer_revision(self):
        with patch('import_chain_research.import_bundle',side_effect=self.importer) as importer:
            self.assertEqual(self.sync()['status'],'success')
            self.assertEqual(self.values(),{'remote-latest':4.25,'research-history':5.25})
            c=db.connect(self.path)
            with c:
                rid=db.start_run(c,'later_remote_revision')
                db.upsert(c,'market_observations','research-history',{'series_id':'REPO','observation_date':'2019-09-17','value':5.5},rid)
            c.close()
            self.assertEqual(self.sync()['status'],'already_applied')
            self.assertEqual(importer.call_count,1)
            self.assertEqual(self.values()['research-history'],5.5)
    def test_failed_import_is_not_marked_applied_and_is_retryable(self):
        with patch('import_chain_research.import_bundle',side_effect=ValueError('bad source hash')):
            with self.assertRaisesRegex(ValueError,'bad source hash'):self.sync()
        self.assertEqual(self.values(),{'remote-latest':4.25})
        with patch('import_chain_research.import_bundle',side_effect=self.importer):
            self.assertEqual(self.sync()['status'],'success')
    def test_missing_committed_input_stops_before_import(self):
        (self.bundle/'fetch_manifest.json').unlink()
        with patch('import_chain_research.import_bundle') as importer:
            with self.assertRaises(FileNotFoundError):self.sync()
            importer.assert_not_called()
    def test_changed_batch_is_imported_as_a_new_content_version(self):
        with patch('import_chain_research.import_bundle',side_effect=self.importer) as importer:
            first=self.sync();(self.bundle/'data/new_pqd_fields.csv').write_text('changed\n');second=self.sync()
            self.assertNotEqual(first['batch_fingerprint'],second['batch_fingerprint'])
            self.assertEqual(importer.call_count,2)
    def test_workflow_imports_after_restore_and_before_collection(self):
        workflow=(db.ROOT.parents[1]/'.github/workflows/daily-data.yml').read_text()
        self.assertLess(workflow.index('python github_release.py restore'),workflow.index('python github_release.py import-reviewed'))
        self.assertLess(workflow.index('python github_release.py import-reviewed'),workflow.index('python update.py'))
