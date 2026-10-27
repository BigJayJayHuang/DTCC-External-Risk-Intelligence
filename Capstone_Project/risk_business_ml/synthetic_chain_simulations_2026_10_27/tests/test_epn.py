"""Independent small-number checks for the hypothetical notification queue."""
import sys
from pathlib import Path
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from epn import processing_finish, simulate_orders, run_experiment


def order(i='a', at=10.0, amount=2.0, valid=True, latency=0.0, pool=20.0):
    return dict(order_id=i, submission_min=at, notional_usd_million=amount,
                initial_valid=valid, correction_latency_min=latency, pool_available_min=pool)


class EPNQueueTests(unittest.TestCase):
    def simulate(self, orders, **kw):
        return simulate_orders(orders, notice_cutoff_min=100, delivery_deadline_min=200,
                               horizon_min=300, processing_capacity_orders_per_min=1,
                               delivery_lag_min=5, **kw)

    def test_on_time_delivery_and_conservation(self):
        events, run = self.simulate([order()])
        self.assertEqual(events.iloc[0].processing_complete_min, 11)
        self.assertEqual(events.iloc[0].delivery_complete_min, 25)
        self.assertEqual(run['overdue_delivery_count'], 0)
        self.assertEqual(run['completed_delivery_notional_usd_million'], 2)
        self.assertEqual(run['notional_conservation_error_usd_million'], 0)

    def test_error_repaired_before_cutoff_is_not_failed_delivery(self):
        e, r = self.simulate([order(valid=False, latency=20)])
        self.assertEqual(r['initial_rejection_count'], 1)
        self.assertEqual(e.iloc[0].valid_notification_min, 30)
        self.assertEqual(e.iloc[0].delivery_complete_min, 36)
        self.assertEqual(r['late_message_count'], 0)
        self.assertEqual(r['unfinished_delivery_count'], 0)

    def test_late_notice_does_not_automatically_mean_late_delivery(self):
        e, r = self.simulate([order(at=105, pool=100)])
        self.assertEqual(r['late_message_count'], 1)
        self.assertEqual(e.iloc[0].delivery_complete_min, 111)
        self.assertEqual(r['overdue_delivery_count'], 0)

    def test_outage_after_completion_has_no_effect(self):
        a, _ = self.simulate([order()])
        b, _ = self.simulate([order()], outage=(100, 200))
        pd.testing.assert_frame_equal(a, b)

    def test_unrelated_outage_has_no_effect(self):
        a, _ = self.simulate([order()])
        b, _ = self.simulate([order()], outage=(0, 1000), outage_applies=False)
        pd.testing.assert_frame_equal(a, b)

    def test_processing_pauses_and_resumes_remaining_work(self):
        self.assertEqual(processing_finish(0, 10, (5,25)), 30)
        self.assertEqual(processing_finish(15, 10, (5,25)), 35)
        self.assertEqual(processing_finish(30, 10, (5,25)), 40)

    def test_known_fifo_queue_and_deadline_boundary(self):
        e, r = simulate_orders([order('a',0,1,pool=0),order('b',0,2,pool=0),order('c',0,3,pool=0)],
            notice_cutoff_min=10, delivery_deadline_min=40, horizon_min=100,
            processing_capacity_orders_per_min=.1, delivery_lag_min=0, outage=(5,25))
        self.assertEqual(e.processing_complete_min.tolist(), [30,40,50])
        self.assertEqual(r['delayed_completed_delivery_count'],1)
        self.assertEqual(r['overdue_notional_usd_million'],3)
        self.assertEqual(r['peak_system_backlog_orders'],3)
        self.assertEqual(r['mean_delay_lower_bound_min'],10/3)

    def test_unfinished_is_separate_from_delayed_completed(self):
        e, r = self.simulate([order()], outage=(0,400))
        self.assertIsNone(e.iloc[0].delivery_complete_min)
        self.assertEqual(r['unfinished_delivery_count'],1)
        self.assertEqual(r['delayed_completed_delivery_count'],0)
        self.assertEqual(r['mean_delay_lower_bound_min'],100)
        self.assertEqual(r['unfinished_notional_usd_million'],2)

    def test_pool_unavailable_does_not_disappear_from_conservation(self):
        _, r = self.simulate([order(pool=None)])
        self.assertEqual(r['unfinished_delivery_count'],1)
        self.assertEqual(r['completed_delivery_notional_usd_million'],0)
        self.assertEqual(r['notional_conservation_error_usd_million'],0)

    def test_invalid_or_duplicate_orders_are_rejected(self):
        with self.assertRaises(ValueError): self.simulate([order(),order()])
        with self.assertRaises(ValueError): self.simulate([order(amount=-1)])
        with self.assertRaises(ValueError): processing_finish(0, float('nan'))

    def test_experiment_is_reproducible_and_controls_pass(self):
        a=run_experiment(7,replications=3);b=run_experiment(7,replications=3)
        for name,frame in a['tables'].items():pd.testing.assert_frame_equal(frame,b['tables'][name])
        self.assertTrue(all(c['passed'] for c in a['checks']))
        self.assertEqual(len(a['tables']['epn_runs']),24)


if __name__=='__main__':unittest.main()
