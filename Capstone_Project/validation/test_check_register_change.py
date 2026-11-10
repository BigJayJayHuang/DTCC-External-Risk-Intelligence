"""Offline tests for validation/check_register_change.py (the CI rule for event_register.csv)."""
import subprocess, unittest

from . import check_register_change as K

BASE = ("event_id,title,entered_by,notes\n"
        "EV0001,SEC adopts T+1,human,a\n"
        "EV0002,US T+1 go-live,human,b\n")
LOG = "date_utc,event_id,action,title,proposal_id,reason,by\n2026-11-09T21:29Z,EV0002,removed,x,PE-1,not a US event,Wenqi Cai\n"


class RegisterRule(unittest.TestCase):
    def test_new_empty_columns_and_reviewed_added_row_pass(self):
        head = ("event_id,title,entered_by,notes,review_status,proposal_id\n"
                "EV0001,SEC adopts T+1,human,a,,\n"
                "EV0002,US T+1 go-live,human,b,,\n"
                "EV0003,New event,Wenqi Cai,c,reviewed,PE-2026-11-02-1\n")
        self.assertEqual(K.check(BASE, head), [])

    def test_existing_row_edit_or_filled_new_column_fails(self):
        head = ("event_id,title,entered_by,notes,review_status,proposal_id\n"
                "EV0001,SEC adopts T+1 (edited),human,a,,\n"
                "EV0002,US T+1 go-live,human,b,reviewed,\n")
        problems = K.check(BASE, head)
        self.assertEqual(len(problems), 2)
        self.assertIn("EV0001: existing row changed (title)", problems)
        self.assertIn("EV0002: existing row changed (review_status)", problems)

    def test_added_row_needs_provenance(self):
        head = ("event_id,title,entered_by,notes,review_status,proposal_id\n"
                "EV0001,SEC adopts T+1,human,a,,\nEV0002,US T+1 go-live,human,b,,\n"
                "EV0003,New,,c,reviewed,\n")
        self.assertEqual(K.check(BASE, head), ["EV0003: added row needs non-empty entered_by, proposal_id"])
        legacy = BASE + "EV0003,New,Wenqi Cai,c\n"                                 # no review_status / proposal_id columns
        self.assertEqual(K.check(BASE, legacy), ["EV0003: added row needs non-empty review_status, proposal_id"])

    def test_removed_row_needs_changelog_entry(self):
        head = "event_id,title,entered_by,notes\nEV0001,SEC adopts T+1,human,a\n"
        self.assertEqual(len(K.check(BASE, head)), 1)
        self.assertEqual(K.check(BASE, head, LOG), [])
        self.assertEqual(len(K.check(BASE, head, LOG.replace("Wenqi Cai", ""))), 1)     # entry must say who

    def test_header_changes_other_than_the_two_columns_fail(self):
        for header in ("event_id,title,notes,entered_by\n", "event_id,title,entered_by,notes,extra\n", "event_id,title,entered_by\n"):
            self.assertEqual(len(K.check(BASE, header)), 1, header)

    def test_current_branch_register_passes_against_main(self):
        try:
            base = K.git_show("origin/main", K.REGISTER)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.skipTest("origin/main not available")
        self.assertEqual(K.check(base, (K.PROJECT / K.REGISTER).read_text(encoding="utf-8"),
                                 (K.PROJECT / K.CHANGELOG).read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
