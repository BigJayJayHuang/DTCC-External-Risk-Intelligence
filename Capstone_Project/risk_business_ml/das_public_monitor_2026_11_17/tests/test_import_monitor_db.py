"""Offline tests for evidence-bound imports and preservation of other datasets."""
from contextlib import closing
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'src/import_monitor_db.py'
spec = importlib.util.spec_from_file_location('import_monitor_db', MODULE)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class ImportMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('evidence', 'results', 'data'):
            (self.root / folder).mkdir()
        self.raw = b'Official public service evidence, not internal V.'
        (self.root / 'evidence/source.txt').write_bytes(self.raw)
        (self.root / 'evidence/second.txt').write_bytes(b'Independent public evidence.')
        self.monitor = {
            'sources': [dict(source_id='official', url='https://example.com/official', status='retrieved',
                             raw_file='evidence/source.txt', raw_sha256=hashlib.sha256(self.raw).hexdigest()),
                        dict(source_id='secondary', url='https://example.com/second', status='retrieved',
                             raw_file='evidence/second.txt')],
            'findings': [dict(finding_id='F01', source_id='official', title='Published service condition')],
            'facts': [dict(fact_id='FACT01', source_ids=['official', 'secondary'], value=4, units='hours')],
            'scope': [dict(card_id='DAS-01', source_id='official', V_score=None)],
            'networks': [dict(network_id='N01', source_id='official', status='public evidence only')],
            'metrics': [dict(metric_id='RTO', source_id='official', observation_date='2026-11-09', value=4)],
            'deadlines': [dict(deadline_id='D01', source_id='official', date=None)],
        }
        self.path = self.root / 'data/test.sqlite3'

    def connect(self):
        return closing(sqlite3.connect(self.path))

    def run_import(self, **kwargs):
        return importer.import_into_database(self.root, self.monitor, self.path, **kwargs)

    def test_reimport_is_idempotent_and_multiple_sources_link_to_blobs(self):
        first = self.run_import()
        with self.connect() as c:
            before = c.execute('SELECT count(*) FROM record_versions').fetchone()[0]
            self.assertEqual(c.execute("SELECT count(*) FROM record_evidence WHERE dataset_id='das_monitor_facts'").fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT count(*) FROM evidence_blobs').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT sum(enabled) FROM sources').fetchone()[0], 0)
        second = self.run_import()
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM record_versions').fetchone()[0], before)
            self.assertEqual(c.execute('SELECT count(*) FROM record_evidence').fetchone()[0], 9)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(first['changes']['new'], 8)
        self.assertEqual(second['changes'], {'unchanged': 8})

    def test_new_metric_dates_and_legacy_latest_data_are_preserved(self):
        db = importer.database_module()
        c = db.connect(self.path)
        with c:
            c.execute('INSERT INTO datasets VALUES(?,?,?,?)', ('market_observations', 'Legacy market', 'day', 'Measured'))
            c.execute('INSERT INTO sources(source_id,name,url,kind,refresh_hours,enabled,config) VALUES(?,?,?,?,?,?,?)',
                      ('legacy_source', 'Legacy', 'https://example.com/legacy', 'feed', 24, 1, '{}'))
            c.execute('INSERT INTO business_lines VALUES(?,?,?)', ('DAS', 'Keep this name', 'Keep this scope'))
            c.execute('INSERT INTO source_business VALUES(?,?)', ('legacy_source', 'DAS'))
        run = db.start_run(c, 'legacy')
        with c:
            db.upsert(c, 'market_observations', 'SERIES|2026-11-17',
                      {'series_id': 'SERIES', 'observation_date': '2026-11-17', 'value': 123}, run, 'legacy_source')
        before = c.execute("SELECT * FROM records WHERE dataset_id='market_observations'").fetchall()
        c.close()
        master = self.path.with_suffix('.sqlite3.gz')
        master.write_bytes(b'Existing master snapshot must not change')
        self.run_import(require_existing=True)
        self.monitor['metrics'][0]['observation_date'] = '2026-11-17'
        self.monitor['metrics'][0]['value'] = 3
        self.run_import(require_existing=True)
        with self.connect() as c:
            after = c.execute("SELECT * FROM records WHERE dataset_id='market_observations'").fetchall()
            self.assertEqual([tuple(x) for x in before], after)
            self.assertEqual(c.execute("SELECT count(*) FROM records WHERE dataset_id='das_monitor_metrics'").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT full_name,scope_note FROM business_lines WHERE business_line='DAS'").fetchone(), ('Keep this name', 'Keep this scope'))
            self.assertEqual(c.execute("SELECT enabled FROM sources WHERE source_id='legacy_source'").fetchone()[0], 1)
        self.assertEqual(master.read_bytes(), b'Existing master snapshot must not change')

    def test_injected_evidence_failure_rolls_back_records_sources_blobs_and_run(self):
        db = importer.database_module()
        c = db.connect(self.path)
        c.close()
        original = db.upsert
        calls = []

        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise sqlite3.IntegrityError('Injected evidence-linking failure')
            return original(*args, **kwargs)

        with patch.object(importer, 'database_module', return_value=db), patch.object(db, 'upsert', side_effect=fail_second):
            with self.assertRaises(sqlite3.IntegrityError):
                self.run_import()
        with self.connect() as c:
            for table in ('records', 'record_versions', 'record_evidence', 'evidence_blobs',
                          'sources', 'datasets', 'runs', 'business_lines'):
                self.assertEqual(c.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0, table)

    def test_hash_mismatch_and_unknown_reference_rejected_before_writes(self):
        self.monitor['sources'][0]['raw_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.run_import()
        self.assertFalse(self.path.exists())
        self.monitor['sources'][0]['raw_sha256'] = hashlib.sha256(self.raw).hexdigest()
        self.monitor['facts'][0]['source_ids'] = ['missing']
        with self.assertRaisesRegex(ValueError, 'Unknown source'):
            self.run_import()
        self.assertFalse(self.path.exists())

    def test_path_escape_and_conflicting_identity_rejected(self):
        outside = self.root / 'outside.txt'
        outside.write_text('outside')
        self.monitor['sources'][0]['raw_file'] = 'outside.txt'
        with self.assertRaisesRegex(ValueError, 'escapes evidence'):
            self.run_import()
        self.monitor['sources'][0]['raw_file'] = 'evidence/source.txt'
        conflicting = dict(self.monitor['facts'][0], value=999)
        self.monitor['facts'].append(conflicting)
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            self.run_import()

    def test_public_snapshot_excludes_raw_bodies_and_has_valid_references(self):
        receipt = self.run_import(make_snapshot=True)
        packed = self.path.with_suffix('.sqlite3.gz')
        self.assertEqual(hashlib.sha256(packed.read_bytes()).hexdigest(), receipt['snapshot']['sha256'])
        snapshot = self.root / 'shared.sqlite3'
        snapshot.write_bytes(gzip.decompress(packed.read_bytes()))
        with closing(sqlite3.connect(snapshot)) as c:
            self.assertEqual(c.execute('SELECT sum(length(content)) FROM evidence_blobs').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT DISTINCT compression FROM evidence_blobs').fetchall(), [('not_bundled',)])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0], 8)

    def test_missing_optional_target_never_created(self):
        monitor_path = self.root / 'results/monitor.json'
        monitor_path.write_text(json.dumps(self.monitor))
        target = self.root / 'missing-project.sqlite3'
        with self.assertRaises(FileNotFoundError):
            importer.import_monitor(monitor_path, target)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / 'data/das_monitor.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
