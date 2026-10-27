"""Independent hand fixtures for hypothetical mechanisms, not real DTCC validation."""
from pathlib import Path
import importlib.util
import math
import unittest

import numpy as np
import pandas as pd

SPEC=importlib.util.spec_from_file_location('expanded_margin_liquidity',Path(__file__).resolve().parents[1]/'src/margin_liquidity.py')
ml=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ml)


class MarketFixtures(unittest.TestCase):
    def test_cash_flow_stock_and_increment_are_separate(self):
        members=[{'member_id':'A','signed_delta':10,'starting_cash_usd_million':10},
                 {'member_id':'B','signed_delta':-10,'starting_cash_usd_million':10}]
        trace,total=ml.market_response(members,move=-2,unit_sigma=1,volatility_multiplier=2,risk_multiplier=3)
        # PnL [-20,+20]; 20 paid and 20 received, not 40 of system loss.
        self.assertEqual(total['vm_paid_usd_million'],20)
        self.assertEqual(total['vm_received_usd_million'],20)
        self.assertEqual(total['pnl_usd_million'],0)
        # Required stock goes 60 ->120, a60 cash call, distinct from20 VM.
        self.assertEqual(total['opening_required_margin_usd_million'],60)
        self.assertEqual(total['required_margin_usd_million'],120)
        self.assertEqual(total['margin_call_usd_million'],60)
        # A needs50 with10cash ->40gap; B funds30call from10cash+20receipt.
        self.assertEqual(total['funding_gap_usd_million'],40)
        self.assertTrue((trace.cash_balance_residual_usd_million==0).all())

    def test_hedge_changes_delta_and_release_is_not_credited_twice(self):
        members=[{'member_id':'A','signed_delta':10,'starting_cash_usd_million':0}]
        trace,total=ml.market_response(members,move=-2,unit_sigma=1,volatility_multiplier=2,residual_fraction=.25,risk_multiplier=3)
        self.assertEqual(total['vm_paid_usd_million'],5)
        self.assertEqual(total['required_margin_usd_million'],15)
        self.assertEqual(total['potential_margin_release_usd_million'],15)
        self.assertEqual(total['margin_call_usd_million'],0)
        self.assertEqual(total['funding_gap_usd_million'],5)
        self.assertEqual(total['ending_cash_usd_million'],0)

    def test_bad_units_and_duplicate_members_rejected(self):
        m=[{'member_id':'A','signed_delta':10,'starting_cash_usd_million':0}]
        for kwargs in [{'move':float('nan'),'unit_sigma':1}, {'move':1,'unit_sigma':-1},
                       {'move':1,'unit_sigma':1,'residual_fraction':1.2}]:
            with self.assertRaises(ValueError):ml.market_response(m,**kwargs)
        with self.assertRaises(ValueError):ml.market_response(m+m,move=1,unit_sigma=1)


class ConcentrationFixtures(unittest.TestCase):
    def test_hand_addon_without_changing_total_position(self):
        positions,r=ml.concentration_requirement([.6,.2,.2],gross_usd_million=100,
            base_margin_fraction=.05,threshold=.3,addon_rate=.2,member_capital_usd_million=20)
        self.assertAlmostEqual(r['concentration_addon_usd_million'],6)
        self.assertAlmostEqual(r['required_margin_usd_million'],11)
        self.assertAlmostEqual(r['requirement_to_assumed_capital'],.55)
        self.assertAlmostEqual(positions.position_usd_million.sum(),100)
        self.assertAlmostEqual(r['security_hhi'],.44)

    def test_exact_threshold_zero_and_weight_normalization(self):
        _,a=ml.concentration_requirement([3,3,2,2],gross_usd_million=100,threshold=.3)
        self.assertEqual(a['concentration_addon_usd_million'],0)
        _,b=ml.concentration_requirement([.3,.3,.2,.2],gross_usd_million=100,threshold=.3)
        self.assertEqual(a,b)
        with self.assertRaises(ValueError):ml.concentration_requirement([0,0],gross_usd_million=100)


class LiquidityFixtures(unittest.TestCase):
    def test_family_aggregation_calls_and_unfunded_call(self):
        members=[{'member_id':'A','family_id':'F','exposure_usd_million':60,'available_cash_usd_million':5},
                 {'member_id':'B','family_id':'F','exposure_usd_million':40,'available_cash_usd_million':5},
                 {'member_id':'C','family_id':'G','exposure_usd_million':80,'available_cash_usd_million':50}]
        trace,r=ml.liquidity_deposits(members,base_resources_usd_million=60,top_families=1)
        self.assertEqual(r['largest_family_exposure_usd_million'],100)  #Not largest singlemember80.
        self.assertEqual(r['sld_called_usd_million'],40)
        self.assertEqual(list(trace.sld_call_usd_million),[24,16,0])
        self.assertEqual(r['sld_collected_usd_million'],10)
        self.assertEqual(r['remaining_liquidity_gap_usd_million'],30)
        self.assertEqual(r['resource_balance_residual_usd_million'],0)

    def test_resource_surplus_and_zero_exposure_need_no_deposit(self):
        m=[{'member_id':'A','family_id':'F','exposure_usd_million':0,'available_cash_usd_million':5}]
        _,r=ml.liquidity_deposits(m,base_resources_usd_million=10)
        self.assertEqual(r['sld_called_usd_million'],0)
        self.assertEqual(r['sld_collected_usd_million'],0)
        self.assertEqual(r['unused_resources_usd_million'],10)
        with self.assertRaises(ValueError):ml.liquidity_deposits(m,base_resources_usd_million=0,top_families=0)


