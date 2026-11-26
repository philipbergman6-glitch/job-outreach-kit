"""Tests for the tracker's writing commands: status, reply, followup, start, normalize. Each one
changes outreach/log.md, replies.md or followups.md through the command line, never by hand, and
leaves every other byte of the file as it was. Stdlib only."""
import unittest

from test_layer import FOLLOW_HEAD, LOG_HEAD, REPLY_HEAD, Layer, log

TODAY = "2026-12-01"


class Writer(Layer):
    def read(self, name):
        return (self.root / "outreach" / name).read_bytes().decode("utf-8")

    def write(self, name, text):
        (self.root / "outreach" / name).write_bytes(text.encode("utf-8"))


class Status(Writer):
    def test_sets_the_status_and_nothing_else(self):
        self.tables(log("Acme", status="submitted") + log("Beta", status="sent"))
        before = self.read("log.md")
        out, _ = self.ok("tracker", "status", "acme-pmm", "sent", "--date", TODAY)
        self.assertIn("sent", out)
        self.assertEqual(self.read("log.md"), before.replace("| submitted |", "| sent |"))

    def test_a_value_outside_the_list_is_refused(self):
        self.tables(log("Acme", status="submitted"))
        before = self.read("log.md")
        self.refused("tracker", "status", "acme-pmm", "rejected", why="not one of started, handoff-pending")
        self.assertEqual(self.read("log.md"), before)

    def test_an_unknown_or_shared_slug_is_refused(self):
        self.tables(log("Acme", status="submitted") + log("Beta", folder="outreach/acme-pmm/")
                    + log("Gamma", folder="none"))
        self.refused("tracker", "status", "nope", "sent", why="no application 'nope'")
        self.refused("tracker", "status", "acme-pmm", "sent", why="Folder of 2 log.md rows")
        self.ok("tracker", "status", "acme-pmm#4", "closed", "--outcome", "Dropped")
        self.ok("tracker", "status", "row-5", "closed", "--outcome", "Dropped")
        self.assertEqual(self.read("log.md").count("| closed |"), 2)

    def test_forward_only_unless_forced_with_a_reason(self):
        self.tables(log("Acme", status="sent"))
        self.refused("tracker", "status", "acme-pmm", "submitted", why="step back")
        self.ok("tracker", "status", "acme-pmm", "submitted", "--force", "emails bounced", "--date", TODAY)
        self.assertIn("| submitted |", self.read("log.md"))
        self.assertIn(f"{TODAY} Status sent -> submitted: emails bounced", self.read("replies.md"))

    def test_a_rerun_changes_nothing_and_says_already(self):
        self.tables(log("Acme", status="submitted"))
        self.ok("tracker", "status", "acme-pmm", "sent")
        before = [self.read(n) for n in ("log.md", "replies.md", "followups.md")]
        out, _ = self.ok("tracker", "status", "acme-pmm", "sent")
        self.assertIn("already", out)
        self.assertEqual([self.read(n) for n in ("log.md", "replies.md", "followups.md")], before)


