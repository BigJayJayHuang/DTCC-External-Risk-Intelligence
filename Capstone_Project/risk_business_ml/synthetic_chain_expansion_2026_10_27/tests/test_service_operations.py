"""Independent small fixtures for the synthetic service gates and ledgers."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import service_operations as ops


def order(ident='A', arrival=0, amount=10, **kwargs):
    return {'order_id':ident,'arrival_min':arrival,'notional_usd_million':amount,
            'operation':'instruction','gate_time_min':0.0,**kwargs}


class ServiceMechanismTests(unittest.TestCase):
    def simulate(self,orders,**kwargs):
        config=dict(capacity_per_min=1,deadline_min=10,horizon_min=20,settlement_lag_min=0)
        config.update(kwargs)
        return ops.simulate_orders(orders,**config)

    def test_missing_ack_blocks_only_matching_acronym(self):
        rows=[order('A',gate_time_min=None,acronym_id='X'),order('B',acronym_id='Y')]
        events,summary=self.simulate(rows)
        self.assertEqual(summary['completed_count'],1)
        self.assertEqual(summary['unfinished_count'],1)
        self.assertEqual(events.set_index('order_id').loc['B','settlement_complete_min'],1)

    def test_registration_confirmation_precedes_credit(self):
        events,_=self.simulate([order(gate_time_min=8)])
        self.assertEqual(events.iloc[0].settlement_complete_min,9)

    def test_deposit_chill_does_not_automatically_block_transfer(self):
        raw=[dict(order('A'),security_group=0,route_uniform=.2),dict(order('B'),security_group=0,route_uniform=.2)]
        configured,_=ops._configure('security_restriction','stress',raw,{**ops.DEFAULT_CONFIG,'base_orders':2})
        events,summary=self.simulate(configured)
        self.assertEqual(summary['completed_count'],1)
        self.assertEqual(events.set_index('order_id').loc['B','operation'],'book_entry_transfer')

    def test_global_lock_blocks_both_modeled_operations(self):
        raw=[dict(order('A'),security_group=0,route_uniform=.2),dict(order('B'),security_group=0,route_uniform=.2)]
        configured,_=ops._configure('security_restriction','sensitivity',raw,{**ops.DEFAULT_CONFIG,'base_orders':2})
        _,summary=self.simulate(configured)
        self.assertEqual(summary['unfinished_count'],2)

    def test_trading_halt_does_not_impose_lock(self):
        raw=[dict(order('A'),security_group=0,route_uniform=.2)]
        configured,_=ops._configure('security_restriction','unrelated',raw,{**ops.DEFAULT_CONFIG,'base_orders':1})
        self.assertTrue(configured[0]['trading_halt_observed'])
        self.assertEqual(configured[0]['explicit_dtc_restriction'],'none')
        _,summary=self.simulate(configured)
        self.assertEqual(summary['completed_count'],1)

    def test_gross_fund_load_not_net_flow(self):
        events,summary=self.simulate([order('P',amount=100,operation='purchase'),order('R',amount=100,operation='redemption')],redemption_cash_usd_million=100)
        self.assertEqual(summary['net_fund_flow_usd_million'],0)
        self.assertEqual(summary['gross_instruction_notional_usd_million'],200)
        self.assertEqual(summary['order_count'],2)
        self.assertEqual(summary['redemption_cash_end_usd_million'],0)

    def test_purchase_money_not_reused_for_redemptions(self):
        _,summary=self.simulate([order('P',amount=100,operation='purchase'),order('R',amount=10,operation='redemption')],redemption_cash_usd_million=5)
        self.assertEqual(summary['cash_blocked_count'],1)
        self.assertEqual(summary['completed_count'],1)
        self.assertEqual(summary['redemption_cash_end_usd_million'],5)

    def test_cash_conservation_and_no_negative_balance(self):
        _,summary=self.simulate([order('A',amount=4,operation='redemption'),order('B',amount=6,operation='redemption'),order('C',amount=3,operation='redemption')],redemption_cash_usd_million=10)
        self.assertEqual(summary['completed_redemptions_usd_million'],10)
        self.assertEqual(summary['redemption_cash_end_usd_million'],0)
        self.assertEqual(summary['unfinished_count'],1)

    def test_paused_service_hand_calculation(self):
        self.assertEqual(ops.service_finish(3,5,(5,10)),13)
        self.assertEqual(ops.service_finish(6,2,(5,10)),12)
        self.assertEqual(ops.service_finish(3,2,(5,10)),5)

    def test_censored_is_not_late_completed(self):
        events,summary=self.simulate([order(outage_exposed=True)],outage=(0,30))
        self.assertEqual(summary['completed_late_count'],0)
        self.assertEqual(summary['unfinished_count'],1)
        self.assertEqual(summary['overdue_count'],1)
        self.assertEqual(events.iloc[0].delay_lower_bound_min,10)

    def test_completed_late_distinct(self):
        _,summary=self.simulate([order(gate_time_min=12)])
        self.assertEqual(summary['completed_late_count'],1)
        self.assertEqual(summary['unfinished_count'],0)

    def test_instruction_count_and_notional_conservation(self):
        _,summary=self.simulate([order('A',amount=7),order('B',amount=11,gate_time_min=None)])
        self.assertEqual(summary['completed_count']+summary['unfinished_count'],2)
        self.assertEqual(summary['completed_notional_usd_million']+summary['unfinished_notional_usd_million'],18)

    def test_separate_link_lane_does_not_delay_domestic(self):
        events,_=self.simulate([order('A',outage_exposed=True,lane_id='link'),order('B',lane_id='domestic')],outage=(0,30))
        self.assertEqual(events.set_index('order_id').loc['B','settlement_complete_min'],1)

    def test_paired_reproducible_and_distinct_link_samples(self):
        first=ops.run_experiment(seed=7,replications=2)
        second=ops.run_experiment(seed=7,replications=2)
        for key in first['tables']:
            pd.testing.assert_frame_equal(first['tables'][key],second['tables'][key])
        self.assertTrue(all(c['passed'] for c in first['checks']))
        runs=first['tables']['ops_runs']
        self.assertEqual(len(runs),70)
        self.assertEqual(len(first['chain_map']),7)
        seeds=runs.loc[runs.scenario_role.eq('baseline')].groupby('model_id').scenario_seed.first()
        self.assertNotEqual(seeds['dtc_canadian_link'],seeds['nscc_international_link'])

    def test_invalid_inputs_rejected(self):
        for kwargs in ({'capacity_per_min':0},{'horizon_min':5},{'redemption_cash_usd_million':-1}):
            with self.assertRaises(ValueError):self.simulate([order()],**kwargs)
        with self.assertRaises(ValueError):self.simulate([order(amount=-1)])
        with self.assertRaises(ValueError):self.simulate([order(),order()])


if __name__=='__main__':unittest.main()
