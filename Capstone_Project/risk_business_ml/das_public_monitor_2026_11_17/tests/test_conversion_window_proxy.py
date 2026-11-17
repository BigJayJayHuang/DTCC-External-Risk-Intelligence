"""Offline tests of the candidate conversion-window proxy, not service uptime.

Calendar entries below are SYNTHETIC TEST FIXTURES ONLY. Their dtcc.com URLs
exercise source-validation rules; they are not collected or verified calendars.
No requests, paid APIs, production inputs, or observed business records are used.
"""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo


MODULE = Path(__file__).resolve().parents[1] / "src" / "conversion_window_proxy.py"
sys.path.insert(0, str(MODULE.parent))
SPEC = importlib.util.spec_from_file_location("conversion_window_proxy_test_subject", MODULE)
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)
IMPORT_SPEC = importlib.util.spec_from_file_location(
    "import_conversion_proxy_test_subject", MODULE.parent / "import_conversion_proxy.py")
proxy_import = importlib.util.module_from_spec(IMPORT_SPEC)
IMPORT_SPEC.loader.exec_module(proxy_import)

NY = ZoneInfo("America/New_York")
SYNTHETIC_SOURCE = "https://www.dtcc.com/SYNTHETIC_TEST_ONLY/conversion-calendar"


def synthetic_calendar():
    """A small complete fixture whose publication precedes its evaluation."""
    return {
        "review_status": "REVIEWED_OFFICIAL_DTS_CONVERSION_CALENDAR",
        "scope": "DTS_CONVERSION_ORDER_SUBMISSION",
        "coverage_start": "2026-11-17",
        "coverage_end": "2026-11-18",
        "coverage_source_url": SYNTHETIC_SOURCE,
        "coverage_published_at": "2026-11-01T00:00:00Z",
        "days": {
            day: {
                "windows": [["02:00", "18:00"]],
                "source_url": SYNTHETIC_SOURCE,
                "published_at": "2026-11-01T00:00:00Z",
            }
            for day in ("2026-11-17", "2026-11-18")
        },
    }


