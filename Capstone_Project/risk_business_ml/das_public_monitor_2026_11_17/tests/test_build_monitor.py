"""Offline core checks. ALL temporary evidence is SYNTHETIC TEST FIXTURE ONLY.

No fixture is written to data/, inputs/, evidence/, or any production register.
Fixture quotations exercise routing rules; they are not collected observations.
"""

from contextlib import contextmanager
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "src" / "build_monitor.py"
sys.path.insert(0, str(MODULE.parent))
SPEC = importlib.util.spec_from_file_location("build_monitor_test_subject", MODULE)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


def synthetic_advisory(identifier="SYNTHETIC_TEST_GHSA_001", **changes):
    row = {
        "ghsa_id": identifier, "summary": "SYNTHETIC TEST FIXTURE ONLY",
        "published_at": "2026-11-10T12:00:00Z", "withdrawn_at": None,
        "html_url": "https://example.invalid/SYNTHETIC_TEST_ONLY/" + identifier,
        "severity": "moderate",
        "vulnerabilities": [{"package": {"name": "org.hyperledger.besu:besu", "ecosystem": "maven"},
                             "vulnerable_version_range": "<= TEST_VERSION", "patched_versions": "TEST_PATCH"}],
    }
    row.update(changes)
    return row


@contextmanager
def synthetic_evidence(*, unavailable=(), launch_quote=True):
    """Build an isolated hash-checked synthetic source manifest."""
    with tempfile.TemporaryDirectory(prefix="SYNTHETIC_monitor_test_") as directory:
        root = Path(directory)
        (root / "inputs").mkdir()
        texts = {
            "launch": "SYNTHETIC TEST ONLY: " + (
                "currently integrated with the Canton Network and DTCC’s private Besu network"
                if launch_quote else "No service relationship is established by this fixture"),
            "solana": "SYNTHETIC TEST ONLY: planned for the second half of 2027",
            "sec_letter": "SYNTHETIC TEST ONLY: the third Friday following each quarter’s end date; "
                          "three years from the date DTC launches operation",
            "besu_advisories": json.dumps([synthetic_advisory()]),
        }
        dates = {"launch": "2026-10-28", "solana": "2026-11-12", "sec_letter": "2025-12-11", "besu_advisories": None}
        sources = []
        for source_id, text in texts.items():
            relative = "inputs/" + source_id + ".txt"
            (root / relative).write_text(text, encoding="utf-8")
            sources.append({
                "source_id": source_id, "url": "https://example.invalid/SYNTHETIC_TEST_ONLY/" + source_id,
                "publication_date": dates[source_id],
                "status": "unavailable" if source_id in unavailable else "retrieved",
                "text_file": relative, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "collected_at_utc": "2026-11-17T12:00:00Z",
            })
        (root / "inputs/source_manifest.json").write_text(json.dumps(sources), encoding="utf-8")
        yield root


