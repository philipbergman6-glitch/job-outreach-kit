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


class Report(Sandbox):
    """fit.py report: the kit's tiers against the owner's labels, worked out by hand below."""

    def setUp(self):
        super().setUp()
        self.jd("a-1.md", "Lead launches for our payments product line.")
        scores = {"A": [5, 4, 5, 4], "B": [3, 3, 3, 3], "C": [2, 2, 2, 2]}
        kept, n = [], 0
        for tier in "ABC":
            for s in scores[tier]:
                n += 1
                kept.append((tier, n, f"Co{n}", "Product Marketing Manager", s, f"https://co{n}.io/j", "a-1.md",
                             "Lead launches for our payments product line"))
        self.list = self.triage(kept=kept, dropped=[
            ("Lumen", "Product Marketing Manager", "https://lumen.io/j", "-", "duplicate", "-")])

    def label(self, *argv):
        code, out, err = self.run_cmd("fit", "label", *argv)
        self.assertEqual(code, 0, out + err)

    def worked_example(self):
        # Kit order (tier, then score): A1 A3 A2 A4 B5 B6 B7 B8 C9 C10 | C11 C12.
        self.label(self.list, "A1", "apply")
        self.label(self.list, "A2", "apply")
        self.label(self.list, "A3", "skip", "--because", "pay", "--reason", "commission only", "--deal-breaker")
        self.label(self.list, "A4", "maybe", "--because", "work", "--reason", "heavy on events")
        self.label(self.list, "B5", "apply")
        self.label(self.list, "B6", "skip", "--because", "place", "--reason", "on-site in Haifa", "--deal-breaker")
        self.label(self.list, "C9", "apply")
        self.label(self.list, "C11", "apply")
        self.label(self.list, "D1", "apply")
        self.label("https://kestrel.io/j", "apply", "--company", "Kestrel", "--role", "PMM")

    def test_top_ten_share_counts_only_labelled_rows(self):
        self.worked_example()
        code, out, err = self.run_cmd("fit", "report")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Top 10: you would apply to 4 of the 7 you labelled (57%)", out)

    def test_deal_breaker_leaks_name_the_row_and_the_brief_section(self):
        self.worked_example()
        out = self.run_cmd("fit", "report")[1]
        self.assertIn("Deal-breaker leaks: 2", out)
        self.assertIn("A3 Co3, Product Marketing Manager (kit: score 5): pay, \"commission only\" → brief.md "
                      "Deal-breakers → Salary floor", out)
        self.assertIn("B6 Co6, Product Marketing Manager (kit: score 3): place, \"on-site in Haifa\"", out)
        self.assertNotIn("A4 Co4", out.split("Deal-breaker leaks")[1].split("Misses")[0], "maybe is no leak")

    def test_misses_cover_tier_c_dropped_and_never_found(self):
        self.worked_example()
        out = self.run_cmd("fit", "report")[1]
        self.assertIn("Misses: 4", out)
        for line in ("C9 Co9, Product Marketing Manager (kit: score 2)",
                     "C11 Co11, Product Marketing Manager (kit: score 2)",
                     "D1 Lumen, Product Marketing Manager (kit: duplicate)",
                     "- Kestrel, PMM (kit: the search never found it)"):
            self.assertIn(line, out)

    def test_reasons_are_counted_with_their_brief_section(self):
        self.worked_example()
        out = self.run_cmd("fit", "report")[1]
        reasons = out.split("Reasons you gave")[1]
        for why in ("pay", "place", "work"):
            self.assertRegex(reasons, rf"\n  {why} +1 ")
        self.assertIn("Story → More of / less of", reasons)

    def test_the_table_crosses_kit_tier_with_the_owner_verdict(self):
        self.worked_example()
        out = self.run_cmd("fit", "report")[1]
        for row in ("| Kit put it in | apply | maybe | skip |", "| A | 2 | 1 | 1 |", "| B | 1 | 0 | 1 |",
                    "| C | 2 | 0 | 0 |", "| Dropped | 1 | 0 | 0 |", "| not shown | 1 | 0 | 0 |"):
            self.assertIn(row, out)

    def test_a_later_verdict_replaces_the_earlier_one(self):
        self.label(self.list, "A1", "skip", "--because", "pay", "--reason", "commission only", "--deal-breaker")
        self.label(self.list, "A1", "apply")
        out = self.run_cmd("fit", "report")[1]
        self.assertIn("Deal-breaker leaks: 0", out)
        self.assertIn("| A | 1 | 0 | 0 |", out)
        self.assertIn("too few to tell", out)

    def test_no_labels_yet_hard_fails_with_the_next_step(self):
        code, _, err = self.run_cmd("fit", "report")
        self.assertEqual(code, 2)
        self.assertIn("no labels yet", err)
        self.assertIn("fit.py label", err)

    def test_a_malformed_labels_file_names_the_file_and_line(self):
        self.label(self.list, "A1", "apply")
        self.label(self.list, "A2", "apply")
        p = self.root / "outreach" / "fit-labels.md"
        good = p.read_text(encoding="utf-8")
        line = next(i for i, l in enumerate(good.splitlines(), 1) if "| Co2 |" in l)
        for bad, worse, why in (("| apply |", "| yes please |", "Verdict 'yes please'"),
                         ("| no | - |", "| maybe | - |", "Deal-breaker 'maybe'"),
                         ("| apply | - |", "| apply | luck |", "Because 'luck'"),
                         ("| apply | - | no | - |", "| apply | - | no |", "cells")):
            lines = good.splitlines()
            lines[line - 1] = lines[line - 1].replace(bad, worse)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            code, _, err = self.run_cmd("fit", "report")
            self.assertEqual(code, 2, bad)
            self.assertIn(f"fit-labels.md, line {line}", err, bad)
            self.assertIn(why, err, bad)
        p.write_text(good.replace("| Verdict |", "| Choice |"), encoding="utf-8")
        code, _, err = self.run_cmd("fit", "report")
        self.assertEqual(code, 2)
        self.assertIn("columns", err)

    def test_a_label_whose_list_is_gone_or_changed_names_the_line(self):
        self.label(self.list, "A1", "apply")
        labels = (self.root / "outreach" / "fit-labels.md").read_text(encoding="utf-8").splitlines()
        line = next(i for i, l in enumerate(labels, 1) if "| Co1 |" in l)
        Path(self.list).write_text(Path(self.list).read_text(encoding="utf-8").replace("https://co1.io/j", "https://x.io/1"),
                                   encoding="utf-8")
        code, _, err = self.run_cmd("fit", "report")
        self.assertEqual(code, 2)
        self.assertIn(f"fit-labels.md, line {line}:", err)
        self.assertIn("is not in triage-2026-11-20.md", err)
        Path(self.list).unlink()
        code, _, err = self.run_cmd("fit", "report")
        self.assertIn("not found", err)

    def test_a_malformed_triage_list_names_its_line(self):
        self.label(self.list, "A1", "apply")
        text = Path(self.list).read_text(encoding="utf-8").replace("| 2 | Co2 |", "| 2 | Co2 | extra |")
        Path(self.list).write_text(text, encoding="utf-8")
        line = next(i for i, l in enumerate(text.splitlines(), 1) if "| Co2 |" in l)
        code, _, err = self.run_cmd("fit", "report")
        self.assertEqual(code, 2)
        self.assertIn(f"line {line}", err)


