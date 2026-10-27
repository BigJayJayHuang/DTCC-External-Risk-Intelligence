"""Hand-calculated mechanism checks, not tests of empirical validity."""
from pathlib import Path
import sys
import unittest
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import default_funding as df


class DefaultResourcesTests(unittest.TestCase):
    def test_own_then_capped_collective_then_unallocated(self):
        r=df.allocate_default_loss(100,30,[20,10])
        self.assertEqual(r['own_resources_used_usd_million'],30)
        self.assertEqual(r['residual_after_own_usd_million'],70)
        self.assertEqual(r['allocations'],[20,10])
        self.assertEqual(r['unallocated_loss_usd_million'],40)
        self.assertEqual(r['loss_conservation_residual'],0)

    def test_prorata_under_cap(self):
        r=df.allocate_default_loss(50,30,[60,20])
        self.assertEqual(r['allocations'],[15,5])
        self.assertEqual(r['unallocated_loss_usd_million'],0)

    def test_no_default_no_resource_use(self):
        r=df.allocate_default_loss(90,10,[20],activated=False)
        self.assertEqual(r['loss_usd_million'],0)
        self.assertEqual(r['allocations'],[0])

    def test_zero_collective_capacity(self):
        r=df.allocate_default_loss(15,5,[0,0])
        self.assertEqual(r['unallocated_loss_usd_million'],10)
        self.assertEqual(r['allocations'],[0,0])

    def test_reject_invalid_inputs(self):
        for args in [(-1,2,[1]),(1,-2,[1]),(1,2,[-1]),(1,2,[])]:
            with self.assertRaises(ValueError):df.allocate_default_loss(*args)


class CloseoutTests(unittest.TestCase):
    def test_long_falls_short_rises_and_cost_is_separate(self):
        positions=[{'quantity':10000,'opening_price':100},{'quantity':-20000,'opening_price':100}]
        rows,r=df.closeout_positions(positions,adverse_fraction=.10,delay_days=1,cost_fraction=.01)
        self.assertEqual(rows[0]['closing_price'],90)
        self.assertAlmostEqual(rows[1]['closing_price'],110)
        self.assertAlmostEqual(rows[0]['signed_pnl_usd_million'],-.1)
        self.assertAlmostEqual(rows[1]['signed_pnl_usd_million'],-.2)
        self.assertAlmostEqual(r['transaction_cost_usd_million'],.03)
        self.assertAlmostEqual(r['closeout_loss_usd_million'],.33)

    def test_delay_mapping_not_random_probability(self):
        _,a=df.closeout_positions([{'quantity':10000,'opening_price':100}],adverse_fraction=.05,delay_days=1)
        _,b=df.closeout_positions([{'quantity':10000,'opening_price':100}],adverse_fraction=.05,delay_days=4)
        self.assertAlmostEqual(b['closeout_loss_usd_million'],2*a['closeout_loss_usd_million'])

    def test_unactivated_closeout(self):
        _,r=df.closeout_positions([{'quantity':1000,'opening_price':100}],adverse_fraction=.1,delay_days=3,cost_fraction=.1,activated=False)
        self.assertEqual(r['closeout_loss_usd_million'],0)

    def test_reject_nonpositive_prices(self):
        with self.assertRaises(ValueError):df.closeout_positions([{'quantity':1,'opening_price':0}],adverse_fraction=.1,delay_days=1)


class GcfDeadlineTests(unittest.TestCase):
    def obligation(self,**updates):
        r={'notional_usd_million':10,'cash_required_usd_million':10,'collateral_required_usd_million':10,
           'cash_available_usd_million':10,'collateral_market_usd_million':10,
           'cash_ready_min':200,'collateral_ready_min':300}
        r.update(updates);return r

    def test_equal_amount_and_equal_cutoff_pass(self):
        rows,r=df.gcf_deadline([self.obligation()],deadline_min=300,horizon_min=480)
        self.assertEqual(r['failed_deadline_count'],0)
        self.assertEqual(rows[0]['completion_min'],300)

    def test_both_gates_required(self):
        rows,r=df.gcf_deadline([self.obligation(cash_available_usd_million=9)],deadline_min=300,horizon_min=480)
        self.assertEqual(r['failed_deadline_notional_usd_million'],10)
        self.assertTrue(rows[0]['unfinished_at_horizon'])
        self.assertEqual(rows[0]['cash_shortfall_usd_million'],1)

    def test_collateral_haircut_does_not_create_cash(self):
        rows,_=df.gcf_deadline([self.obligation(collateral_market_usd_million=20)],deadline_min=300,horizon_min=480,haircut=.6)
        self.assertEqual(rows[0]['cash_available_usd_million'],10)
        self.assertEqual(rows[0]['eligible_collateral_usd_million'],8)
        self.assertTrue(rows[0]['failed_at_deadline'])

    def test_late_completion_and_unfinished_are_separate(self):
        obligations=[self.obligation(obligation_id='late',cash_ready_min=350),self.obligation(obligation_id='unfinished',cash_ready_min=500)]
        rows,r=df.gcf_deadline(obligations,deadline_min=300,horizon_min=480)
        self.assertEqual(r['late_completed_count'],1)
        self.assertEqual(r['unfinished_count'],1)
        self.assertTrue(rows[0]['late_completed']);self.assertFalse(rows[0]['unfinished_at_horizon'])
        self.assertFalse(rows[1]['late_completed']);self.assertTrue(rows[1]['unfinished_at_horizon'])

    def test_injected_resources_count_once(self):
        rows,_=df.gcf_deadline([self.obligation(cash_available_usd_million=0,collateral_market_usd_million=0)],deadline_min=300,horizon_min=480,extra_cash_fraction=1,extra_collateral_fraction=1)
        self.assertFalse(rows[0]['failed_at_deadline'])
        self.assertEqual(rows[0]['cash_available_usd_million'],10)
        self.assertEqual(rows[0]['eligible_collateral_usd_million'],10)


