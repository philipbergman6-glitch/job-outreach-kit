"""Tests for the tracking layer: tracker.py (status vocabulary, closing, application ids,
Trigger durations), board.py (the HTML board) and sweep.py (the inbox-sweep window).
Stdlib only. Each test works in a throwaway copy of the kit."""
import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "tracker", "board", "sweep")
LOG_HEAD = ("| Date | Company | Role | JD URL | Apply channel | CV | Contacts | Emails | Status | Folder |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n")
REPLY_HEAD = "| Company | Role | Got back? | Reply date | Reply from | Outcome | Notes |\n|---|---|---|---|---|---|---|\n"
FOLLOW_HEAD = ("# Follow-ups\n\n| Added | Company | Role | Trigger | Action | Text source | Done |\n"
               "|---|---|---|---|---|---|---|\n")


def log(company, role="PMM", emails="2026-11-01", status="sent", day="2026-11-01", folder=None,
        contacts="", url=None):
    folder = folder if folder is not None else f"outreach/{company.lower()}-{role.lower()}/"
    return (f"| {day} | {company} | {role} | {url or f'https://x/{company}/{role}'} | greenhouse | cv.pdf | "
            f"{contacts} | {emails} | {status} | {folder} |\n")


class Layer(unittest.TestCase):
    TODAY = date(2026, 12, 1)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach").mkdir()
        self.profile = json.loads((REPO / "examples" / "profile.json").read_text(encoding="utf-8"))
        self.save_profile()
        for m in MODS:
            sys.modules.pop(m, None)
        sys.path.insert(0, str(self.root / "scripts"))

    def tearDown(self):
        sys.path.remove(str(self.root / "scripts"))
        for m in MODS:
            sys.modules.pop(m, None)
        self.tmp.cleanup()

    def save_profile(self):
        (self.root / "profile" / "profile.json").write_text(json.dumps(self.profile), encoding="utf-8")

    def tables(self, logs, replies="", follow=""):
        out = self.root / "outreach"
        (out / "log.md").write_text(LOG_HEAD + logs, encoding="utf-8")
        (out / "replies.md").write_text(REPLY_HEAD + replies, encoding="utf-8")
        (out / "followups.md").write_text(FOLLOW_HEAD + follow, encoding="utf-8")

    def mod(self, name):
        return importlib.import_module(name)

    def run_cmd(self, mod, *argv):
        module = importlib.import_module(mod)
        out, err, code = io.StringIO(), io.StringIO(), 0
        old = sys.argv
        sys.argv = [mod + ".py", *argv]
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                module.run(module.main)
        except SystemExit as e:
            code = e.code or 0
        finally:
            sys.argv = old
        return code, out.getvalue(), err.getvalue()

    def ok(self, mod, *argv):
        code, out, err = self.run_cmd(mod, *argv)
        self.assertEqual(code, 0, err + out)
        return out, err

    def refused(self, mod, *argv, why=""):
        code, out, err = self.run_cmd(mod, *argv)
        self.assertEqual(code, 2, f"expected a hard-fail, got exit {code}\n{out}{err}")
        self.assertIn("HARD-FAIL", err)
        self.assertNotIn("Traceback", err)
        self.assertIn(why, err)
        return err

    def due(self):
        return {(r["Company"], r["Action"]): r for r in self.mod("tracker").due(self.TODAY)}


