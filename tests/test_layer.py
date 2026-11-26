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


class Board(Layer):
    """board.py: outreach/board.html, one row per application, built from the tables alone."""

    def build(self):
        self.ok("board")
        return (self.root / "outreach" / "board.html").read_text(encoding="utf-8")

    def test_one_row_per_application_with_its_stage_and_next_step(self):
        self.tables(log("Acme", contacts="Maya Stone (HM, High); Tom Reed (Rec, Medium)")
                    + log("Beta", emails="held", status="handoff-pending")
                    + log("Gamma", status="closed") + log("Delta"),
                    "| Acme | PMM | No | | | Pending | |\n| Beta | PMM | No | | | Pending | |\n"
                    "| Gamma | PMM | Yes | 2026-11-03 | ATS | Rejected | |\n"
                    "| Delta | PMM | Yes | 2026-11-04 | Maya | Interview | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")
        page = self.build()
        self.assertEqual(page.count('<tr data-stage='), 4)
        acme = page[page.index('data-id="acme-pmm"'):].split("</tr>")[0]
        self.assertIn('data-stage="action"', page[page.rindex("<tr", 0, page.index('data-id="acme-pmm"')):][:80])
        self.assertIn("Maya Stone", acme)
        self.assertIn("High", acme)
        self.assertIn("N1 nudge manager", acme)
        for slug, stage in (("beta-pmm", "action"), ("gamma-pmm", "closed"), ("delta-pmm", "live")):
            start = page.rindex("<tr", 0, page.index(f'data-id="{slug}"'))
            self.assertIn(f'data-stage="{stage}"', page[start:start + 80], slug)
        self.assertIn("Interview", page)

    def test_a_cold_application_needs_the_owner(self):
        self.tables(log("Acme", emails="2026-01-01"), "| Acme | PMM | No | | | Pending | |\n")
        page = self.build()
        self.assertIn('<tr data-stage="action" data-id="acme-pmm"', page)
        self.assertIn("cold", page)

    def test_cells_are_escaped_and_links_are_only_web_links(self):
        self.tables(log("<script>alert(1)</script>", role='A&B "lead"', url="javascript:alert(2)",
                        folder="outreach/x/"), "")
        page = self.build()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("A&amp;B &quot;lead&quot;", page)
        self.assertNotIn('href="javascript:', page)

    def test_works_offline_and_follows_the_theme(self):
        self.tables(log("Acme", url="https://jobs.example.com/1"), "")
        page = self.build()
        self.assertIn('href="https://jobs.example.com/1"', page)
        for external in ("<link", "@import", 'src="http', "fonts.googleapis"):
            self.assertNotIn(external, page)
        self.assertIn("prefers-color-scheme: dark", page)
        self.assertIn('[data-theme="dark"]', page)

    def test_status_warnings_show_on_the_board(self):
        self.tables(log("Acme", status="dropped"), "")
        _, err = self.ok("board")
        self.assertIn("WARN", err)
        self.assertIn("&#x27;dropped&#x27;", (self.root / "outreach" / "board.html").read_text(encoding="utf-8"))

    def test_a_broken_table_builds_nothing(self):
        self.tables(log("Acme"), "| Acme | Other role | No | | | Pending | |\n")
        self.refused("board", why="must match")
        self.assertFalse((self.root / "outreach" / "board.html").exists())


class Sweep(Layer):
    """sweep.py: the inbox-sweep window. begin decides whether to sweep and from when; done stamps it."""
    NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)

    def begin(self, force=False, now=None):
        return self.mod("sweep").begin(force, now or self.NOW)

    def done(self, now=None):
        return self.mod("sweep").done()

    @property
    def last(self):
        return self.root / "outreach" / "sweep-last.txt"

    @property
    def lock(self):
        return self.root / "outreach" / ".sweep-started"

    def test_first_sweep_looks_back_seven_days(self):
        lines = self.begin()
        week = int((self.NOW - timedelta(days=7)).timestamp())
        self.assertTrue(lines[0].startswith(f"SWEEP after:{week} "), lines)
        self.assertTrue(lines[1].startswith(f"QUERY after:{week} -in:sent"), lines)
        self.assertTrue(self.lock.exists())

    def test_done_moves_the_start_into_the_last_sweep(self):
        self.begin()
        self.assertTrue(self.done().startswith("DONE"))
        self.assertFalse(self.lock.exists())
        self.assertEqual(datetime.fromisoformat(self.last.read_text().strip()), self.NOW)
        later = self.NOW + timedelta(hours=5)
        self.assertIn(f"after:{int(self.NOW.timestamp())}", self.begin(now=later)[0])

    def test_a_recent_sweep_is_skipped_unless_forced(self):
        self.last.write_text((self.NOW - timedelta(hours=1)).isoformat() + "\n")
        lines = self.begin()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("SKIP last sweep 60 min ago"), lines)
        self.assertFalse(self.lock.exists())
        self.assertTrue(self.begin(force=True)[0].startswith("SWEEP"))

    def test_a_sweep_in_progress_is_skipped(self):
        self.begin()
        self.assertTrue(self.begin(now=self.NOW + timedelta(minutes=10))[0].startswith("SKIP another sweep"))
        self.assertTrue(self.begin(now=self.NOW + timedelta(minutes=45))[0].startswith("SWEEP"),
                        "a start marker older than 30 minutes is a sweep that died")

    def test_done_without_begin_fails(self):
        self.refused("sweep", "done", why="begin")

    def test_bad_state_files_fail_by_name(self):
        for text, why in (("yesterday", "sweep-last.txt"), ("2026-11-30T10:00:00", "timezone"),
                          ("2027-01-01T00:00:00+00:00", "future")):
            with self.subTest(text=text):
                self.last.write_text(text + "\n")
                self.refused("sweep", "begin", why=why)
                self.assertFalse(self.lock.exists())

    def test_a_bare_date_is_local_midnight(self):
        self.last.write_text("2026-11-20\n")
        local_midnight = datetime(2026, 11, 20).astimezone()
        self.assertIn(f"after:{int(local_midnight.timestamp())}", self.begin()[0])

    def test_senders_to_skip_come_from_the_profile(self):
        self.profile["sweep"] = {"skip_senders": ["alerts@jobs.example.com", "@news.example.org"]}
        self.save_profile()
        query = self.begin()[1]
        self.assertIn("-from:alerts@jobs.example.com", query)
        self.assertIn("-from:news.example.org", query)

    def test_a_bad_skip_list_fails(self):
        for bad in ("alerts@jobs.example.com", ["not an address"], [3], {"x": 1}):
            with self.subTest(bad=bad):
                self.profile["sweep"] = {"skip_senders": bad}
                self.save_profile()
                self.refused("sweep", "begin", why="skip_senders")

    def test_usage(self):
        self.refused("sweep", "begin", "--now")
        self.refused("sweep")


if __name__ == "__main__":
    unittest.main()
