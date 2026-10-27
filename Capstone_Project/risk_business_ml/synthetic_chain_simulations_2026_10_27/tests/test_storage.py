"""Synthetic isolation and repeatability tests, with no empirical DB writes."""
from pathlib import Path
import json,sqlite3,sys,tempfile,unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from run_simulations import add_tags,store_database

class SyntheticStorageTests(unittest.TestCase):
    def test_repeat_is_idempotent_and_real_records_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.sqlite3'
            row={'scenario_id':'toy_baseline','replicate_id':0,'scenario_seed':42,'value':1.0}
            tables={'toy':add_tags(pd.DataFrame([row]),'SIM_TEST')}
            anchor={'reference_id':'toy_reference','source_type':'public_reference','value':2}
            first=store_database(path,'SIM_TEST',{'seed':42},tables,[],anchor)
            again=store_database(path,'SIM_TEST',{'seed':42},tables,[],anchor)
            self.assertEqual(first['changes'],{'new':1,'changed':0,'unchanged':0})
            self.assertEqual(again['changes'],{'new':0,'changed':0,'unchanged':1})
            c=sqlite3.connect(path)
            try:
                self.assertEqual(c.execute('SELECT value FROM synthetic_toy').fetchone()[0],1)
                self.assertEqual(c.execute('SELECT scenario_seed FROM synthetic_toy').fetchone()[0],'42')
                payload=json.dumps({'source_type':'empirical','empirical_validation':True})
                with self.assertRaises(sqlite3.IntegrityError):c.execute('INSERT INTO simulation_records VALUES(?,?,?,?,?)',('SIM_TEST','toy','bad',payload,'bad'))
            finally:c.close()
    def test_plan_identity_collision_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.sqlite3';anchor={'reference_id':'toy','source_type':'public_reference'}
            store_database(path,'SIM_TEST',{'seed':1},{},[],anchor)
            with self.assertRaisesRegex(ValueError,'identity collision'):store_database(path,'SIM_TEST',{'seed':2},{},[],anchor)