class TriggerDurations(Layer):
    """A Trigger like "3-5 days" counts from the row's Added date and takes the later bound."""

    def test_a_day_range_is_due_at_its_later_bound(self):
        self.tables(log("Acme", emails="held"), "",
                    "| 2026-11-24 | Acme | PMM | 3-5 days | Check the portal | | |\n")
        r = self.due()[("Acme", "Check the portal")]
        self.assertEqual(r["State"], "urgent", "2026-11-24 + 5 days = 2026-11-29, two days before today")
        self.assertIn("2026-11-29", r["Due"])

    def test_weeks_and_business_days(self):
        self.tables(log("Acme", emails="held"), "",
                    "| 2026-11-27 | Acme | PMM | in 2 weeks | Ask about the second round | | |\n"
                    "| 2026-11-27 | Acme | PMM | 1-2 business days | Look for the test link | | |\n")
        d = self.due()
        self.assertIn("2026-12-11", d[("Acme", "Ask about the second round")]["Due"])
        self.assertIn("2026-12-01", d[("Acme", "Look for the test link")]["Due"], "Fri + 2 business days = Tue")
        self.assertEqual(d[("Acme", "Look for the test link")]["State"], "urgent")

    def test_a_range_inside_an_event_waits_on_the_event(self):
        self.tables(log("Acme", emails="held"), "",
                    "| 2026-11-24 | Acme | PMM | Maya answers within 3-5 days of the interview | Log it | | |\n")
        self.assertEqual(self.due()[("Acme", "Log it")]["State"], "waiting")

    def test_a_span_needs_an_added_date(self):
        self.tables(log("Acme", emails="held"), "", "| | Acme | PMM | 3-5 days | Check the portal | | |\n")
        self.refused("tracker", "due", why="Added")

    def test_a_badly_written_date_still_fails(self):
        self.tables(log("Acme", emails="held"), "", "| 2026-11-24 | Acme | PMM | 3/5 | Check the portal | | |\n")
        self.refused("tracker", "due", why="3/5")