class BuildMonitorTest(unittest.TestCase):
    def test_stale_api_interpretation_quarantined_without_disabling_live_monitor(self):
        with synthetic_evidence() as root:
            (root/'results').mkdir()
            sources=json.loads((root/'inputs/source_manifest.json').read_text())
            source=next(x for x in sources if x['source_id']=='launch')
            fact=dict(fact_id='SYNTHETIC_TEST_API_FACT',source_id='launch',
                      source_text_sha256=source['text_sha256'],
                      quote='currently integrated with the Canton Network',statement='SYNTHETIC TEST ONLY')
            path=root/'results/aws_reviewed_facts.json'
            path.write_text(json.dumps({'facts':[fact]}))
            current=monitor.build(root=root)
            self.assertEqual(current['summary']['aws_interpreted_source_checked_facts'],1)
            fact['source_text_sha256']='0'*64
            path.write_text(json.dumps({'facts':[fact]}))
            stale=monitor.build(root=root)
            self.assertEqual(stale['summary']['aws_interpreted_source_checked_facts'],0)
            self.assertEqual(stale['summary']['stale_aws_fact_ids'],['SYNTHETIC_TEST_API_FACT'])
            self.assertEqual(len(stale['findings']),len(current['findings']))

    def test_unsubstantiated_api_quote_rejected(self):
        with synthetic_evidence() as root:
            (root/'results').mkdir()
            source=next(x for x in json.loads((root/'inputs/source_manifest.json').read_text()) if x['source_id']=='launch')
            fact=dict(fact_id='SYNTHETIC_BAD_QUOTE',source_id='launch',source_text_sha256=source['text_sha256'],
                      quote='invented performance measurement',statement='SYNTHETIC TEST ONLY')
            (root/'results/aws_reviewed_facts.json').write_text(json.dumps({'facts':[fact]}))
            with self.assertRaisesRegex(ValueError,'Unsupported AWS reviewed quote'):
                monitor.build(root=root)

    def test_advisories_dates_withdrawals_and_package_filter(self):
        rows = [synthetic_advisory("SYNTHETIC_START", published_at="2026-11-09T00:00:00Z"),
                synthetic_advisory("SYNTHETIC_END", published_at="2026-11-17T23:59:59Z"),
                synthetic_advisory("SYNTHETIC_TOO_EARLY", published_at="2026-11-08T23:59:59Z"),
                synthetic_advisory("SYNTHETIC_FUTURE", published_at="2026-11-18T00:00:00Z"),
                synthetic_advisory("SYNTHETIC_WITHDRAWN", withdrawn_at="2026-11-15T00:00:00Z"),
                synthetic_advisory("SYNTHETIC_WITHDRAWN_LATER", withdrawn_at="2026-11-18T00:00:00Z"),
                synthetic_advisory("SYNTHETIC_WRONG_PACKAGE", vulnerabilities=[{"package": {"name": "another-package"}}])]
        selected = monitor.recent_advisories(rows, date(2026, 11, 9), date(2026, 11, 17))
        self.assertEqual({row["ghsa_id"] for row, _ in selected},
                         {"SYNTHETIC_START", "SYNTHETIC_END", "SYNTHETIC_WITHDRAWN_LATER"})

    def test_third_friday_strictly_after_quarter_and_current_calendar(self):
        self.assertEqual(monitor.third_friday_after(date(2026, 12, 31)), date(2027, 1, 15))
        # A Friday quarter end is not counted as the first following Friday.
        self.assertEqual(monitor.third_friday_after(date(2023, 6, 30)), date(2023, 7, 21))
        self.assertEqual(monitor.third_friday_after(date(2022, 9, 30)), date(2022, 10, 21))
        with synthetic_evidence() as root:
            result = monitor.build(root=root, as_of=date(2026, 11, 17))
        due = next(row for row in result["deadlines"] if row.get("deadline"))
        self.assertEqual(due["deadline"], "2027-01-15")
        self.assertEqual(due["source_id"], "sec_letter")
        self.assertEqual(due["submission_status"], "NOT_PUBLICLY_OBSERVED")
        self.assertEqual(due["calendar_days_remaining"], 59)
        self.assertIn("not assumed missing or late", due["limitation"])
        # Early Q1 must retain the still-upcoming report for the preceding Q4.
        with synthetic_evidence() as root:
            january = monitor.build(root=root, as_of=date(2027, 1, 1))
        next_due = next(row for row in january["deadlines"] if row.get("deadline"))
        self.assertEqual(next_due["deadline"], "2027-01-15")
        self.assertEqual(next_due["reporting_quarter"], "2026Q4")

    def test_unavailable_sources_do_not_become_zero_risk(self):
        with synthetic_evidence(unavailable=("launch", "sec_letter", "besu_advisories")) as root:
            result = monitor.build(root=root)
        metric = next(row for row in result["metrics"] if row["metric_id"] == "besu_advisories_in_window")
        self.assertIsNone(metric["value"])
        self.assertIsNone(result["summary"]["risk_score"])
        self.assertIsNone(result["summary"]["internal_V"])
        self.assertIsNone(result["summary"]["accepted_proxy_V"])
        self.assertEqual(result["deadlines"], [])
        self.assertFalse(any(row["event_type"] == "dependency_security_advisory" for row in result["findings"]))

    def test_solana_planned_gate_and_no_future_publication_lookahead(self):
        with synthetic_evidence() as root:
            current = monitor.build(root=root, as_of=date(2026, 11, 17))
            historical = monitor.build(root=root, as_of=date(2026, 11, 11))
        solana = next(row for row in current["networks"] if row["network_id"] == "Solana")
        self.assertEqual(solana["deployment_status"], "PLANNED_NOT_LIVE_IN_THIS_EVIDENCE")
        self.assertFalse(solana["include_in_current_outage_assessment"])
        self.assertFalse(any(row["network_id"] == "Solana" for row in historical["networks"]))
        self.assertFalse(any(row["source_id"] == "solana" for row in historical["facts"]))
        self.assertFalse(any(row["source_id"] == "solana" for row in historical["findings"]))

    def test_current_findings_unscored_and_relationship_quote_required(self):
        with synthetic_evidence() as root:
            result = monitor.build(root=root)
        self.assertEqual(len(result["findings"]), 2)
        for finding in result["findings"]:
            for key in ("internal_V", "shock_score", "risk_score", "confirmed_DAS_incident"):
                self.assertIsNone(finding[key])
        self.assertFalse(result["summary"]["empirical_validation"])
        self.assertFalse(result["summary"]["automation_enabled"])
        with synthetic_evidence(launch_quote=False) as root:
            no_relationship = monitor.build(root=root)
        self.assertFalse(any(row["event_type"] == "dependency_security_advisory" for row in no_relationship["findings"]))
        with synthetic_evidence() as root:
            exported = []
            for label, timestamp in [("BEFORE", "2026-11-08T14:00:00Z"),
                                     ("IN_WINDOW", "2026-11-10T14:00:00Z"),
                                     ("AFTER", "2026-11-18T14:00:00Z")]:
                exported.append({"order_id": "SYNTHETIC_TEST_ONLY_" + label,
                                 "created_at": timestamp, "updated_at": timestamp,
                                 "status": "Processing", "quantity": 1,
                                 "network": "SYNTHETIC_TEST_ONLY"})
            path = root / "SYNTHETIC_authorized_order_fixture.json"
            path.write_text(json.dumps(exported), encoding="utf-8")
            supplied = monitor.build(root=root, orders_path=path)
        self.assertEqual(supplied["authorized_orders"]["metrics"]["order_count"], 1)
        self.assertEqual(supplied["authorized_orders"]["excluded_rows"], 2)
        self.assertNotIn("no authorized business telemetry was obtained", supplied["summary"]["bounds"].lower())

    def test_hash_tampering_and_path_escape_fail_closed(self):
        with synthetic_evidence() as root:
            source = json.loads((root / "inputs/source_manifest.json").read_text())[0]
            (root / source["text_file"]).write_text("SYNTHETIC TEST TAMPERING", encoding="utf-8")
            with self.assertRaises(ValueError):
                monitor.build(root=root)
            source["text_file"] = "../SYNTHETIC_OUTSIDE_FILE.txt"
            with self.assertRaises(ValueError):
                monitor.read_source(root, source)


if __name__ == "__main__":
    unittest.main()
