"""Tests for scripts/watch.py: the watchlist of job boards read again on every run, showing only
postings not seen before. Stdlib only, no network: each test works in a throwaway copy of the kit
and the boards answer from canned replies shaped like the real APIs (see tests/test_jobs.py)."""
import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "jobs", "watch", "validate", "accounts", "portfolio")
NOW = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)
GH_API = "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true"


def gh_job(n, title="Product Marketing Manager", place="Tel Aviv, Israel", day="2026-11-20", board="acme"):
    return {"id": n, "title": title, "absolute_url": f"https://job-boards.greenhouse.io/{board}/jobs/{n}",
            "location": {"name": place}, "first_published": f"{day}T10:00:00+00:00",
            "company_name": board.capitalize(), "content": f"&lt;p&gt;Job {n}: own the launches.&lt;/p&gt;"}


def no_network(*a, **k):
    raise AssertionError("a test tried to open a network connection")


class Watch(unittest.TestCase):
    def setUp(self):
        guard = mock.patch("socket.create_connection", no_network)
        guard.start()
        self.addCleanup(guard.stop)
        nap = mock.patch("time.sleep")
        self.slept = nap.start()
        self.addCleanup(nap.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach").mkdir()
        for f in ("cv.pdf", "cv.txt"):
            shutil.copy(REPO / "examples" / f, self.root / "profile" / f)
        self.profile = json.loads((REPO / "examples" / "profile.json").read_text(encoding="utf-8"))
        self.profile["cvs"] = [{"file": "profile/cv.pdf", "use_when": "default"}]
        self.profile["watch"] = {"boards": ["greenhouse:acme"], "title": "product marketing",
                                 "location": "tel aviv|remote", "days": 30}
        self.save_profile()
        self.boards = {"acme": [gh_job(1)]}
        self.down = {}
        for m in MODS:
            sys.modules.pop(m, None)
        sys.path.insert(0, str(self.root / "scripts"))
        importlib.import_module("jobs").http = self.http

    def tearDown(self):
        sys.path.remove(str(self.root / "scripts"))
        for m in MODS:
            sys.modules.pop(m, None)
        self.tmp.cleanup()

    def http(self, url, **k):
        from _common import NetError
        for board, why in self.down.items():
            if f"/boards/{board}/" in url:
                raise NetError(why, 500)
        for board, jobs in self.boards.items():
            if url == GH_API.format(board):
                return {"jobs": jobs}
        raise NetError(f"GET {url} HTTP 404: no such board", 404)

    def save_profile(self):
        (self.root / "profile" / "profile.json").write_text(json.dumps(self.profile), encoding="utf-8")

    def mod(self):
        return importlib.import_module("watch")

    def run_watch(self, now=NOW, force=False):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            lines = self.mod().run(now=now, force=force)
        return "\n".join(lines), err.getvalue()

    def run_cmd(self, *argv, script="watch"):
        module = importlib.import_module(script)
        out, err, code = io.StringIO(), io.StringIO(), 0
        old = sys.argv
        sys.argv = [f"{script}.py", *argv]
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                (module.run_script if script == "watch" else module.run)(module.main)
        except SystemExit as e:
            code = e.code or 0
        finally:
            sys.argv = old
        return code, out.getvalue(), err.getvalue()

    def refused(self, *argv, why="", script="watch"):
        code, out, err = self.run_cmd(*argv, script=script)
        self.assertEqual(code, 2, f"expected a hard-fail, got exit {code}\n{out}{err}")
        self.assertIn("HARD-FAIL", err)
        self.assertNotIn("Traceback", err)
        self.assertIn(why, err)
        return err

    @property
    def jobs_dir(self):
        return self.root / "outreach" / "jobs"


class Run(Watch):
    def test_a_new_posting_is_shown_and_saved_for_triage(self):
        out, _ = self.run_watch()
        self.assertIn("1 new job", out)
        self.assertIn("https://job-boards.greenhouse.io/acme/jobs/1", out)
        saved = self.jobs_dir / "acme-1.md"
        self.assertTrue(saved.is_file(), out)
        text = saved.read_text(encoding="utf-8")
        self.assertIn("url: https://job-boards.greenhouse.io/acme/jobs/1", text)
        self.assertIn("Job 1: own the launches.", text)
        self.assertIn("acme-1.md", out, "the JD file name is shown, as triage.py expects it")

    def test_the_next_run_shows_only_what_is_new_since(self):
        self.run_watch()
        self.boards["acme"].append(gh_job(2, title="Senior Product Marketing Manager"))
        out, _ = self.run_watch(now=NOW + timedelta(days=1))
        self.assertIn("1 new job", out)
        self.assertIn("/jobs/2", out)
        self.assertNotIn("/jobs/1 ", out)
        out, _ = self.run_watch(now=NOW + timedelta(days=2))
        self.assertIn("0 new jobs", out)

    def test_a_run_within_20_hours_is_skipped_unless_forced(self):
        self.run_watch()
        self.boards["acme"].append(gh_job(2))
        out, _ = self.run_watch(now=NOW + timedelta(hours=5))
        self.assertTrue(out.startswith("SKIP last run 5 h ago"), out)
        self.assertFalse((self.jobs_dir / "acme-2.md").exists(), "a skipped run reads no board")
        out, _ = self.run_watch(now=NOW + timedelta(hours=5), force=True)
        self.assertIn("1 new job", out)

    def test_old_and_unmatched_postings_are_left_out(self):
        self.boards["acme"] += [gh_job(2, title="Account Executive"), gh_job(3, place="Berlin, Germany"),
                                gh_job(4, day="2026-09-01"), gh_job(5, place="Remote (EMEA)")]
        out, _ = self.run_watch()
        self.assertIn("2 new jobs", out)
        self.assertIn("/jobs/5", out)
        for n in (2, 3, 4):
            self.assertNotIn(f"/jobs/{n} ", out)

    def test_each_run_is_kept_in_a_dated_file(self):
        self.run_watch()
        self.boards["acme"].append(gh_job(2))
        self.run_watch(now=NOW + timedelta(hours=1), force=True)
        report = (self.root / "outreach" / "watch-2026-11-26.md").read_text(encoding="utf-8")
        self.assertEqual(report.count("## Run "), 2, report)
        self.assertIn("/acme/jobs/1", report)
        self.assertIn("/acme/jobs/2", report)


class Status(Watch):
    def status(self, now=NOW + timedelta(hours=3)):
        return "\n".join(self.mod().status(now=now))

    def test_before_any_run(self):
        self.assertIn("no run yet", self.status())

    def test_last_run_and_what_is_still_waiting_to_be_scored(self):
        self.boards["acme"].append(gh_job(2))
        self.run_watch()
        out = self.status()
        self.assertIn("last run 3 h ago", out)
        self.assertIn("2 new", out)
        self.assertIn("2 waiting to be scored", out)
        self.assertIn("acme-1.md", out)
        (self.root / "outreach" / "triage-2026-11-26.md").write_text(
            "| 1 | Acme | PMM | ... | acme-1.md | ... |\n", encoding="utf-8")
        out = self.status()
        self.assertIn("1 waiting to be scored", out)
        self.assertNotIn("acme-1.md", out)
        self.assertIn("acme-2.md", out)


class Failures(Watch):
    def setUp(self):
        super().setUp()
        self.profile["watch"]["boards"] = ["greenhouse:broken", "greenhouse:acme"]
        self.save_profile()
        self.down = {"broken": "GET https://boards-api.greenhouse.io/v1/boards/broken/jobs HTTP 500: oops"}

    def test_a_failing_board_is_named_and_the_rest_still_read(self):
        out, _ = self.run_watch()
        self.assertIn("SKIPPED greenhouse:broken", out)
        self.assertIn("HTTP 500", out)
        self.assertIn("/acme/jobs/1", out)
        self.assertIn("1 board skipped", out)

    def test_a_skipped_board_is_read_again_next_time(self):
        self.boards["broken"] = [gh_job(7, board="broken")]
        self.run_watch()
        self.down = {}
        out, _ = self.run_watch(now=NOW + timedelta(days=1))
        self.assertIn("/broken/jobs/7", out)

    def test_a_blocked_network_ends_the_run_with_nothing_recorded(self):
        from _common import NetBlocked

        def blocked(url, **k):
            raise NetBlocked("the internet is blocked on this network")
        importlib.import_module("jobs").http = blocked
        with self.assertRaises(NetBlocked):
            self.run_watch()
        self.assertFalse((self.root / "outreach" / "watch-state.json").exists())

    def test_a_posting_whose_text_cannot_be_read_is_named_and_retried(self):
        self.profile["watch"]["boards"] = ["breezy:acme"]
        self.save_profile()
        listing = [{"id": "5480ceb9beff", "name": "Product Marketing Manager",
                    "url": "https://acme.breezy.hr/p/5480ceb9beff-pmm", "published_date": "2026-11-20T13:35:11Z",
                    "location": {"name": "Tel Aviv", "is_remote": False}}]
        page = {"text": "<html>moved</html>"}

        def breezy(url, **k):
            return listing if url == "https://acme.breezy.hr/json" else page["text"]
        importlib.import_module("jobs").http = breezy
        out, _ = self.run_watch()
        self.assertIn("SKIPPED https://acme.breezy.hr/p/5480ceb9beff-pmm", out)
        self.assertIn("0 new jobs", out)
        page["text"] = ('<script type="application/ld+json">{"@type":"JobPosting",'
                        '"description":"&lt;p&gt;Own launches.&lt;/p&gt;"}</script>')
        out, _ = self.run_watch(now=NOW + timedelta(days=1))
        self.assertIn("1 new job", out)
        self.assertIn("Own launches.", (self.jobs_dir / "acme-5480ceb9beff.md").read_text(encoding="utf-8"))


class Watchlist(Watch):
    """profile.json -> watch: checked by watch.py and by validate.py --check-profile alike."""

    def test_no_watchlist_yet_is_a_skip_not_a_failure(self):
        del self.profile["watch"]
        self.save_profile()
        code, out, err = self.run_cmd("run")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("SKIP no watchlist"), out)
        self.assertIn("ONBOARDING.md step 9", out)

    def test_a_good_watchlist_passes_the_profile_check(self):
        self.profile["watch"]["boards"].append({"board": "workday:acme.wd5/External", "search": "marketing"})
        self.save_profile()
        code, out, err = self.run_cmd("--check-profile", script="validate")
        self.assertEqual(code, 0, err)

    def test_a_bad_watchlist_is_refused_naming_the_cause(self):
        good = dict(self.profile["watch"])
        cases = (
            (["greenhouse:acme"], "'watch' must be an object"),
            ({**good, "boards": []}, "watch.boards must be a non-empty list"),
            ({**good, "boards": ["acme"]}, "watch.boards: 'acme' is not a board name"),
            ({**good, "boards": ["monster:acme"]}, "unknown board type 'monster'"),
            ({**good, "boards": ["workday:nvidia"]}, "workday board 'nvidia' must look like"),
            ({**good, "boards": ["greenhouse:acme", "greenhouse:acme"]}, "listed twice"),
            ({**good, "boards": [{"board": "greenhouse:acme", "serch": "x"}]}, "unknown key"),
            ({**good, "title": ""}, "watch.title must be a pattern"),
            ({**good, "title": "pm("}, "watch.title is not a valid pattern"),
            ({**good, "location": 3}, "watch.location must be a pattern"),
            ({**good, "days": "30"}, "watch.days must be a whole number"),
            ({**good, "days": 0}, "watch.days must be a whole number"),
            ({**good, "every": "day"}, "unknown watch key"),
        )
        for bad, why in cases:
            with self.subTest(why):
                self.profile["watch"] = bad
                self.save_profile()
                self.refused("run", why=why)
                self.refused("--check-profile", why=why, script="validate")

    def test_a_broken_state_file_is_refused(self):
        (self.root / "outreach" / "watch-state.json").write_text("{nope", encoding="utf-8")
        self.refused("run", why="watch-state.json")
        self.refused("status", why="watch-state.json")

    def test_unknown_commands_are_refused(self):
        self.refused("go")
        self.refused("run", "--now")
        self.refused()


if __name__ == "__main__":
    unittest.main()