class ParseInstantTest(unittest.TestCase):
    def test_equivalent_instants_normalize_to_utc(self):
        expected = datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc)
        values = [
            "2026-11-17T15:00:00Z",
            "2026-11-17T10:00:00-05:00",
            "2026-11-17T23:00:00+08:00",
            datetime(2026, 11, 17, 10, tzinfo=NY),
        ]
        for value in values:
            with self.subTest(value=value):
                actual = proxy.parse_instant(value)
                self.assertEqual(actual, expected)
                self.assertEqual(actual.utcoffset().total_seconds(), 0)

    def test_naive_or_invalid_times_are_rejected(self):
        for value in ["2026-11-17", "2026-11-17T10:00:00",
                      datetime(2026, 11, 17, 10), "not a timestamp"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                proxy.parse_instant(value)


class BaselineAccessTest(unittest.TestCase):
    def test_weekday_window_is_open_at_two_and_closed_at_eighteen(self):
        cases = [
            ("2026-11-17T01:59:59-05:00", False, 1 / 3600),
            ("2026-11-17T02:00:00-05:00", True, 0),
            ("2026-11-17T17:59:59-05:00", True, 0),
            ("2026-11-17T18:00:00-05:00", False, 8),
            ("2026-11-17T18:00:01-05:00", False, 8 - 1 / 3600),
        ]
        for at, is_open, expected_hours in cases:
            with self.subTest(at=at):
                result = proxy.baseline_access(at)
                self.assertIs(result["baseline_submission_window_open"], is_open)
                self.assertAlmostEqual(result["baseline_wait_hours"], expected_hours, places=6)

    def test_next_opening_retains_new_york_offset(self):
        result = proxy.baseline_access("2026-11-17T18:00:00-05:00")
        opening = datetime.fromisoformat(result["baseline_next_open_local"])
        self.assertEqual(opening.isoformat(), "2026-11-18T02:00:00-05:00")

    def test_weekend_wait_is_elapsed_time_across_dst_transitions(self):
        cases = [
            # The clock moves back on Sunday 2026-11-01: one extra elapsed hour.
            ("2026-10-30T18:00:00-04:00", 57, "2026-11-02T02:00:00-05:00"),
            # An ordinary weekend still contains 56 hours until Monday 02:00.
            ("2026-11-13T18:00:00-05:00", 56, "2026-11-16T02:00:00-05:00"),
            # The clock moves forward on Sunday 2027-03-14: one fewer hour.
            ("2027-03-12T18:00:00-05:00", 55, "2027-03-15T02:00:00-04:00"),
        ]
        for at, hours, next_open in cases:
            with self.subTest(at=at):
                result = proxy.baseline_access(at)
                self.assertIs(result["baseline_submission_window_open"], False)
                self.assertEqual(result["baseline_wait_hours"], hours)
                self.assertEqual(
                    datetime.fromisoformat(result["baseline_next_open_local"]).isoformat(),
                    next_open,
                )

    def test_repeated_fall_back_hour_is_not_collapsed(self):
        first = proxy.baseline_access("2026-11-01T01:30:00-04:00")
        second = proxy.baseline_access("2026-11-01T01:30:00-05:00")
        self.assertEqual(first["baseline_wait_hours"], 25.5)
        self.assertEqual(second["baseline_wait_hours"], 24.5)

    def test_utc_and_local_inputs_produce_identical_access(self):
        self.assertEqual(
            proxy.baseline_access("2026-11-17T23:00:00Z"),
            proxy.baseline_access("2026-11-17T18:00:00-05:00"),
        )


class CandidateScoreTest(unittest.TestCase):
    def test_every_threshold_is_assigned_without_gaps(self):
        cases = [
            (0, 1),
            (math.nextafter(0.0, math.inf), 2),
            (math.nextafter(8.0, -math.inf), 2),
            (8, 2),
            (math.nextafter(8.0, math.inf), 3),
            (24, 3),
            (math.nextafter(24.0, math.inf), 4),
            (48, 4),
            (math.nextafter(48.0, math.inf), 5),
            (57, 5),
        ]
        for hours, expected in cases:
            with self.subTest(hours=hours):
                self.assertEqual(proxy.candidate_score(hours), expected)

    def test_negative_and_nonfinite_waits_cannot_be_scored(self):
        for hours in [-1, -0.000001, float("nan"), float("inf"), -float("inf")]:
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                proxy.candidate_score(hours)


class EvaluateEvidenceBoundariesTest(unittest.TestCase):
    def assert_not_accepted_or_risk(self, result):
        for field in ("internal_V", "accepted_proxy_V", "risk_score"):
            with self.subTest(field=field):
                self.assertIn(field, result)
                self.assertIsNone(result[field])

    def test_prelaunch_is_determined_by_new_york_date_without_backfill(self):
        # UTC is already October 29, but New York is still October 28.
        before = proxy.evaluate("2026-10-29T03:59:59Z")
        self.assertEqual(before["state"], "BEFORE_SUPPORTED_BASELINE")
        self.assertIsNone(before["baseline_wait_hours"])
        self.assertIsNone(before["candidate_proxy_v_score_1_5"])
        self.assertIsNone(before["calendar_confirmed_wait_hours"])
        self.assert_not_accepted_or_risk(before)

        at_launch = proxy.evaluate("2026-10-29T04:00:00Z")
        self.assertNotEqual(at_launch["state"], "BEFORE_SUPPORTED_BASELINE")
        self.assertEqual(at_launch["baseline_wait_hours"], 2)
        self.assertEqual(at_launch["candidate_proxy_v_score_1_5"], 2)
        self.assert_not_accepted_or_risk(at_launch)

    def test_missing_calendar_leaves_confirmation_unknown_even_when_baseline_open(self):
        for at, expected_wait, score in [
            ("2026-11-17T10:00:00-05:00", 0, 1),
            ("2026-11-17T18:00:00-05:00", 8, 2),
            ("2026-10-30T18:00:00-04:00", 57, 5),
        ]:
            with self.subTest(at=at):
                result = proxy.evaluate(at)
                self.assertEqual(result["baseline_wait_hours"], expected_wait)
                self.assertEqual(result["candidate_proxy_v_score_1_5"], score)
                self.assertIsNone(result["calendar_confirmed_wait_hours"])
                self.assert_not_accepted_or_risk(result)

    def test_policy_cannot_backfill_before_the_supported_evidence_floor(self):
        policy = {"first_supported_local_date": "2020-01-01"}
        result = proxy.evaluate("2026-10-28T10:00:00-04:00", policy=policy)
        self.assertEqual(result["state"], "BEFORE_SUPPORTED_BASELINE")
        self.assertIsNone(result["baseline_wait_hours"])
        self.assertIsNone(result["candidate_proxy_v_score_1_5"])
        self.assert_not_accepted_or_risk(result)

    def test_unconfirmed_calendar_does_not_become_zero_or_accepted_v(self):
        calendar = {
            "coverage_start": None, "coverage_end": None,
            "coverage_source_url": None, "days": {},
        }
        result = proxy.evaluate("2026-11-17T18:00:00-05:00", calendar=calendar)
        self.assertEqual(result["baseline_wait_hours"], 8)
        self.assertIsNone(result["calendar_confirmed_wait_hours"])
        self.assertEqual(result["candidate_proxy_v_score_1_5"], 2)
        self.assert_not_accepted_or_risk(result)

    def test_equivalent_instants_produce_identical_evaluations(self):
        self.assertEqual(
            proxy.evaluate("2026-11-17T23:00:00Z"),
            proxy.evaluate(datetime(2026, 11, 17, 18, tzinfo=NY)),
        )

    def test_open_and_closed_windows_do_not_claim_service_health_or_observed_latency(self):
        for at in ["2026-11-17T10:00:00-05:00", "2026-11-17T20:00:00-05:00"]:
            with self.subTest(at=at):
                result = proxy.evaluate(at)
                self.assertIsNone(result["service_health"])
                self.assertIsNone(result["actual_submission_or_completion_delay_hours"])
                self.assertIs(result["operating_telemetry"], False)
                self.assertIs(result["historical_point_in_time_verified"], False)
                self.assertIs(result["quarterly_internal_v_replacement"], False)
                self.assertEqual(result["event_applicability"], "NOT_ASSESSED")
                self.assertEqual(result["measurement_type"], "PUBLIC_RULE_DERIVED_WEEKLY_BASELINE")
                self.assertIn("PROPOSED", result["score_status"])
                self.assert_not_accepted_or_risk(result)

    def test_holiday_is_not_guessed_from_a_different_markets_calendar(self):
        # Thanksgiving has no applicable conversion-calendar evidence here.
        result = proxy.evaluate("2026-11-26T12:00:00-05:00")
        self.assertIs(result["baseline_submission_window_open"], True)
        self.assertEqual(result["baseline_wait_hours"], 0)
        self.assertIsNone(result["calendar_confirmed_wait_hours"])
        self.assert_not_accepted_or_risk(result)


class CalendarEvidenceTest(unittest.TestCase):
    def assert_unconfirmed(self, result):
        self.assertIsNone(result["calendar_confirmed_wait_hours"])
        self.assertIsNone(result["calendar_confirmed_next_open_local"])
        self.assertNotIn("CONDITIONAL_ON_INPUT", result["calendar_status"])
        for field in ("internal_V", "accepted_proxy_V", "risk_score", "service_health"):
            self.assertIsNone(result[field])

    def test_reviewed_complete_fixture_is_still_conditional_on_input(self):
        result = proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=synthetic_calendar())
        self.assertEqual(result["calendar_confirmed_wait_hours"], 7)
        self.assertEqual(result["calendar_confirmed_next_open_local"], "2026-11-18T02:00:00-05:00")
        self.assertIn("CONDITIONAL_ON_INPUT", result["calendar_status"])
        for field in ("internal_V", "accepted_proxy_V", "risk_score", "service_health"):
            self.assertIsNone(result[field])
        self.assertIs(result["operating_telemetry"], False)

    def test_explicit_closure_changes_calendar_wait_without_rewriting_baseline(self):
        calendar = synthetic_calendar()
        calendar["days"]["2026-11-17"]["windows"] = []
        result = proxy.evaluate("2026-11-17T10:00:00-05:00", calendar=calendar)
        self.assertEqual(result["baseline_wait_hours"], 0)
        self.assertEqual(result["calendar_confirmed_wait_hours"], 16)
        self.assertEqual(result["candidate_proxy_v_score_1_5"], 1)
        self.assertIsNone(result["accepted_proxy_V"])

    def test_delayed_next_opening_uses_override_instead_of_weekday_default(self):
        calendar = synthetic_calendar()
        calendar["days"]["2026-11-18"]["windows"] = [["04:00", "18:00"]]
        result = proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar)
        self.assertEqual(result["baseline_wait_hours"], 7)
        self.assertEqual(result["calendar_confirmed_wait_hours"], 9)
        self.assertEqual(result["calendar_confirmed_next_open_local"], "2026-11-18T04:00:00-05:00")

    def test_review_scope_and_coverage_metadata_cannot_be_omitted(self):
        required = ["review_status", "scope", "coverage_start", "coverage_end",
                    "coverage_source_url", "coverage_published_at"]
        for missing in required:
            with self.subTest(missing=missing):
                calendar = synthetic_calendar()
                del calendar[missing]
                self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))
        calendar = synthetic_calendar()
        calendar["scope"] = "DTC_SETTLEMENT_CALENDAR"
        self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))

    def test_isolated_dated_entries_cannot_establish_complete_coverage(self):
        calendar = synthetic_calendar()
        calendar.update(coverage_start=None, coverage_end=None)
        calendar["days"]["2026-11-17"]["windows"] = []
        self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))

    def test_query_and_next_opening_must_both_be_inside_declared_coverage(self):
        for at in ["2026-11-16T19:00:00-05:00", "2026-11-19T10:00:00-05:00"]:
            with self.subTest(at=at):
                self.assert_unconfirmed(proxy.evaluate(at, calendar=synthetic_calendar()))
        calendar = synthetic_calendar()
        calendar["coverage_end"] = "2026-11-17"
        self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))

    def test_future_coverage_or_day_publication_cannot_be_used_in_historical_query(self):
        for target in ("coverage", "2026-11-17", "2026-11-18"):
            with self.subTest(target=target):
                calendar = synthetic_calendar()
                if target == "coverage":
                    calendar["coverage_published_at"] = "2026-11-18T12:00:00Z"
                else:
                    calendar["days"][target]["published_at"] = "2026-11-18T12:00:00Z"
                self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))

    def test_missing_override_provenance_cannot_confirm_a_day(self):
        for field in ("source_url", "published_at"):
            with self.subTest(field=field):
                calendar = synthetic_calendar()
                del calendar["days"]["2026-11-18"][field]
                self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))

    def test_untrusted_or_spoofed_source_urls_are_not_official_evidence(self):
        urls = [
            "https://example.invalid/SYNTHETIC_TEST_ONLY",
            "https://www.dtcc.com.example.invalid/SYNTHETIC_TEST_ONLY",
            "https://dtcc.com@example.invalid/SYNTHETIC_TEST_ONLY",
            "https://example.invalid/?source=dtcc.com",
            "http://www.dtcc.com/SYNTHETIC_TEST_ONLY",
        ]
        for url in urls:
            for target in ("coverage", "day"):
                with self.subTest(url=url, target=target):
                    calendar = synthetic_calendar()
                    if target == "coverage":
                        calendar["coverage_source_url"] = url
                    else:
                        calendar["days"]["2026-11-18"]["source_url"] = url
                    self.assert_unconfirmed(proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar))

    def test_malformed_or_overlapping_windows_fail_closed(self):
        windows = [
            [["18:00", "02:00"]],
            [["02:00", "12:00"], ["11:00", "18:00"]],
            [["02:00"]],
            "02:00-18:00",
        ]
        for invalid in windows:
            with self.subTest(windows=invalid), self.assertRaises(ValueError):
                calendar = synthetic_calendar()
                calendar["days"]["2026-11-18"]["windows"] = invalid
                proxy.evaluate("2026-11-17T19:00:00-05:00", calendar=calendar)

    def test_nonexistent_or_ambiguous_dst_override_times_are_rejected(self):
        cases = [
            ("2027-03-13T18:00:00-05:00", "2027-03-13", "2027-03-15",
             "2027-03-14", [["02:00", "18:00"]]),
            ("2026-10-31T18:00:00-04:00", "2026-10-31", "2026-11-02",
             "2026-11-01", [["01:30", "18:00"]]),
        ]
        for at, first, last, override_day, windows in cases:
            with self.subTest(at=at), self.assertRaises(ValueError):
                calendar = deepcopy(synthetic_calendar())
                calendar.update(coverage_start=first, coverage_end=last,
                                coverage_published_at="2026-10-01T00:00:00Z")
                calendar["days"] = {
                    override_day: {
                        "windows": windows,
                        "source_url": SYNTHETIC_SOURCE,
                        "published_at": "2026-10-01T00:00:00Z",
                    }
                }
                proxy.evaluate(at, calendar=calendar)