class Close(Writer):
    def setUp(self):
        super().setUp()
        self.tables(log("Acme", status="sent") + log("Beta", status="sent"),
                    "| Acme | PMM | No | | | Pending | |\n| Beta | PMM | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n"
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N2 nudge recruiter | messages.md | 2026-11-08 |\n"
                    "| 2026-11-01 | Beta | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")

    def test_closing_needs_a_reason(self):
        self.refused("tracker", "status", "acme-pmm", "closed", why="--outcome")

    def test_closing_writes_the_outcome_and_settles_its_follow_ups(self):
        self.ok("tracker", "status", "acme-pmm", "closed", "--outcome", "rejected (role filled)", "--date", TODAY)
        self.assertIn("| Acme | PMM | No | | | Rejected (role filled) | |", self.read("replies.md"))
        self.assertIn("| Beta | PMM | No | | | Pending | |", self.read("replies.md"))
        follow = self.read("followups.md")
        self.assertIn(f"| N1 nudge manager | messages.md | {TODAY} (closed) |", follow)
        self.assertIn("| N2 nudge recruiter | messages.md | 2026-11-08 |", follow)
        self.assertIn("| Beta | PMM | 2026-11-08 | N1 nudge manager | messages.md | |", follow)

    def test_an_outcome_already_closing_is_enough(self):
        self.write("replies.md", REPLY_HEAD + "| Acme | PMM | Yes | 2026-11-20 | Tom | Rejected | |\n"
                   "| Beta | PMM | No | | | Pending | |\n")
        self.ok("tracker", "status", "acme-pmm", "closed")
        self.assertIn("| Rejected |", self.read("replies.md"))

    def test_an_outcome_outside_the_list_is_refused(self):
        self.refused("tracker", "status", "acme-pmm", "closed", "--outcome", "Ghosted", why="must start with")

    def test_outcome_without_closed_is_refused(self):
        self.refused("tracker", "status", "acme-pmm", "sent", "--outcome", "Rejected", why="tracker.py reply")

    def test_a_missing_replies_row_is_added(self):
        self.write("replies.md", REPLY_HEAD)
        self.ok("tracker", "status", "beta-pmm", "closed", "--outcome", "Expired")
        self.assertEqual(self.read("replies.md"), REPLY_HEAD + "| Beta | PMM | No | | | Expired | |\n")

    def test_a_replies_row_that_would_pair_with_another_application_is_refused(self):
        self.tables(log("Acme", folder="outreach/acme-1/") + log("Acme", folder="outreach/acme-2/"))
        self.refused("tracker", "status", "acme-2", "closed", "--outcome", "Expired", why="row 3, not row 4")
        self.assertEqual(self.read("replies.md"), REPLY_HEAD)


class SafeWrites(Writer):
    def test_every_other_byte_is_kept(self):
        self.tables(log("Beta"))
        odd = "|2026-11-02|Acme|PMM|https://x|greenhouse|cv.pdf||  2026-11-03 |submitted|outreach/acme-pmm/|"
        text = "\ufeff# My log\r\n\r\n" + LOG_HEAD.replace("\n", "\r\n") + odd + "\r\n" + \
            log("Beta").replace("\n", "\r\n") + "\r\nNote: Beta was a referral.\r\n"
        (self.root / "outreach" / "log.md").write_bytes(text.encode("utf-8"))
        self.ok("tracker", "status", "acme-pmm", "sent")
        self.assertEqual((self.root / "outreach" / "log.md").read_bytes().decode("utf-8"),
                         text.replace("|submitted|", "| sent |"))
        self.assertEqual(list((self.root / "outreach").glob(".*tmp")), [])

    def test_an_appended_row_goes_under_the_table_not_after_the_notes(self):
        self.tables(log("Acme"))
        self.write("replies.md", REPLY_HEAD + "\nNotes below the table.\n")
        self.ok("tracker", "status", "acme-pmm", "closed", "--outcome", "Dropped")
        self.assertEqual(self.read("replies.md"),
                         REPLY_HEAD + "| Acme | PMM | No | | | Dropped | |\n\nNotes below the table.\n")

    def test_a_wrong_header_names_the_file_and_line(self):
        self.tables(log("Acme"))
        self.write("replies.md", "# Replies\n\n| Company | Got back? |\n|---|---|\n")
        self.refused("tracker", "status", "acme-pmm", "closed", "--outcome", "Dropped", why="replies.md line 3: header")
        self.assertIn("| sent |", self.read("log.md"))

    def test_a_pipe_in_a_value_is_refused(self):
        self.tables(log("Acme"))
        self.refused("tracker", "status", "acme-pmm", "closed", "--outcome", "Rejected | late", why="no '|'")


if __name__ == "__main__":
    unittest.main()
