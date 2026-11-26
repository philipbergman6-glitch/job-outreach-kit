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


LABELS_HEAD = "| Date | Triage | Row | Company | Role | Link | Verdict | Because | Deal-breaker | Reason |"


class Label(Sandbox):
    """fit.py label: the owner's verdict on one posting, written to outreach/fit-labels.md."""

    def setUp(self):
        super().setUp()
        self.jd("a-1.md", "Lead launches for our payments product line.")
        self.list = self.triage(
            kept=[("A", 1, "Acme", "Product Marketing Manager", 5, "https://acme.io/j/1", "a-1.md",
                   "Lead launches for our payments product line"),
                  ("B", 2, "Beta", "Go-to-Market Manager", 3, "https://beta.io/j/2", "a-1.md",
                   "Lead launches for our payments product line")],
            dropped=[("Gamma", "Event Marketing Lead", "https://gamma.io/j/3", "-", "already applied", "-")])
        self.labels = self.root / "outreach" / "fit-labels.md"

    def rows(self):
        return [l for l in self.labels.read_text(encoding="utf-8").splitlines() if l.startswith("| 2")]

    def test_a_row_of_a_triage_list_is_labelled(self):
        code, out, err = self.run_cmd("fit", "label", self.list, "A1", "apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn(LABELS_HEAD, self.labels.read_text(encoding="utf-8"))
        cells = [c.strip() for c in self.rows()[0].strip("|").split("|")]
        self.assertEqual(cells[1:], ["triage-2026-11-20.md", "A1", "Acme", "Product Marketing Manager",
                                     "https://acme.io/j/1", "apply", "-", "no", "-"])
        self.assertEqual(cells[0], date.today().isoformat())

    def test_skip_keeps_the_reason_and_the_deal_breaker_mark(self):
        code, out, err = self.run_cmd("fit", "label", self.list, "B2", "skip", "--because", "place",
                                      "--reason", "on-site five days", "--deal-breaker")
        self.assertEqual(code, 0, out + err)
        self.assertIn("| B2 | Beta | Go-to-Market Manager | https://beta.io/j/2 | skip | place | yes | on-site five days |",
                      self.rows()[0])

    def test_a_dropped_row_is_labelled_by_its_place_in_the_table(self):
        self.assertEqual(self.run_cmd("fit", "label", self.list, "D1", "maybe", "--because", "work",
                                      "--reason", "events, but a big brand")[0], 0)
        self.assertIn("| D1 | Gamma |", self.rows()[0])

    def test_skip_and_maybe_need_a_reason(self):
        for argv in (("skip",), ("maybe", "--because", "pay"), ("skip", "--reason", "too far")):
            code, _, err = self.run_cmd("fit", "label", self.list, "A1", *argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("needs --because", err)
        self.assertFalse(self.labels.exists(), "a refused label writes nothing")

    def test_bad_input_is_refused_by_name(self):
        for argv, why in ((("A9", "apply"), "no row A9"), (("A1", "love"), "must be one of apply"),
                          (("A1", "skip", "--because", "vibes", "--reason", "x"), "--because 'vibes'"),
                          (("A1", "apply", "--deal-breaker"), "skip only"),
                          (("A1", "skip", "--because", "pay", "--reason", "a | b"), "'|'")):
            code, _, err = self.run_cmd("fit", "label", self.list, *argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(why, err, argv)
        code, _, err = self.run_cmd("fit", "label", "triage-1999-01-01.md", "A1", "apply")
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_the_same_verdict_twice_writes_once_and_a_change_is_appended(self):
        self.run_cmd("fit", "label", self.list, "A1", "apply")
        code, out, _ = self.run_cmd("fit", "label", self.list, "A1", "apply")
        self.assertIn("already", out)
        self.assertEqual(len(self.rows()), 1)
        code, out, _ = self.run_cmd("fit", "label", self.list, "A1", "skip", "--because", "pay", "--reason", "low")
        self.assertIn("changed", out)
        self.assertEqual(len(self.rows()), 2)

    def test_a_link_finds_its_row_in_the_lists(self):
        self.assertEqual(self.run_cmd("fit", "label", "https://beta.io/j/2?utm_source=x", "apply")[0], 0)
        self.assertIn("| triage-2026-11-20.md | B2 | Beta |", self.rows()[0])

    def test_a_job_the_kit_never_showed_needs_company_and_role(self):
        code, _, err = self.run_cmd("fit", "label", "https://kestrel.io/j/9", "apply")
        self.assertEqual(code, 2)
        self.assertIn("--company and --role", err)
        code, out, err = self.run_cmd("fit", "label", "https://kestrel.io/j/9", "apply", "--company", "Kestrel",
                                      "--role", "Product Marketing Manager")
        self.assertEqual(code, 0, out + err)
        self.assertIn("| - | - | Kestrel | Product Marketing Manager | https://kestrel.io/j/9 | apply |", self.rows()[0])
