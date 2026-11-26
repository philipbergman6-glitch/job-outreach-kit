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


if __name__ == "__main__":
    unittest.main()