class Reapplication(Layer):
    """Follow-ups, replies and closing belong to one application (one log.md row, one folder), not
    to its Company + Role text: an earlier, closed application to the same role hides nothing."""
    OLD = log("Acme", day="2026-01-10", emails="2026-01-10", status="closed", folder="outreach/acme-pmm-jan/")
    NEW = log("Acme", day="2026-11-01", emails="2026-11-01", status="sent", folder="outreach/acme-pmm/")
    REPLIES = "| Acme | PMM | Yes | 2026-01-20 | ATS | Rejected | |\n| Acme | PMM | No | | | Pending | |\n"

    def test_the_new_nudge_is_owed(self):
        self.tables(self.OLD + self.NEW, self.REPLIES,
                    "| 2026-01-10 | Acme | PMM | 2026-01-17 | N1 nudge manager | messages.md | 2026-01-17 |\n"
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")
        r = self.due()[("Acme", "N1 nudge manager")]
        self.assertEqual(r["State"], "overdue")
        self.assertEqual(r["App"], "acme-pmm")

    def test_the_new_application_goes_cold(self):
        self.tables(self.OLD + self.NEW, self.REPLIES,
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | 2026-11-09 |\n")
        self.assertEqual(self.due()[("Acme", "PMM")]["State"], "cold")

    def test_a_follow_up_before_every_application_is_named(self):
        self.tables(self.OLD + self.NEW, self.REPLIES,
                    "| 2025-12-01 | Acme | PMM | 2026-01-17 | N1 nudge manager | messages.md | |\n")
        self.refused("tracker", "due", why="2025-12-01")


class Closing(Layer):
    """Status `closed` ends an application; a rejected, expired, dropped or withdrawn reply ends its
    nudges and its cold verdict. Any other Status is named in a warning, never guessed at."""

    def test_a_closing_reply_stops_the_nudges(self):
        for outcome in ("Rejected", "Expired", "Dropped (role filled)", "withdrawn: took another offer"):
            with self.subTest(outcome=outcome):
                self.tables(log("Acme"), f"| Acme | PMM | Yes | 2026-11-05 | ATS | {outcome} | |\n",
                            "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n"
                            "| 2026-11-05 | Acme | PMM | Maya answers the feedback request | Log it | | |\n")
                d = self.due()
                self.assertNotIn(("Acme", "N1 nudge manager"), d)
                self.assertNotIn(("Acme", "PMM"), d, "never cold")
                self.assertEqual(d[("Acme", "Log it")]["State"], "waiting")

    def test_an_interview_is_not_a_close(self):
        self.tables(log("Acme"), "| Acme | PMM | Yes | 2026-11-05 | Maya | Interview | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")
        self.assertEqual(self.due()[("Acme", "N1 nudge manager")]["State"], "answered")

    def test_a_status_outside_the_vocabulary_is_named(self):
        self.tables(log("Acme", status="rejected 2026-11-06"), "| Acme | PMM | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")
        out, err = self.ok("tracker", "due")
        self.assertIn("WARN", err)
        self.assertIn("row 3 (Acme / PMM)", err)
        self.assertIn("'rejected 2026-11-06'", err)
        self.assertIn("N1 nudge manager", out, "treated as open, so the nudge still shows")

    def test_every_status_in_the_vocabulary_is_quiet(self):
        self.tables("".join(log(f"Co{i}", status=s, emails="held") for i, s in
                            enumerate(("started", "handoff-pending", "submitted", "sent", "closed", "Sent"))))
        out, err = self.ok("tracker", "due")
        self.assertNotIn("WARN", err)


MESSAGES = """---
company: Acme
role: PMM
channel: greenhouse
applied: 2026-11-01
cv: cv.pdf
hm_name: Maya Stone
hm_email: maya.stone@example.com
hm_email_confidence: High
rec_name: Tom Reed
rec_email: {rec_email}
rec_email_confidence: Low
hook: Launch Playbook
---

## T1 manager email
"""


class Spreadsheet(Layer):
    """tracker.py build: applications.csv carries each application's next due action and, per
    recipient, what happened: emailed, nudged, replied."""

    def csv(self):
        import csv
        self.ok("tracker", "build")
        with (self.root / "outreach" / "applications.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def folder(self, slug="acme-pmm", rec_email=""):
        d = self.root / "outreach" / slug
        d.mkdir()
        (d / "messages.md").write_text(MESSAGES.format(rec_email=rec_email), encoding="utf-8")

    def test_next_due_and_per_recipient_state(self):
        self.folder()
        self.tables(log("Acme", contacts="Maya Stone (HM, High); Tom Reed (Rec, Medium)"),
                    "| Acme | PMM | Yes | 2026-11-06 | Maya Stone | Interview | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | 2026-11-08 |\n"
                    "| 2026-11-06 | Acme | PMM | 2099-01-02 | Send the case study | | |\n")
        row = self.csv()[0]
        self.assertEqual(row["Next due"], "2099-01-02")
        self.assertEqual(row["Next action"], "waiting: Send the case study")
        self.assertEqual(row["Manager"], "Maya Stone (email High)")
        self.assertEqual(row["Manager state"], "emailed 2026-11-01, nudged 2026-11-08, replied 2026-11-06")
        self.assertEqual(row["Recruiter"], "Tom Reed (email Low)")
        self.assertEqual(row["Recruiter state"], "no email: LinkedIn only")

    def test_a_held_email_and_an_open_nudge(self):
        self.folder(rec_email="tom.reed@example.com")
        self.tables(log("Acme", emails="held", status="submitted"), "| Acme | PMM | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N2 nudge recruiter | messages.md | |\n")
        row = self.csv()[0]
        self.assertEqual(row["Manager state"], "held")
        self.assertEqual(row["Recruiter state"], "held, nudge 2026-11-08")
        self.assertEqual(row["Next due"], "2026-11-08")

    def test_closed_and_folderless_rows(self):
        self.tables(log("Acme", status="closed") + log("Beta", folder="none"),
                    "| Acme | PMM | No | | | Pending | |\n| Beta | PMM | No | | | Pending | |\n")
        rows = self.csv()
        self.assertEqual(rows[0]["Next action"], "nothing: closed")
        self.assertEqual(rows[0]["Manager"], "")
        self.assertEqual(rows[1]["Id"], "row-4")


if __name__ == "__main__":
    unittest.main()