class AuctionLedgerTests(unittest.TestCase):
    def test_backlog_and_explicit_cash_conservation(self):
        rows,r=df.auction_cash_ledger([{'issue_day':0,'net_cash_due_usd_million':100}],daily_funding=[20,50,20],opening_cash=5)
        self.assertEqual([x['unpaid_due_usd_million'] for x in rows],[75,25,5])
        self.assertEqual(r['peak_unpaid_due_usd_million'],75)
        self.assertEqual(r['total_paid_usd_million'],95)
        self.assertEqual(r['terminal_unpaid_usd_million'],5)
        self.assertTrue(all(x['cash_conservation_residual']==0 and x['obligation_conservation_residual']==0 for x in rows))

    def test_same_total_different_issue_dates(self):
        concentrated=[{'issue_day':0,'net_cash_due_usd_million':100}]
        staggered=[{'issue_day':i,'net_cash_due_usd_million':25} for i in range(4)]
        _,a=df.auction_cash_ledger(concentrated,daily_funding=[25]*4)
        _,b=df.auction_cash_ledger(staggered,daily_funding=[25]*4)
        self.assertEqual(a['total_due_usd_million'],b['total_due_usd_million'])
        self.assertEqual(a['peak_unpaid_due_usd_million'],75)
        self.assertEqual(b['peak_unpaid_due_usd_million'],0)
        self.assertEqual(a['terminal_unpaid_usd_million'],0)

    def test_cash_carried_not_discarded(self):
        rows,r=df.auction_cash_ledger([{'issue_day':1,'net_cash_due_usd_million':15}],daily_funding=[10,10])
        self.assertEqual(rows[0]['closing_cash_usd_million'],10)
        self.assertEqual(r['terminal_cash_usd_million'],5)


class BankGateTests(unittest.TestCase):
    def participants(self):
        return [{'participant_id':'a','bank_id':'X','signed_balance_usd_million':10,'service':'DTC'},
                {'participant_id':'b','bank_id':'X','signed_balance_usd_million':-3,'service':'DTC'},
                {'participant_id':'c','bank_id':'Y','signed_balance_usd_million':5,'service':'DTC'}]

    def test_aggregate_net_and_gross_are_different(self):
        rows,r=df.settling_bank_gate(self.participants(),service='DTC',bank_acceptance_min={'X':None,'Y':300},deadline_min=420)
        self.assertEqual(rows[0]['aggregate_net_net_usd_million'],7)
        self.assertEqual(r['blocked_participant_debit_usd_million'],10)
        self.assertEqual(r['blocked_participant_credit_usd_million'],3)
        self.assertEqual(r['unsettled_bank_net_debit_usd_million'],7)
        self.assertTrue(all(x['netting_identity_residual']==0 for x in rows))

    def test_equal_deadline_accepts(self):
        _,r=df.settling_bank_gate(self.participants(),service='DTC',bank_acceptance_min={'X':420,'Y':420},deadline_min=420)
        self.assertEqual(r['banks_blocked'],0)

    def test_late_ack_stays_unsettled_at_deadline(self):
        _,r=df.settling_bank_gate(self.participants(),service='DTC',bank_acceptance_min={'X':421,'Y':420},deadline_min=420)
        self.assertEqual(r['banks_blocked'],1)

    def test_reject_cross_service_netting(self):
        p=self.participants();p[0]['service']='NSCC'
        with self.assertRaises(ValueError):df.settling_bank_gate(p,service='DTC',bank_acceptance_min={'X':300},deadline_min=420)


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.result=df.run_experiment(20261027,2)

    def test_all_runtime_checks(self):
        self.assertTrue(all(x['passed'] for x in self.result['checks']))
        self.assertEqual(len(self.result['scenarios']),36)
        self.assertEqual(len(self.result['chain_map']),6)

    def test_run_count_identity_and_seed_text(self):
        r=self.result['tables']['df_runs'];self.assertEqual(len(r),72)
        self.assertTrue(r.scenario_seed.map(lambda x:isinstance(x,str)).all())
        self.assertFalse(r.duplicated(['scenario_id','replicate_id']).any())
        self.assertEqual(set(r.primary_units),{'USD million'})

    def test_reproducibility(self):
        other=df.run_experiment(20261027,2)
        for name,frame in self.result['tables'].items():pd.testing.assert_frame_equal(frame,other['tables'][name])

    def test_workloads_paired_within_model_replication(self):
        x=self.result['tables']['df_inputs']
        for (_, _),g in x.groupby(['model_id','replicate_id']):
            frames=[]
            for _,f in g.groupby('scenario_id'):
                frames.append(f.drop(columns=['scenario_id']).reset_index(drop=True))
            for f in frames[1:]:pd.testing.assert_frame_equal(frames[0],f)

    def test_mitigation_explicit_resources_and_different_service_workloads(self):
        r=self.result['tables']['df_runs']
        g=r[(r.model_id=='gcf_deadline')&r.scenario_id.str.endswith('_mitigation')]
        self.assertTrue((g.additional_cash_usd_million>0).all())
        d=r[(r.model_id=='dtc_bank')&r.scenario_id.str.endswith('_shock')].primary_value.to_numpy()
        n=r[(r.model_id=='nscc_bank')&r.scenario_id.str.endswith('_shock')].primary_value.to_numpy()
        self.assertFalse((d==n).all())


if __name__=='__main__':unittest.main()
