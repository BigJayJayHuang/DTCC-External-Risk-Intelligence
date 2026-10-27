from pathlib import Path
import hashlib,sys,unittest
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gap_models import (load_observed,cash_ledger,tba_stock_ledger,compatible_member_shares,
                        normalized_addon,run_experiment,DEFAULT_CONFIG)

class CashLedgerTests(unittest.TestCase):
    def test_hand_cash_and_unpaid_conservation(self):
        rows,result=cash_ledger([10,10],[5,15])
        self.assertEqual([r['unpaid_usd'] for r in rows],[5,0])
        self.assertEqual(result['peak_unpaid_usd'],5)
        self.assertEqual(result['total_paid_usd'],20)
        self.assertEqual(result['terminal_cash_usd'],0)
        self.assertEqual(sum(r['cash_conservation_residual_usd'] for r in rows),0)
    def test_terminal_shortfall_not_erased(self):
        rows,result=cash_ledger([10],[3],opening_cash=2)
        self.assertEqual(result['terminal_unpaid_usd'],5)
        self.assertEqual(result['total_paid_usd'],5)
    def test_invalid_cash_schedules(self):
        for due,fund in [([],[]),([1],[]),([-1],[1]),([1],[float('nan')])]:
            with self.assertRaises(ValueError):cash_ledger(due,fund)

class TbaStockTests(unittest.TestCase):
    def test_hand_due_partitions(self):
        rows,result=tba_stock_ledger(100,[.2,.3,.5],[.5,.5,0])
        np.testing.assert_allclose([r['overdue_usd'] for r in rows],[10,20,0])
        np.testing.assert_allclose([r['settled_usd'] for r in rows],[10,20,70])
        np.testing.assert_allclose([r['closing_assumed_tba_stock_usd'] for r in rows],[90,70,0])
        self.assertEqual(result['peak_overdue_to_assumed_tba_stock'],.2)
        self.assertEqual(result['total_settled_usd'],100)
        self.assertLess(max(abs(r['partition_residual_usd']) for r in rows),1e-10)
    def test_zero_deferral_and_zero_stock(self):
        rows,result=tba_stock_ledger(0,[.5,.5],[1,1]);self.assertEqual(result['peak_overdue_usd'],0)
        rows,result=tba_stock_ledger(100,[.5,.5],[0,0]);self.assertEqual(result['peak_overdue_usd'],0)
    def test_invalid_maturity_and_deferral(self):
        for maturity,defer in [([.2,.2],[0,0]),([.5,.5],[0]),([.5,.5],[0,1.1])]:
            with self.assertRaises(ValueError):tba_stock_ledger(100,maturity,defer)

class ConcentrationTests(unittest.TestCase):
    def test_actual_top5_sum_rank_and_normalization(self):
        for skew in [0,.15,.8,1]:
            shares=compatible_member_shares(.3649,np.array([.1,.2,.4,.1,.2]),25,skew)
            self.assertAlmostEqual(shares.sum(),1,places=13)
            self.assertAlmostEqual(shares[:5].sum(),.3649,places=13)
            self.assertGreaterEqual(shares[4]+1e-14,shares[5:].max())
            self.assertTrue((np.diff(shares)<=1e-14).all())
    def test_exact_feasibility_boundary_is_uniform(self):
        shares=compatible_member_shares(.2,np.array([.1,.2,.4,.1,.2]),25,.9)
        np.testing.assert_allclose(shares,np.full(25,.04))
    def test_invalid_observed_share_not_overwritten(self):
        for s,n in [(.1,25),(.3,20),(1.1,25)]:
            with self.assertRaises(ValueError):compatible_member_shares(s,np.full(5,.2),n)
    def test_hand_addon_uses_normalized_units_not_dollars(self):
        exposure,addon=normalized_addon([.2,.1,.7],100,10,.2)
        np.testing.assert_allclose(exposure,[20,10,70]);np.testing.assert_allclose(addon,[2,0,12])

class ObservedInputAndExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_root=Path(__file__).resolve().parents[1]/'inputs/observed'
        cls.observed=load_observed(cls.source_root)
        cls.out=run_experiment(seed=20261027,replications=2,source_root=cls.source_root)
    def test_source_units_actual_average_peak_and_stock(self):
        self.assertEqual(float(self.observed['nscc']['top5_position_share']),.3649)
        self.assertEqual(float(self.observed['peak_evidence']['value']),.4025)
        self.assertEqual(float(self.observed['mbsd']['chosen_usd']),562_000_000_000)
        self.assertEqual(self.observed['avg_evidence']['dimension'],'AverageInQuarter')
        self.assertEqual(self.observed['peak_evidence']['dimension'],'PeakInQuarter')
    def test_observed_sources_and_fields_are_immutable(self):
        for row in self.out['sources']:
            self.assertEqual(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest(),row['sha256'])
        lots=self.out['tables']['auction_lots'];source=self.observed['auctions']
        for _,g in lots.groupby(['scenario_id','replicate_id']):
            g=g.sort_values('source_row_index')
            np.testing.assert_array_equal(g.observed_offered_amount_usd.to_numpy(),source.offered_amount_usd.to_numpy())
            np.testing.assert_array_equal(g.observed_issue_date.to_numpy(),source.issue_date.to_numpy())
        members=self.out['tables']['concentration_members']
        self.assertTrue(members.observed_top5_average_share.eq(.3649).all())
        self.assertTrue(members.observed_top5_peak_share.eq(.4025).all())
    def test_generated_obligations_do_not_become_actual_awards(self):
        lots=self.out['tables']['auction_lots']
        expected=lots.observed_offered_amount_usd*lots.assumed_effective_eligible_participation_of_offered*lots.assumed_net_obligation_fraction
        np.testing.assert_allclose(lots.conditional_obligation_usd,expected,rtol=1e-12)
        self.assertNotIn('actual_awarded_usd',lots)
        self.assertNotIn('actual_gsd_obligation_usd',lots)
    def test_pairing_null_controls_and_run_count(self):
        r=self.out['tables']['gap_runs']
        self.assertEqual(len(r),15*2);self.assertEqual(r.model_id.nunique(),3)
        self.assertTrue(r.groupby(['model_id','replicate_id']).scenario_seed.nunique().eq(1).all())
        self.assertTrue(r.scenario_seed.map(lambda x:isinstance(x,str)).all())
        self.assertTrue(all(x['passed'] for x in self.out['checks']))
    def test_reproducibility_without_writing_sources(self):
        other=run_experiment(seed=20261027,replications=2,source_root=self.source_root)
        for name in self.out['tables']:pd.testing.assert_frame_equal(self.out['tables'][name],other['tables'][name])
        self.assertEqual(DEFAULT_CONFIG['concentration_normalized_total'],100)

if __name__=='__main__':unittest.main()
