"""Protection against stale readers and invalid Cboe cache replacement."""
import csv
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation import data as D
from validation import refresh_scoring_inputs as R


def body(rows):
    f=io.StringIO();w=csv.writer(f,lineterminator='\n')
    w.writerow(['Day','Market Participant','Total Shares']);w.writerows(rows)
    return f.getvalue().encode()


class CboeRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.raw=self.root/'raw';self.derived=self.root/'derived'
        self.target=self.raw/'cboe/market_history_2026.csv';self.target.parent.mkdir(parents=True)
        self.old=body([['2026-11-02','NYSE','10'],['2026-11-02','Nasdaq','20']])
        self.target.write_bytes(self.old)
    def tearDown(self):self.tmp.cleanup()
    def refresh(self,new):
        return R.refresh_cboe(raw=self.raw,derived=self.derived,as_of=date(2026,11,9),fetch=lambda url:(200,new))
    def test_valid_current_year_updates_and_aggregates_each_venue_once(self):
        historical=self.raw/'cboe/market_history_2025.csv'
        historical.write_bytes(body([['2025-12-31','NYSE','5']]))
        before=historical.read_bytes()
        new=body([['2026-11-02','NYSE','11'],['2026-11-02','Nasdaq','20'],['2026-11-03','NYSE','30'],['2026-11-03','Nasdaq','40']])
        requests=[]
        result=R.refresh_cboe(raw=self.raw,derived=self.derived,as_of=date(2026,11,9),fetch=lambda url:(requests.append(url) or 200,new))
        self.assertEqual(len(requests),1);self.assertTrue(requests[0].endswith('market_history_2026.csv'))
        self.assertEqual(historical.read_bytes(),before);self.assertEqual(self.target.read_bytes(),new)
        with (self.derived/'cboe_consolidated_daily.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertEqual([(r['Day'],r['total_shares']) for r in rows],[('2025-12-31','5'),('2026-11-02','31'),('2026-11-03','70')])
        self.assertEqual(result['coverage_end'],'2026-11-03')
        self.assertEqual(result['new_venue_day_rows'],2)
        self.assertEqual(result['revised_venue_day_rows'],1)
        self.assertEqual(result['removed_venue_day_rows'],0)
        with (self.raw/'SOURCES_LOG.csv').open() as f:log=list(csv.DictReader(f))
        self.assertEqual(log[0]['sha256'],result['sha256'])
    def test_bad_schema_and_duplicate_response_preserve_valid_cache(self):
        cases=[b'<html>temporary problem</html>',body([['2026-11-02','NYSE','10'],['2026-11-02','NYSE','10']])]
        for new in cases:
            with self.subTest(new=new),self.assertRaises(ValueError):self.refresh(new)
            self.assertEqual(self.target.read_bytes(),self.old)
        self.assertFalse((self.raw/'SOURCES_LOG.csv').exists())
    def test_future_date_and_nonfinite_values_are_rejected(self):
        for new in [body([['2026-11-10','NYSE','2']]),body([['2026-11-02','NYSE','NaN']]),body([['2026-11-02','NYSE','-1']])]:
            with self.subTest(new=new),self.assertRaises(ValueError):self.refresh(new)
            self.assertEqual(self.target.read_bytes(),self.old)
    def test_truncated_history_does_not_replace_cache(self):
        with self.assertRaisesRegex(ValueError,'loses previously'):
            self.refresh(body([['2026-11-03','NYSE','40']]))
        self.assertEqual(self.target.read_bytes(),self.old)
    def test_materially_incomplete_new_day_is_not_used(self):
        oldrows=[['2026-11-02',venue,'10'] for venue in ['NYSE','Nasdaq','Cboe']]
        self.old=body(oldrows);self.target.write_bytes(self.old)
        with self.assertRaisesRegex(ValueError,'incomplete venue'):
            self.refresh(body(oldrows+[['2026-11-03','NYSE','30']]))
        self.assertEqual(self.target.read_bytes(),self.old)
    def test_backup_files_cannot_duplicate_current_year_volume(self):
        (self.target.parent/'market_history_2026.backup.csv').write_bytes(self.old)
        totals=R.aggregate_cboe(R.cboe_rows(self.target.parent,as_of=date(2026,11,9)))
        self.assertEqual(totals,[{'Day':'2026-11-02','total_shares':'30','venues':2}])
    def test_http_failure_preserves_cache(self):
        with self.assertRaisesRegex(ValueError,'HTTP403'):
            R.refresh_cboe(raw=self.raw,derived=self.derived,as_of=date(2026,11,9),fetch=lambda url:(403,b'blocked'))
        self.assertEqual(self.target.read_bytes(),self.old)


class MortgageReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.raw=self.root/'raw';(self.raw/'fred').mkdir(parents=True)
        self.market=self.root/'market.csv'
        self.fallback=self.raw/'fred/MORTGAGE30US.csv'
        self.fallback.write_text('observation_date,MORTGAGE30US\n2026-10-22,7.30\n2026-10-29,7.24\n')
        self.market.write_text('series_id,observation_date,value\nMORTGAGE30US,2026-10-29,7.20\nMORTGAGE30US,2026-11-05,7.10\nMORTGAGE30US,2099-01-01,99\nDGS10,2026-11-06,4.20\n')
        self.patches=[patch.object(D,'RAW',self.raw),patch.object(D,'MARKET_DAILY',self.market),patch.object(R,'today_ny',return_value=date(2026,11,9))]
        for p in self.patches:p.start()
        D.fred.cache_clear()
    def tearDown(self):
        D.fred.cache_clear()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_export_overrides_frozen_mortgage_and_adds_latest_week(self):
        s=D.fred('MORTGAGE30US')
        self.assertEqual(s.index.strftime('%Y-%m-%d').tolist(),['2026-10-22','2026-10-29','2026-11-05'])
        self.assertEqual(s.tolist(),[7.3,7.2,7.1])
    def test_missing_export_value_keeps_valid_fallback(self):
        self.market.write_text('series_id,observation_date,value\nMORTGAGE30US,2026-10-29,.\n')
        s=D.fred('MORTGAGE30US');self.assertEqual(s.iloc[-1],7.24)
    def test_export_without_mortgage_still_uses_frozen_history(self):
        self.market.write_text('series_id,observation_date,value\nDGS10,2026-11-06,4.2\n')
        self.assertEqual(D.fred('MORTGAGE30US').iloc[-1],7.24)
    def test_export_can_work_without_frozen_file(self):
        self.fallback.unlink();s=D.fred('MORTGAGE30US')
        self.assertEqual(s.index.max().strftime('%Y-%m-%d'),'2026-11-05')
        self.assertEqual(D.fred('DGS10').iloc[-1],4.2)
    def test_audit_default_never_downloads(self):
        with patch.object(R,'download',side_effect=AssertionError('No network allowed')),patch.object(R,'audit',return_value={'audit_errors':[]}),patch('sys.stdout',new_callable=io.StringIO):
            report=R.main(['--audit','--as-of','2026-11-09'])
        self.assertEqual(report['mode'],'audit_only');self.assertEqual(report['model_calls'],0)


if __name__=='__main__':unittest.main()
