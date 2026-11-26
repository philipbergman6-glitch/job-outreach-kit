"""Tests for the fit loop: the owner's own verdict on each posting (fit.py label), how well the
kit's shortlist agrees with it (fit.py report), the brief-driven gates in triage.py check, and the
golden fixtures in tests/fixtures/fit/. No network. Each test works in a throwaway copy of scripts/."""
import contextlib
import importlib
import io
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "triage", "jobs", "fit")
RECENT = (date.today() - timedelta(days=3)).isoformat()
KEPT_HEAD = ("| # | Company | Role | Location | Posted | Salary | Visa | Score | Apply path | Link | JD file "
             "| Why it fits | Quote |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
DROP_HEAD = "| Company | Role | Link | JD file | Reason | Quote |\n|---|---|---|---|---|---|\n"


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach" / "jobs").mkdir(parents=True)
        shutil.copy(REPO / "examples" / "brief.md", self.root / "profile" / "brief.md")
        for m in MODS:
            sys.modules.pop(m, None)
        sys.path.insert(0, str(self.root / "scripts"))

    def tearDown(self):
        sys.path.remove(str(self.root / "scripts"))
        for m in MODS:
            sys.modules.pop(m, None)
        self.tmp.cleanup()

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

    def jd(self, name, text):
        (self.root / "outreach" / "jobs" / name).write_text(text, encoding="utf-8")

    def triage(self, kept=(), dropped=(), name="triage-2026-11-20.md"):
        """A triage file. kept: (tier, #, company, role, score, link, jd, quote); dropped:
        (company, role, link, jd, reason, quote)."""
        body = "# Triage 2026-11-20: test, 9 postings read\n\n"
        for tier in "ABC":
            rows = [k for k in kept if k[0] == tier]
            if rows:
                body += f"## {tier}: x\n" + KEPT_HEAD + "".join(
                    f"| {n} | {c} | {r} | Tel Aviv | {RECENT} | - | - | {s} | greenhouse | {l} | {j} | Launch hook "
                    f"| \"{q}\" |\n" for _, n, c, r, s, l, j, q in rows) + "\n"
        if dropped:
            body += "## Dropped\n" + DROP_HEAD + "".join(
                f"| {c} | {r} | {l} | {j} | {why} | {q} |\n" for c, r, l, j, why, q in dropped)
        p = self.root / "outreach" / name
        p.write_text(body, encoding="utf-8")
        return str(p)

    def brief_line(self, old, new):
        p = self.root / "profile" / "brief.md"
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new), encoding="utf-8")


class BriefGates(Sandbox):
    """triage.py check stops a kept row that the brief itself rules out: a title the owner
    listed under 'Titles to skip', or a phrase they listed under 'Deal-breakers'."""

    def test_a_title_to_skip_cannot_be_kept(self):
        self.jd("n-1.md", "Run growth experiments across our funnel every week.")
        p = self.triage(kept=[("A", 1, "Nimbus", "Senior Growth Hacker", 5, "https://nimbus.io/j/1", "n-1.md",
                               "Run growth experiments across our funnel")])
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertEqual(code, 1, out)
        self.assertIn("Titles to skip", out)
        self.assertIn("Growth Hacker", out)

    def test_a_title_to_skip_is_dropped_without_a_quote(self):
        p = self.triage(dropped=[("Nimbus", "Growth Hacker", "https://nimbus.io/j/1", "-", "title to skip: Growth Hacker", "-")])
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertEqual(code, 0, out)

    def test_a_wanted_title_that_contains_a_skip_word_is_not_caught(self):
        self.brief_line("Titles to skip: Growth Hacker", "Titles to skip: Growth")
        self.jd("n-1.md", "Own launches for our growth-stage payments product.")
        p = self.triage(kept=[("A", 1, "Nimbus", "Product Marketing Manager", 5, "https://nimbus.io/j/1", "n-1.md",
                               "Own launches for our growth-stage payments product")])
        self.assertEqual(self.run_cmd("triage", "check", p)[0], 0)

    def test_a_deal_breaker_phrase_in_the_posting_must_be_dropped(self):
        self.jd("o-1.md", "Pay is commission only, with a generous uncapped plan.")
        p = self.triage(kept=[("A", 1, "Orbit", "Product Marketing Manager", 5, "https://orbit.io/j/1", "o-1.md",
                               "with a generous uncapped plan")])
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertEqual(code, 1, out)
        self.assertIn("Phrases that end it", out)
        self.assertIn("Pay is commission only, with a generous uncapped plan.", out)

    def test_no_phrases_written_means_no_phrase_gate(self):
        self.brief_line('- Phrases that end it: "commission only", "weekend shifts", "frequent travel abroad"',
                        "- Phrases that end it: none")
        self.jd("o-1.md", "Pay is commission only, with a generous uncapped plan.")
        p = self.triage(kept=[("A", 1, "Orbit", "Product Marketing Manager", 5, "https://orbit.io/j/1", "o-1.md",
                               "with a generous uncapped plan")])
        self.assertEqual(self.run_cmd("triage", "check", p)[0], 0)
