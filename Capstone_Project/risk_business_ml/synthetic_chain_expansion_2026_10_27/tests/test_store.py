from pathlib import Path
import sqlite3,sys,tempfile,unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from run_expansion import tag,store

class StoreTests(unittest.TestCase):
    def test_repeat_and_exact_seed_and_constraints(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'simulation.sqlite3'
            f=tag(pd.DataFrame([dict(scenario_id='toy',replicate_id=0,scenario_seed='18446744073709551615',value=2.5)]),'SIM_TEST')
            one=store(p,'SIM_TEST',{'seed':42},{'toy':f});two=store(p,'SIM_TEST',{'seed':42},{'toy':f})
            self.assertEqual(one['changes']['new'],1);self.assertEqual(two['changes'],{'new':0,'changed':0,'unchanged':1})
            c=sqlite3.connect(p)
            try:
                self.assertEqual(c.execute('select scenario_seed from synthetic_toy').fetchone()[0],'18446744073709551615')
                with self.assertRaises(sqlite3.IntegrityError):c.execute("update synthetic_toy set source_type='empirical'")
                with self.assertRaises(sqlite3.IntegrityError):c.execute('update synthetic_toy set empirical_validation=1')
            finally:c.close()
    def test_immutable_rows_and_plan(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'simulation.sqlite3';f=tag(pd.DataFrame([dict(scenario_id='toy',replicate_id=0,scenario_seed='1',value=2.5)]),'SIM_TEST')
            store(p,'SIM_TEST',{'seed':1},{'toy':f})
            with self.assertRaisesRegex(ValueError,'identity collision'):store(p,'SIM_TEST',{'seed':2},{'toy':f})
            f['value']=3
            with self.assertRaisesRegex(ValueError,'row changed'):store(p,'SIM_TEST',{'seed':1},{'toy':f})

if __name__=='__main__':unittest.main()
