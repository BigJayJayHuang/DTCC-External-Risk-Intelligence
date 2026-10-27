"""Independent fixtures for the synthetic two-constraint queue."""
from pathlib import Path
import importlib.util
import unittest
import numpy as np
import pandas as pd

SPEC=importlib.util.spec_from_file_location('synthetic_dtc',Path(__file__).resolve().parents[1]/'src/dtc.py')
dtc=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(dtc)

def tx(tid,time,amount):return {'transaction_id':tid,'time_minutes':time,'amount_usd_million':amount}

class DtcEngineTests(unittest.TestCase):
    def test_exact_cap_and_haircut_boundary_then_repayment_recycles_fifo(self):
        r=dtc.simulate_day([tx('A',1,40),tx('B',2,10)],[{'event_type':'cash_funding','time_minutes':3,'amount_usd_million':10}],net_debit_cap_usd_million=40,collateral_market_value_usd_million=50,haircut=.2,horizon_minutes=5)
        settled=[e for e in r['events'] if e['event_type']=='settlement']
        self.assertEqual([(e['transaction_id'],e['time_minutes']) for e in settled],[('A',1),('B',3)])
        self.assertEqual(r['summary']['settled_amount_usd_million'],50)
        self.assertEqual(r['summary']['eod_net_debit_usd_million'],40)
        self.assertAlmostEqual(r['summary']['queue_area_usd_million_minutes'],10)
        self.assertEqual(r['summary']['eod_pending_count'],0)
    def test_collateral_limit_blocks_even_with_spare_cap(self):
        r=dtc.simulate_day([tx('A',1,41)],[],net_debit_cap_usd_million=100,collateral_market_value_usd_million=50,haircut=.2,horizon_minutes=5)
        self.assertEqual(r['summary']['settled_count'],0)
        blocked=[e for e in r['events'] if e['event_type']=='blocked']
        self.assertEqual(blocked[0]['reason'],'eligible_collateral')
    def test_cash_can_repair_collateral_headroom_without_being_double_counted(self):
        r=dtc.simulate_day([tx('A',1,20),tx('B',2,15)],[{'event_type':'cash_funding','time_minutes':3,'amount_usd_million':15}],net_debit_cap_usd_million=100,collateral_market_value_usd_million=20,horizon_minutes=5)
        self.assertEqual(r['summary']['settled_amount_usd_million'],35)
        self.assertEqual(r['summary']['eod_net_debit_usd_million'],20)
        self.assertEqual(r['summary']['eod_cash_usd_million'],0)
        self.assertEqual(r['summary']['eod_eligible_collateral_usd_million'],20)
        self.assertTrue(all(abs(e['ledger_residual_usd_million'])<1e-9 for e in r['events']))
    def test_cash_above_outstanding_debit_becomes_prefunding(self):
        r=dtc.simulate_day([tx('A',1,20)],[{'event_type':'cash_funding','time_minutes':2,'amount_usd_million':30}],net_debit_cap_usd_million=20,collateral_market_value_usd_million=20,horizon_minutes=5)
        self.assertEqual(r['summary']['eod_net_debit_usd_million'],0)
        self.assertEqual(r['summary']['eod_cash_usd_million'],10)
        funding=[e for e in r['events'] if e['event_type']=='cash_funding'][0]
        self.assertEqual(funding['cash_repaid_usd_million'],20)
        self.assertEqual(funding['eligible_collateral_usd_million'],20)
    def test_cap_increase_is_not_cash_and_cannot_alone_solve_collateral_deficit(self):
        r=dtc.simulate_day([tx('A',1,21)],[{'event_type':'cap_increase','time_minutes':2,'amount_usd_million':100}],net_debit_cap_usd_million=10,collateral_market_value_usd_million=20,horizon_minutes=5)
        self.assertEqual(r['summary']['settled_amount_usd_million'],0)
        self.assertEqual(r['summary']['cash_funding_received_usd_million'],0)
        self.assertEqual(r['summary']['eod_eligible_collateral_usd_million'],20)
    def test_fifo_blocks_smaller_later_transaction(self):
        r=dtc.simulate_day([tx('A',1,11),tx('B',2,1)],[],net_debit_cap_usd_million=10,collateral_market_value_usd_million=10,horizon_minutes=5)
        self.assertEqual(r['summary']['settled_count'],0)
        self.assertEqual(r['summary']['eod_pending_amount_usd_million'],12)
        self.assertEqual(r['summary']['ever_queued_count'],2)
        self.assertEqual(r['summary']['ever_head_blocked_count'],1)
    def test_after_horizon_cash_is_not_available_before_cutoff(self):
        r=dtc.simulate_day([tx('A',1,10)],[{'event_type':'cash_funding','time_minutes':6,'amount_usd_million':10}],horizon_minutes=5)
        self.assertEqual(r['summary']['eod_pending_amount_usd_million'],10)
        self.assertTrue(all(e['time_minutes']<=5 for e in r['events']))
    def test_revaluation_does_not_reverse_completed_settlement(self):
        r=dtc.simulate_day([tx('A',1,10)],[{'event_type':'collateral_update','time_minutes':2,'haircut':.8}],net_debit_cap_usd_million=20,collateral_market_value_usd_million=20,horizon_minutes=5)
        self.assertEqual(r['summary']['settled_amount_usd_million'],10)
        self.assertTrue(r['events'][-1]['resource_breach_after_revaluation'])
    def test_invalid_amounts_and_duplicate_transactions_rejected(self):
        for bad in [-1,float('nan')]:
            with self.assertRaises(ValueError):dtc.simulate_day([tx('A',1,bad)],[])
        with self.assertRaises(ValueError):dtc.simulate_day([tx('A',1,1),tx('A',2,1)],[])

class DtcExperimentTests(unittest.TestCase):
    def test_reproducibility_common_random_numbers_and_controls(self):
        a=dtc.run_experiment(27,replications=3);b=dtc.run_experiment(27,replications=3)
        for name in a['tables']:pd.testing.assert_frame_equal(a['tables'][name],b['tables'][name])
        self.assertTrue(all(c['passed'] for c in a['checks']))
        runs=a['tables']['dtc_runs'];self.assertEqual(len(runs),24)
        inp=a['tables']['dtc_inputs'];txs=inp[inp.input_type.eq('transaction')]
        for (_,tid),group in txs.groupby(['replicate_id','transaction_id']):
            self.assertEqual(group.time_minutes.nunique(),1)
            self.assertEqual(group.amount_usd_million.nunique(),1)
        metrics=['settled_amount_usd_million','queue_area_usd_million_minutes','mean_settled_wait_minutes','eod_pending_amount_usd_million']
        baseline=runs[runs.scenario_id.eq('dtc_baseline')].set_index('replicate_id')
        unrelated=runs[runs.scenario_id.eq('dtc_unrelated_event')].set_index('replicate_id')
        self.assertTrue(np.allclose(baseline[metrics],unrelated[metrics]))
        shock=runs[runs.scenario_id.eq('dtc_funding_shock')].set_index('replicate_id')
        rescue=runs[runs.scenario_id.eq('dtc_cash_rescue')].set_index('replicate_id')
        self.assertTrue((rescue.eod_pending_amount_usd_million<=shock.eod_pending_amount_usd_million+1e-8).all())
        self.assertTrue((rescue.eod_pending_count==0).all())
        self.assertEqual(set(runs.chain_ids),{'ECS-DTC-06'})

if __name__=='__main__':unittest.main()
