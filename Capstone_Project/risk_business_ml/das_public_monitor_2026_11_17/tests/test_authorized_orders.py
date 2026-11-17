"""Synthetic fixtures ONLY: no observed DTS data, no model calibration claims."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "src" / "authorized_orders.py"
SPEC = importlib.util.spec_from_file_location("authorized_orders", MODULE)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def synthetic_order(order_id="SYNTHETIC_TEST_ONLY_001", **changes):
    row = dict(order_id=order_id, created_at="2026-11-10T14:00:00Z",
               updated_at="2026-11-10T14:05:00Z", status="Processing",
               quantity=1, network="SYNTHETIC_TEST_NETWORK", confirmed_completed_at=None)
    row.update(changes)
    return row


class AuthorizedOrdersTest(unittest.TestCase):
    def test_no_data_preserves_null_metrics(self):
        result = adapter.analyze_authorized_orders()
        self.assertEqual(result["availability"], "awaiting_authorized_data")
        self.assertTrue(all(value is None for value in result["metrics"].values()))

    def test_real_template_is_header_only(self):
        path = MODULE.parents[1] / "data" / "authorized_orders_template.csv"
        self.assertEqual(adapter.load_orders(path), [])
        self.assertEqual(adapter.analyze_authorized_orders(path)["availability"], "awaiting_authorized_data")

    def test_latest_snapshot_deduplicated(self):
        early = synthetic_order()
        late = synthetic_order(status="Completed", updated_at="2026-11-10T14:10:00Z",
                               confirmed_completed_at="2026-11-10T14:09:00Z")
        result = adapter.summarize_orders([late, early, late])
        self.assertEqual(result["metrics"]["order_count"], 1)
        self.assertEqual(result["metrics"]["completed_count"], 1)
        self.assertEqual(result["duplicate_rows_removed"], 2)
        self.assertEqual(result["metrics"]["mean_completed_duration_seconds"], 540)

    def test_updated_at_never_becomes_completion(self):
        result = adapter.summarize_orders([synthetic_order(status="Completed")])
        self.assertEqual(result["metrics"]["completed_count"], 1)
        self.assertEqual(result["metrics"]["completed_duration_sample_count"], 0)
        self.assertIsNone(result["metrics"]["mean_completed_duration_seconds"])

    def test_confirmed_http202_and_wrong_case_are_unknown(self):
        rows = [synthetic_order(f"SYNTHETIC_TEST_ONLY_{i}", status=status)
                for i, status in enumerate(["Confirmed", "202", "completed", "New", "Declined"])]
        result = adapter.summarize_orders(rows)
        self.assertEqual(result["metrics"]["unknown_status_count"], 5)
        self.assertEqual(result["metrics"]["completed_count"], 0)
        self.assertIn("Confirmed", result["unknown_status_counts"])

    def test_explicit_order_status_mapping(self):
        rows = [synthetic_order(f"SYNTHETIC_TEST_ONLY_{i}", status=status)
                for i, status in enumerate(["Processing", "Completed", "Failed"])]
        result = adapter.summarize_orders(rows)
        for key in ("completed_count", "failed_count", "processing_count"):
            self.assertEqual(result["metrics"][key], 1)
        self.assertEqual(result["metrics"]["terminal_failure_rate"], 0.5)

    def test_asof_window_excludes_future_update_uses_old_snapshot(self):
        rows = [synthetic_order(), synthetic_order(status="Completed", updated_at="2026-11-11T00:01:00Z")]
        result = adapter.summarize_orders(rows, window_start="2026-11-10T00:00:00Z", window_end="2026-11-11T00:00:00Z")
        self.assertEqual(result["metrics"]["processing_count"], 1)
        self.assertEqual(result["metrics"]["completed_count"], 0)
        self.assertEqual(result["excluded_rows"], 1)

    def test_half_open_created_window_and_no_usable_orders(self):
        result = adapter.summarize_orders([synthetic_order()], window_start="2026-11-11T00:00:00Z")
        self.assertEqual(result["availability"], "no_usable_orders_in_window")
        self.assertIsNone(result["metrics"]["order_count"])

    def test_conflicting_latest_snapshots_quarantined(self):
        result = adapter.summarize_orders([synthetic_order(), synthetic_order(status="Failed")])
        self.assertEqual(len(result["conflicting_order_ids"]), 1)
        self.assertEqual(result["orders"], [])

    def test_negative_and_inconsistent_completion_not_timed(self):
        rows = [synthetic_order("SYNTHETIC_TEST_ONLY_BAD_TIME", status="Completed", confirmed_completed_at="2026-11-10T13:59:00Z"),
                synthetic_order("SYNTHETIC_TEST_ONLY_NOT_COMPLETE", confirmed_completed_at="2026-11-10T14:03:00Z")]
        result = adapter.summarize_orders(rows)
        self.assertEqual(result["metrics"]["completed_duration_sample_count"], 0)
        self.assertEqual(len(result["data_quality_issues"]), 2)

    def test_naive_time_invalid_not_assumed_local(self):
        result = adapter.summarize_orders([synthetic_order(created_at="2026-11-10T14:00:00")])
        self.assertEqual(result["invalid_rows"], 1)
        self.assertIsNone(result["metrics"]["completed_count"])

    def test_raw_order_alias_and_network(self):
        raw = {"orderId": "SYNTHETIC_TEST_ONLY_RAW", "createdAt": "2026-11-10T09:00:00-05:00",
               "updatedAt": "2026-11-10T14:05:00Z", "status": "Completed", "quantity": 1,
               "fromWallet": {"network": "DTC_Classic"}, "toWallet": {"network": "Besu"}}
        result = adapter.summarize_orders([raw])
        self.assertEqual(result["orders"][0]["network"], "Besu")
        self.assertEqual(result["orders"][0]["created_at"], "2026-11-10T14:00:00Z")

    def test_async_operation_is_not_order(self):
        result = adapter.summarize_orders([{"id": "SYNTHETIC_ASYNC_ONLY", "resourceId": "SYNTHETIC_ORDER", "status": "Completed"}])
        self.assertEqual(result["invalid_rows"], 1)
        self.assertIsNone(result["metrics"]["completed_count"])

    def test_json_flat_array_only_and_csv_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic_fixture.json"
            path.write_text(json.dumps([synthetic_order()]))
            self.assertEqual(len(adapter.load_orders(path)), 1)
            path.write_text(json.dumps({"items": [synthetic_order()]}))
            with self.assertRaises(ValueError):
                adapter.load_orders(path)
            path = Path(directory) / "synthetic_fixture.csv"
            path.write_text("id,status\nSYNTHETIC_ONLY,Completed\n")
            with self.assertRaises(ValueError):
                adapter.load_orders(path)

    def test_invalid_window_and_quantity(self):
        with self.assertRaises(ValueError):
            adapter.summarize_orders([], window_start="2026-11-11T00:00:00Z", window_end="2026-11-10T00:00:00Z")
        result = adapter.summarize_orders([synthetic_order(quantity="NaN")])
        self.assertEqual(result["invalid_rows"], 1)


if __name__ == "__main__":
    unittest.main()
