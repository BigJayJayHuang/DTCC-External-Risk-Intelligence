"""Independent toy examples for the hypothetical stock-flow maturity ladder."""
from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import tba


class TbaLadderTests(unittest.TestCase):
    def test_known_two_day_rollforward_and_deferral(self):
        x=tba.simulate_ladder({0:100},[20,10],[1,1],[5,0],[.5,1])
        # Day0:120 before cancellation,115 after; due100*(115/120).
        due=100*115/120;settled=due*.5
        self.assertAlmostEqual(x.loc[0,'settled_usd'],settled)
        self.assertAlmostEqual(x.loc[0,'closing_unsettled_usd'],115-settled)
        self.assertAlmostEqual(x.loc[0,'overdue_unsettled_usd'],due*.5)
        # All remaining original and day0 trades are due on day1; new10 is not.
        self.assertAlmostEqual(x.loc[1,'settled_usd'],115-settled)
        self.assertAlmostEqual(x.loc[1,'closing_unsettled_usd'],10)

    def test_zero_deferral_balanced_daily_flow(self):
        x=tba.simulate_ladder({0:10},[10]*5,[1]*5,[0]*5,[1]*5)
        np.testing.assert_allclose(x.closing_unsettled_usd,10)
        np.testing.assert_allclose(x.settled_usd,10)
        np.testing.assert_allclose(x.overdue_unsettled_usd,0)

    def test_deferral_preserves_original_positions_and_catches_up(self):
        x=tba.simulate_ladder({0:100},[0,0],[1,1],[0,0],[0,1])
        self.assertEqual(list(x.closing_unsettled_usd),[100,0])
        self.assertEqual(list(x.settled_usd),[0,100])
        self.assertEqual(list(x.overdue_unsettled_usd),[100,0])

    def test_cancellation_cannot_create_negative_positions(self):
        x=tba.simulate_ladder({5:10},[2],[1],[100],[1])
        self.assertEqual(x.loc[0,'cancelled_usd'],12)
        self.assertEqual(x.loc[0,'closing_unsettled_usd'],0)
        self.assertEqual(x.loc[0,'settled_usd'],0)

    def test_optional_early_settlement_is_capped(self):
        x=tba.simulate_ladder({5:10},[2],[1],[0],[1],[100])
        self.assertEqual(x.loc[0,'settled_early_usd'],12)
        self.assertEqual(x.loc[0,'closing_unsettled_usd'],0)

    def test_invalid_inputs_rejected(self):
        for kwargs in [dict(new_trades=[-1]),dict(new_tenors=[0]),dict(completion_fractions=[1.1]),dict(cancellation_requests=[np.nan])]:
            defaults=dict(initial_cohorts={0:1},new_trades=[0],new_tenors=[1],cancellation_requests=[0],completion_fractions=[1]);defaults.update(kwargs)
            with self.assertRaises(ValueError):tba.simulate_ladder(**defaults)

    def test_seed_reproducibility_and_unrelated_event(self):
        a=tba.run_experiment(42,replications=2);b=tba.run_experiment(42,replications=2)
        for name in a['tables']:pd.testing.assert_frame_equal(a['tables'][name],b['tables'][name])
        daily=a['tables']['tba_daily'];cols=[c for c in daily if c!='scenario_id']
        base=daily[daily.scenario_id.eq('tba_baseline')][cols].reset_index(drop=True)
        control=daily[daily.scenario_id.eq('tba_unrelated_event')][cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(base,control)
        self.assertTrue(all(c['passed'] for c in a['checks']))

    def test_delay_and_earlier_recovery_preserve_units_and_positions(self):
        x=tba.run_experiment(123,replications=1)['tables']['tba_runs'].set_index('scenario_id')
        self.assertGreater(x.loc['tba_prolonged_delay','overdue_notional_days_usd_days'],0)
        self.assertLess(x.loc['tba_earlier_recovery','overdue_notional_days_usd_days'],x.loc['tba_prolonged_delay','overdue_notional_days_usd_days'])
        self.assertGreater(x.loc['tba_prolonged_delay','excess_unsettled_notional_days_usd_days'],0)
        self.assertEqual(x.loc['tba_baseline','initial_unsettled_usd'],562e9*.5)
        self.assertEqual(x.loc['tba_share_25_baseline','initial_unsettled_usd'],562e9*.25)
        self.assertNotIn('cash_obligation_usd',x.columns)

    def test_share_sensitivity_is_a_scale_assumption_not_estimated_exposure(self):
        x=tba.run_experiment(13,replications=1)['tables']['tba_runs'].set_index('scenario_id')
        self.assertAlmostEqual(x.loc['tba_share_75_delay','peak_unsettled_usd']/x.loc['tba_share_25_delay','peak_unsettled_usd'],3)


if __name__=='__main__':unittest.main()