class CrossMarginFixtures(unittest.TestCase):
    def test_exact_offset_correlation_and_floor(self):
        exact=ml.combined_margin(100,-100,correlation=1,sigma_fraction=.02,risk_multiplier=3,gross_floor_fraction=.005)
        self.assertEqual(exact['risk_component_usd_million'],0)
        self.assertEqual(exact['combined_requirement_usd_million'],1)
        independent=ml.combined_margin(100,-100,correlation=0,sigma_fraction=.02,risk_multiplier=3,gross_floor_fraction=0)
        self.assertAlmostEqual(independent['combined_requirement_usd_million'],6*math.sqrt(2))
        same=ml.combined_margin(100,100,correlation=1,sigma_fraction=.02,risk_multiplier=3,gross_floor_fraction=0)
        self.assertAlmostEqual(same['combined_requirement_usd_million'],12)
        self.assertAlmostEqual(same['risk_offset_usd_million'],0)

    def test_invalid_correlation_is_not_silently_clipped(self):
        for bad in [-1.01,1.01,float('nan')]:
            with self.assertRaises(ValueError):ml.combined_margin(100,-100,correlation=bad)


class ExperimentFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=ml.run_experiment(seed=27,replications=2)

    def test_scenario_identity_reproducibility_and_exact_seed(self):
        other=ml.run_experiment(seed=27,replications=2)
        for name,table in self.output['tables'].items():
            pd.testing.assert_frame_equal(table,other['tables'][name])
            self.assertTrue(table.scenario_seed.map(lambda x:isinstance(x,str) and x.isdigit()).all())
        runs=self.output['tables']['ml_runs']
        self.assertEqual(len(runs),62)
        self.assertEqual(len(self.output['scenarios']),31)
        self.assertEqual(len(self.output['chain_map']),7)
        self.assertTrue(all(c['passed'] for c in self.output['checks']))
        self.assertFalse(self.output['assumptions']['empirical_validation'])

    def test_common_inputs_and_nulls(self):
        inputs=self.output['tables']['ml_market_inputs']
        grouped=inputs.groupby(['model_id','replicate_id','member_id'])
        self.assertTrue((grouped.signed_delta.nunique()==1).all())
        self.assertTrue((grouped.starting_cash_usd_million.nunique()==1).all())
        for model,g in self.output['tables']['ml_runs'].groupby('model_id'):
            a=g[g.scenario_id.eq(model+'_baseline')].sort_values('replicate_id')
            b=g[g.scenario_id.eq(model+'_unrelated')].sort_values('replicate_id')
            np.testing.assert_array_equal(a.primary_value,b.primary_value)

    def test_stress_mitigation_and_sensitivity_under_declared_assumptions(self):
        runs=self.output['tables']['ml_runs'].set_index(['scenario_id','replicate_id'])
        for rep in range(2):
            for service in ['gsd','mbsd','nscc']:
                pref='ml_market_'+service
                shock=runs.loc[(pref+'_stress',rep)]
                hedge=runs.loc[(pref+'_hedged',rep)]
                sensitivity=runs.loc[(pref+'_vol_sensitivity',rep)]
                self.assertLess(hedge.vm_paid_usd_million,shock.vm_paid_usd_million)
                self.assertLessEqual(hedge.margin_call_usd_million,shock.margin_call_usd_million)
                self.assertGreater(sensitivity.margin_call_usd_million,shock.margin_call_usd_million)
            stress=runs.loc[('ml_sld_stress',rep)]
            rescue=runs.loc[('ml_sld_cash_rescue',rep)]
            self.assertAlmostEqual(rescue.sld_called_usd_million,stress.sld_called_usd_million)
            self.assertLess(rescue.remaining_liquidity_gap_usd_million,stress.remaining_liquidity_gap_usd_million)
            self.assertAlmostEqual(rescue.remaining_liquidity_gap_usd_million,0)
            cross=runs.loc[('ml_cross_margin_stress',rep)].primary_value
            restored=runs.loc[('ml_cross_margin_correlation_rescue',rep)].primary_value
            self.assertLess(restored,cross)

    def test_defaults_not_mutated(self):
        before=ml.DEFAULT_CONFIG['members']
        ml.run_experiment(27,1,{'members':6,'liquidity_families':3})
        self.assertEqual(ml.DEFAULT_CONFIG['members'],before)


if __name__=='__main__':unittest.main()