class ImportPayloadSafetyTest(unittest.TestCase):
    """Exercise only in-memory validation; never invoke any database importer."""

    def baseline_payload(self):
        row = proxy.evaluate("2026-11-17T10:00:00-05:00")
        row.update(metric_id="das05_conversion_access_hourly", value=0,
                   unit="hours_until_nominal_order_submission_window",
                   source_ids=["SYNTHETIC_TEST_ONLY_SOURCE"])
        return {"sources": [], "metrics": [row]}

    def test_correct_baseline_payload_is_accepted_without_mutation(self):
        payload = self.baseline_payload()
        before = deepcopy(payload)
        proxy_import.validate_payload(payload)
        self.assertEqual(payload, before)

    def test_scenario_fields_are_forbidden_even_if_their_values_are_null(self):
        for field, example in [
            ("scenario_id", "SYNTHETIC_TEST_ONLY_SCENARIO"),
            ("assumed_shock_score", 3),
            ("illustrative_priority_index", 9),
        ]:
            for value in (None, example):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    payload = self.baseline_payload()
                    payload["metrics"][0][field] = value
                    proxy_import.validate_payload(payload)

    def test_internal_accepted_or_risk_scores_cannot_be_imported_even_as_zero(self):
        for field in ("internal_V", "accepted_proxy_V", "risk_score"):
            for value in (0, 3):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    payload = self.baseline_payload()
                    payload["metrics"][0][field] = value
                    proxy_import.validate_payload(payload)

    def test_unknown_metric_or_policy_is_rejected(self):
        for field, value in [("metric_id", "SYNTHETIC_TEST_ONLY_UNREVIEWED_METRIC"),
                             ("policy_id", "SYNTHETIC_TEST_ONLY_OTHER_POLICY")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                payload = self.baseline_payload()
                payload["metrics"][0][field] = value
                proxy_import.validate_payload(payload)

    def test_every_row_is_checked_after_an_initial_valid_row(self):
        payload = self.baseline_payload()
        invalid = deepcopy(payload["metrics"][0])
        invalid["assumed_shock_score"] = 3
        payload["metrics"].append(invalid)
        with self.assertRaises(ValueError):
            proxy_import.validate_payload(payload)

    def test_telemetry_and_quarterly_replacement_claims_are_rejected(self):
        for field in ("operating_telemetry", "quarterly_internal_v_replacement"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                payload = self.baseline_payload()
                payload["metrics"][0][field] = True
                proxy_import.validate_payload(payload)

    def test_accepted_events_or_other_record_categories_cannot_enter_proxy_import(self):
        for category in ("findings", "facts", "scope", "networks", "deadlines"):
            with self.subTest(category=category), self.assertRaises(ValueError):
                payload = self.baseline_payload()
                payload[category] = [{"id": "SYNTHETIC_TEST_ONLY_NON_PROXY_RECORD"}]
                proxy_import.validate_payload(payload)

    def test_empty_or_missing_metrics_cannot_pass_as_an_import(self):
        for payload in ({}, {"metrics": []}, {"metrics": None}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                proxy_import.validate_payload(payload)


if __name__ == "__main__":
    unittest.main()
