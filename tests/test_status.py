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


class Reply(Writer):
    def setUp(self):
        super().setUp()
        self.tables(log("Acme"), "| Acme | PMM | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n"
                    "| 2026-11-01 | Acme | PMM | Tom accepted the LinkedIn invite | T4 Tom | messages.md | |\n")

    def test_a_person_replied(self):
        out, _ = self.ok("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "Interview",
                         "--from", "Tom Lee <tom@acme.com>", "--thread", "18c2f", "--date", TODAY)
        self.assertIn(f"| Acme | PMM | Yes | {TODAY} | Tom Lee <tom@acme.com> | Interview | thread 18c2f |",
                      self.read("replies.md"))
        follow = self.read("followups.md")
        self.assertIn(f"| N1 nudge manager | messages.md | {TODAY} (replied) |", follow)
        self.assertIn("| T4 Tom | messages.md | |", follow)
        self.assertIn("| sent |", self.read("log.md"))

    def test_an_auto_ack_settles_nothing(self):
        self.ok("tracker", "reply", "acme-pmm", "--got", "auto-ack", "--outcome", "Pending", "--date", TODAY)
        self.assertIn(f"| Acme | PMM | Auto-ack only | {TODAY} | | Pending | |", self.read("replies.md"))
        self.assertIn("| N1 nudge manager | messages.md | |", self.read("followups.md"))

    def test_an_auto_ack_never_hides_a_persons_reply(self):
        self.ok("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "Rejected", "--date", "2026-11-20",
                "--thread", "aaa")
        self.ok("tracker", "reply", "acme-pmm", "--got", "auto-ack", "--outcome", "Pending", "--thread", "bbb")
        self.assertIn("| Acme | PMM | Yes | 2026-11-20 | | Rejected | thread aaa; thread bbb |", self.read("replies.md"))

    def test_a_closing_outcome_is_kept_unless_forced(self):
        self.ok("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "Rejected")
        self.refused("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "Interview", why="--force")
        self.ok("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "Interview", "--force", "they reopened it")
        self.assertIn("| Interview |", self.read("replies.md"))

    def test_a_closing_reply_points_at_closing_the_application(self):
        out, _ = self.ok("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "rejected")
        self.assertIn("tracker.py status acme-pmm closed", out)
        self.assertIn("| Rejected |", self.read("replies.md"))

    def test_the_same_thread_twice_is_already(self):
        args = ("reply", "acme-pmm", "--got", "yes", "--outcome", "Interview", "--thread", "x1", "--date", TODAY)
        self.ok("tracker", *args)
        before = self.read("replies.md") + self.read("followups.md")
        out, _ = self.ok("tracker", *args)
        self.assertIn("already", out)
        self.assertEqual(self.read("replies.md") + self.read("followups.md"), before)

    def test_bad_input_is_refused(self):
        self.refused("tracker", "reply", "acme-pmm", "--got", "maybe", "--outcome", "Pending", why="--got")
        self.refused("tracker", "reply", "acme-pmm", "--got", "yes", why="--outcome")
        self.refused("tracker", "reply", "acme-pmm", "--got", "yes", "--outcome", "Under review", why="must start with")


class Followup(Writer):
    def setUp(self):
        super().setUp()
        self.tables(log("Acme"), "| Acme | PMM | No | | | Pending | |\n")

    def test_add_writes_one_row_for_the_application(self):
        self.ok("tracker", "followup", "acme-pmm", "add", "--trigger", "2026-12-08", "--action", "N1 nudge manager",
                "--source", "messages.md", "--date", TODAY)
        self.assertEqual(self.read("followups.md"),
                         FOLLOW_HEAD + f"| {TODAY} | Acme | PMM | 2026-12-08 | N1 nudge manager | messages.md | |\n")
        out, _ = self.ok("tracker", "followup", "acme-pmm", "add", "--trigger", "2026-12-08", "--action",
                         "N1 nudge manager", "--date", TODAY)
        self.assertIn("already", out)
        self.assertEqual(self.read("followups.md").count("N1 nudge"), 1)

    def test_add_refuses_a_trigger_date_written_otherwise(self):
        self.refused("tracker", "followup", "acme-pmm", "add", "--trigger", "8/12", "--action", "N1 nudge manager",
                     why="YYYY-MM-DD")

    def test_add_refuses_a_row_that_would_belong_to_another_application(self):
        self.tables(log("Acme", folder="outreach/acme-1/", day="2026-10-01")
                    + log("Acme", folder="outreach/acme-2/", day="2026-11-01"))
        self.refused("tracker", "followup", "acme-1", "add", "--trigger", "2026-12-08", "--action", "N1 nudge manager",
                     "--date", TODAY, why="acme-2")

    def test_done_marks_the_one_it_names(self):
        self.write("followups.md", FOLLOW_HEAD
                   + "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n"
                   + "| 2026-11-01 | Acme | PMM | 2026-11-08 | N2 nudge recruiter | messages.md | |\n")
        self.refused("tracker", "followup", "acme-pmm", "done", "--action", "N", why="2 open follow-ups")
        self.refused("tracker", "followup", "acme-pmm", "done", "--action", "T4", why="N1 nudge manager")
        self.ok("tracker", "followup", "acme-pmm", "done", "--action", "n2", "--date", TODAY,
                "--note", "recruiter left")
        self.assertIn(f"| N2 nudge recruiter | messages.md | {TODAY} (recruiter left) |", self.read("followups.md"))
        self.assertIn("| N1 nudge manager | messages.md | |", self.read("followups.md"))
        out, _ = self.ok("tracker", "followup", "acme-pmm", "done", "--action", "N2")
        self.assertIn("already", out)


class Normalize(Writer):
    def setUp(self):
        super().setUp()
        self.tables(log("Acme", status="dropped") + log("Beta", status="rejected 2026-11-06")
                    + log("Gamma", status="drafted") + log("Delta", status="Sent") + log("Eps", status="on hold")
                    + log("Zeta", status="expired"),
                    "| Acme | PMM | No | | | Pending | |\n"
                    "| Beta | PMM | Yes | 2026-11-06 | Ann | Rejected (no match) | thread 1a |\n"
                    "| Gamma | PMM | No | | | Pending | |\n| Delta | PMM | No | | | Pending | |\n"
                    "| Eps | PMM | No | | | Pending | |\n| Zeta | PMM | Yes | 2026-11-02 | Bo | Under review | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")

    def files(self):
        return [self.read(n) for n in ("log.md", "replies.md", "followups.md")]

    def test_a_dry_run_lists_each_change_and_writes_nothing(self):
        before = self.files()
        out, _ = self.ok("tracker", "normalize")
        self.assertEqual(self.files(), before)
        for line in ("acme-pmm (Acme / PMM): log.md Status 'dropped' -> 'closed'",
                     "acme-pmm (Acme / PMM): replies.md Outcome 'Pending' -> 'Dropped'",
                     "beta-pmm (Beta / PMM): log.md Status 'rejected 2026-11-06' -> 'closed'",
                     "gamma-pmm (Gamma / PMM): log.md Status 'drafted' -> 'started'",
                     "delta-pmm (Delta / PMM): log.md Status 'Sent' -> 'sent'",
                     "zeta-pmm (Zeta / PMM): replies.md Outcome 'Under review' -> 'Expired'",
                     "eps-pmm (Eps / PMM): Status 'on hold' has no rule"):
            self.assertIn(line, out)
        self.assertNotIn("beta-pmm (Beta / PMM): replies.md", out)  # its Outcome already closes it
        self.assertIn("--apply", out)

    def test_apply_writes_it_and_a_rerun_finds_nothing_more(self):
        self.ok("tracker", "normalize", "--apply", "--date", TODAY)
        logs = self.read("log.md")
        for company, status in (("Acme", "closed"), ("Beta", "closed"), ("Gamma", "started"), ("Delta", "sent"),
                                ("Eps", "on hold"), ("Zeta", "closed")):
            self.assertIn(f"| {company} | PMM |", logs)
            self.assertIn(f"| {status} | outreach/{company.lower()}-pmm/ |", logs)
        replies = self.read("replies.md")
        self.assertIn("| Acme | PMM | No | | | Dropped | |", replies)
        self.assertIn("| Rejected (no match) |", replies)
        self.assertIn(f"| N1 nudge manager | messages.md | {TODAY} (closed) |", self.read("followups.md"))
        before = self.files()
        out, _ = self.ok("tracker", "normalize", "--apply")
        self.assertEqual(self.files(), before)
        self.assertIn("eps-pmm", out)
        self.assertNotIn("acme-pmm", out)

    def test_a_clean_log_has_nothing_to_change(self):
        self.tables(log("Acme"))
        out, _ = self.ok("tracker", "normalize")
        self.assertIn("nothing to change", out)


if __name__ == "__main__":
    unittest.main()