GOLDEN = REPO / "tests" / "fixtures" / "fit" / "golden.json"
STOPS = (("Titles to skip", "skip-title"), ("Phrases that end it", "phrase"), ("asks the candidate to pay", "scam"))


class Golden(Sandbox):
    """The rule-based gates against the example persona's own verdicts (tests/fixtures/fit/).

    What this can test: the gates that are code. jobs.py list's title, place and date filters
    (with the patterns the assistant writes from the brief) and triage.py check's brief and scam
    gates stop exactly the postings each fixture says, and never a job the owner would apply to
    or consider. What it cannot test: the assistant's 1-5 score, which is judgement; the fixtures
    marked rules=pass with a skip verdict are left to it, and only fit.py report on the owner's
    real labels measures how well it does."""

    def setUp(self):
        super().setUp()
        import json
        self.data = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.jobs = importlib.import_module("jobs")

    def search_gate(self, p):
        """title / place / stale when jobs.py list would not list the posting, else None."""
        s = self.data["search"]
        today = date.today()
        j = {"title": p["title"], "location": p["location"], "remote": p["remote"],
             "posted": None if p["age_days"] is None else today - timedelta(days=p["age_days"])}
        for gate, args in (("title", (s["title"], "", 10 ** 6)), ("place", ("", s["location"], 10 ** 6)),
                           ("stale", ("", "", 30))):
            if not self.jobs.keep([j], *args, today=today):
                return gate
        return None

    def check_gates(self, listed):
        """{posting id: [gates triage.py check named]} with every listed posting kept in tier A."""
        kept = []
        for n, p in enumerate(listed, 1):
            self.jd(f"{p['id']}.md", p["text"])
            first = p["text"].split(". ")[0].rstrip(".")
            kept.append(("A", n, p["company"], p["title"], 5, f"https://{p['id']}.example.com/job", f"{p['id']}.md", first))
        code, out, err = self.run_cmd("triage", "check", self.triage(kept=kept))
        self.assertNotEqual(code, 2, err)
        found = {p["id"]: [] for p in listed}
        for line in out.splitlines():
            for n, p in enumerate(listed, 1):
                if line.strip().startswith(f"[A{n} {p['company']}]"):
                    hit = [g for words, g in STOPS if words in line]
                    self.assertTrue(hit, f"{p['id']}: an unexpected problem: {line}")
                    found[p["id"]] += hit
        return found

    def test_the_fixtures_are_well_formed(self):
        posts = self.data["postings"]
        self.assertGreaterEqual(len(posts), 15)
        self.assertEqual(len({p["id"] for p in posts}), len(posts))
        fit = importlib.import_module("fit")
        for p in posts:
            g = p["golden"]
            self.assertIn(g["verdict"], fit.VERDICTS, p["id"])
            self.assertTrue(g["because"] == "-" or g["because"] in fit.BECAUSE, p["id"])
            self.assertTrue(g["reason"].strip(), p["id"])
            self.assertFalse(g["deal_breaker"] and g["verdict"] != "skip", p["id"])
            self.assertIn(p["rules"], ("pass", "title", "place", "stale", "skip-title", "phrase", "scam"), p["id"])

    def test_each_gate_stops_exactly_the_postings_the_fixtures_say(self):
        listed, got = [], {}
        for p in self.data["postings"]:
            gate = self.search_gate(p)
            if gate:
                got[p["id"]] = gate
            else:
                listed.append(p)
        for pid, gates in self.check_gates(listed).items():
            got[pid] = gates[0] if len(gates) == 1 else ("pass" if not gates else "+".join(gates))
        for p in self.data["postings"]:
            self.assertEqual(got[p["id"]], p["rules"], f"{p['id']} ({p['golden']['reason']})")

    def test_no_gate_stops_a_job_the_owner_would_apply_to_or_consider(self):
        for p in self.data["postings"]:
            if p["golden"]["verdict"] in ("apply", "maybe"):
                self.assertEqual(p["rules"], "pass", p["id"])

    def test_the_skips_left_to_judgement_are_named(self):
        """The honest gap: these skips pass every gate and rest on the assistant's score. The two
        deal-breakers among them are lines the brief does not yet turn into a gate (no ruled-out
        industry, a contract rule with no phrase): the leaks fit.py report would show."""
        left = {p["id"] for p in self.data["postings"] if p["golden"]["verdict"] == "skip" and p["rules"] == "pass"}
        self.assertEqual(left, {"pinecrest-817", "tidewater-918", "bluefin-119", "corvid-220", "linden-321"})
        leaks = {p["id"] for p in self.data["postings"] if p["id"] in left and p["golden"]["deal_breaker"]}
        self.assertEqual(leaks, {"corvid-220", "linden-321"})
