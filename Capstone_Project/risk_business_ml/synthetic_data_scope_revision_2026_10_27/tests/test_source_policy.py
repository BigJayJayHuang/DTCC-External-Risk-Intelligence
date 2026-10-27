from pathlib import Path
import sys,unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from source_policy import assert_generation_allowed,assert_observed_unchanged

class SourcePolicyTests(unittest.TestCase):
    def test_observed_generation_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'must not be generated'):
            assert_generation_allowed(['issue_date','assumed_participation'],['issue_date','offered_amount_usd'])
        assert_generation_allowed(['assumed_participation'],['issue_date','offered_amount_usd'])
    def test_known_values_and_missingness_cannot_be_overwritten(self):
        f=pd.DataFrame({'observed':[1.0,float('nan')],'assumed_missing':[2.,3.]})
        g=f.copy();g['assumed_missing']=[4.,5.]
        assert_observed_unchanged(f,g,['observed'])
        g.loc[1,'observed']=0
        with self.assertRaises(AssertionError):assert_observed_unchanged(f,g,['observed'])

if __name__=='__main__':unittest.main()
