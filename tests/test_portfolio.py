"""Tests for the portfolio catalog: profile.json "portfolio", scripts/portfolio.py (list, check,
rank, migrate, github) and validate.py's checks on the project and link a message cites. No network:
each test works in a throwaway copy of scripts/, GitHub replaced by a fake."""
import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "validate", "accounts", "portfolio")

LAUNCH = {"id": "launch-playbook", "name": "Launch Playbook",
          "what": "a repeatable launch process",
          "link": "https://example.com/dana-levi/launch-playbook", "shareable": True,
          "own_part": "built and ran it for six releases",
          "proof": "trial-to-paid conversion from 11% to 16% over two quarters",
          "skills": ["product launches", "go-to-market", "launch review"],
          "fits": ["product marketing"]}


def no_network(*a, **k):
    raise AssertionError("a test tried to open a network connection")


class Sandbox(unittest.TestCase):
    def setUp(self):
        guard = mock.patch("socket.create_connection", no_network)
        guard.start()
        self.addCleanup(guard.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach" / "jobs").mkdir(parents=True)
        for f in ("cv.pdf", "cv.txt", "brief.md"):
            shutil.copy(REPO / "examples" / f, self.root / "profile" / f)
        self.profile = json.loads((REPO / "examples" / "profile.json").read_text(encoding="utf-8"))
        self.profile["cvs"] = [{"file": "profile/cv.pdf", "use_when": "default"}]
        self.save()
        for m in MODS:
            sys.modules.pop(m, None)
        sys.path.insert(0, str(self.root / "scripts"))

    def tearDown(self):
        sys.path.remove(str(self.root / "scripts"))
        for m in MODS:
            sys.modules.pop(m, None)
        self.tmp.cleanup()

    def save(self):
        (self.root / "profile" / "profile.json").write_text(json.dumps(self.profile), encoding="utf-8")

    def catalog(self, *entries):
        self.profile.pop("hooks", None)
        self.profile["portfolio"] = [dict(e) if isinstance(e, dict) else e for e in entries]
        self.save()

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
        return out

    def refused(self, mod, *argv, why=()):
        code, out, err = self.run_cmd(mod, *argv)
        self.assertEqual(code, 2, f"expected a hard-fail, got exit {code}\n{out}{err}")
        self.assertIn("HARD-FAIL", err)
        self.assertNotIn("unexpected", err)
        for w in why:
            self.assertIn(w, err)
        return err


class Catalog(Sandbox):
    """profile.json "portfolio" is the catalog; the hook names come from it."""

    def test_hook_names_come_from_the_catalog(self):
        self.catalog(LAUNCH, {**LAUNCH, "id": "churn-study", "name": "Churn Study", "link": None,
                              "shareable": False})
        out = self.ok("validate", "--check-profile")
        self.assertIn("PROFILE OK", out)
        self.assertIn("'Launch Playbook', 'Churn Study'", out)

    def test_the_older_hooks_list_still_loads(self):
        self.profile.pop("portfolio", None)
        self.profile["hooks"] = ["Launch Playbook", "Churn Study"]
        self.save()
        self.assertIn("'Launch Playbook', 'Churn Study'", self.ok("validate", "--check-profile"))

    def test_neither_catalog_nor_hooks_hard_fails(self):
        self.profile.pop("portfolio", None)
        self.profile.pop("hooks", None)
        self.save()
        self.refused("validate", "--check-profile", why=("'portfolio' must be a non-empty list",))

    def test_a_broken_entry_hard_fails_naming_it(self):
        other = {**LAUNCH, "id": "churn-study", "name": "Churn Study"}
        cases = [
            ([{**LAUNCH, "link": "ftp://example.com/x"}], "link must start with http:// or https://"),
            ([{**LAUNCH, "link": "javascript:alert(1)"}], "link must start with http:// or https://"),
            ([{**LAUNCH, "id": "Launch Playbook"}], "id 'Launch Playbook' must be lowercase letters"),
            ([LAUNCH, {**other, "id": "launch-playbook"}], "id 'launch-playbook' is used twice"),
            ([LAUNCH, {**other, "name": "launch playbook"}], "name 'launch playbook' is used twice"),
            ([{**LAUNCH, "shareable": "yes"}], "shareable must be true or false"),
            ([{**LAUNCH, "skills": "launches"}], "skills must be a list of words"),
            ([{**LAUNCH, "proof": 16}], "proof must be text"),
            ([{**LAUNCH, "name": " "}], "needs a name"),
            (["Launch Playbook"], "each entry must be an object"),
        ]
        for entries, why in cases:
            with self.subTest(why=why):
                self.catalog(*entries)
                self.refused("validate", "--check-profile", why=(why,))

    def test_hooks_beside_a_catalog_must_be_its_names(self):
        self.catalog(LAUNCH)
        self.profile["hooks"] = ["Launch Playbook", "Churn Study"]
        self.save()
        self.refused("validate", "--check-profile", why=("'hooks' lists 'Churn Study'",))
        self.profile["hooks"] = ["Launch Playbook"]
        self.save()
        self.ok("validate", "--check-profile")


class Check(Sandbox):
    """`check`: every entry says what the owner did, what it proved, and where to see it."""

    def check_fails(self, *why):
        code, out, err = self.run_cmd("portfolio", "check")
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL", out)
        for w in why:
            self.assertIn(w, out)
        return out

    def test_a_complete_catalog_passes(self):
        self.catalog(LAUNCH)
        self.assertIn("CATALOG OK", self.ok("portfolio", "check"))

    def test_missing_parts_are_each_named(self):
        self.catalog({**LAUNCH, "own_part": " ", "proof": ""},
                     {k: v for k, v in LAUNCH.items() if k not in ("skills", "fits")}
                     | {"id": "churn-study", "name": "Churn Study"})
        self.check_fails("'Launch Playbook': own_part is empty", "'Launch Playbook': proof is empty",
                         "'Churn Study': skills is empty", "'Churn Study': fits is empty")

    def test_a_shareable_entry_has_a_link_or_says_why_not(self):
        self.catalog({**LAUNCH, "link": None})
        self.check_fails("'Launch Playbook' is shareable but has no link")
        self.catalog({**LAUNCH, "link": None, "no_link_why": "the write-up is not public yet"})
        self.ok("portfolio", "check")

    def test_a_proof_figure_must_trace_to_the_cv_or_brief(self):
        self.catalog({**LAUNCH, "proof": "trial-to-paid conversion from 11% to 19%"})
        self.check_fails("'Launch Playbook': proof figure 19 is in neither the CV text nor brief.md")

    def test_an_older_profile_is_told_how_to_migrate(self):
        self.profile.pop("portfolio", None)
        self.profile["hooks"] = ["Launch Playbook"]
        self.save()
        self.check_fails("no portfolio catalog yet", "portfolio.py migrate")


CHURN = {"id": "churn-study", "name": "Churn Study", "link": None, "shareable": False,
         "own_part": "led the interviews and wrote the findings",
         "proof": "cut first-month churn by a fifth",
         "skills": ["customer research", "retention"], "fits": ["product marketing"]}
PRICING = {"id": "pricing-page-test", "name": "Pricing Page Test", "link": None, "shareable": False,
           "own_part": "helped run it", "proof": "demo requests up 9%",
           "skills": ["pricing experiments", "A/B tests"], "fits": ["growth marketing"]}
POSTING = """# JD
URL: https://boards.greenhouse.io/acme/jobs/1
Fetched: 2026-11-20

Senior Product Marketing Manager

About the role
You will own Product Launches for the warehouse product line.

Requirements:
- 5+ years in B2B product marketing
- Experience running go-to-market for new products
- Strong customer research skills

Nice to have:
- Experience with pricing experiments
"""


class Rank(Sandbox):
    """`rank`: the catalog against one saved posting; every point quotes the posting's own words."""

    def setUp(self):
        super().setUp()
        self.catalog(PRICING, CHURN, LAUNCH)
        self.folder = self.root / "outreach" / "acme"
        self.folder.mkdir()
        (self.folder / "jd.md").write_text(POSTING, encoding="utf-8")

    def ranked_ids(self, out):
        import re
        return re.findall(r"^\d+\. (\S+)", out, re.M)

    def test_must_haves_outrank_the_rest_and_each_point_is_quoted(self):
        out = self.ok("portfolio", "rank", "acme")
        self.assertEqual(self.ranked_ids(out), ["launch-playbook", "churn-study", "pricing-page-test"])
        self.assertIn('must-have "go-to-market": "Experience running go-to-market for new products"', out)
        self.assertIn('"product launches": "You will own Product Launches for the warehouse product line."', out)
        self.assertIn('nice-to-have "pricing experiments": "Experience with pricing experiments"', out)
        import re
        for quote in re.findall(r'": "(.+)"$', out, re.M):
            self.assertIn(quote, POSTING, "a quote must be the posting's own words")

    def test_an_entry_nothing_matches_says_so(self):
        (self.folder / "jd.md").write_text(POSTING.replace("pricing experiments", "SQL"), encoding="utf-8")
        out = self.ok("portfolio", "rank", "acme")
        self.assertIn("pricing-page-test  Pricing Page Test  0 points: no posting words matched", out)

    def test_a_saved_posting_file_can_be_ranked(self):
        job = self.root / "outreach" / "jobs" / "acme-1.md"
        job.write_text(POSTING, encoding="utf-8")
        self.assertEqual(self.ranked_ids(self.ok("portfolio", "rank", str(job)))[0], "launch-playbook")
        self.assertEqual(self.ranked_ids(self.ok("portfolio", "rank", "acme-1"))[0], "launch-playbook")

    def test_no_posting_hard_fails_naming_where_it_looked(self):
        self.refused("portfolio", "rank", "globex", why=("outreach/globex/jd.md", "outreach/jobs/globex.md"))

    def test_the_link_and_whether_it_may_be_shared_are_shown(self):
        out = self.ok("portfolio", "rank", "acme")
        self.assertIn("link: https://example.com/dana-levi/launch-playbook (may be shared)", out)
        self.assertIn("link: none", out)

    def test_the_cv_evidence_for_the_tailoring_decision(self):
        out = self.ok("portfolio", "rank", "acme")
        self.assertIn("CV profile/cv.pdf names: product marketing", out)
        self.assertIn("lacks: go-to-market, customer research", out)

    def test_an_older_profile_cannot_rank(self):
        self.profile.pop("portfolio")
        self.profile["hooks"] = ["Launch Playbook"]
        self.save()
        self.refused("portfolio", "rank", "acme", why=("portfolio.py migrate",))


class ListAndMigrate(Sandbox):
    def old_profile(self, hooks=("Launch Playbook", "Churn Study", "Pricing Page Test")):
        self.profile.pop("portfolio", None)
        self.profile["hooks"] = list(hooks)
        self.save()

    def test_list_shows_every_entry(self):
        self.catalog(LAUNCH, CHURN)
        out = self.ok("portfolio", "list")
        for s in ("launch-playbook  Launch Playbook", "link: https://example.com/dana-levi/launch-playbook (may be shared)",
                  "own part: built and ran it for six releases", "proof: cut first-month churn by a fifth",
                  "skills: customer research, retention", "fits: product marketing"):
            self.assertIn(s, out)

    def test_list_on_an_older_profile_points_to_migrate(self):
        self.old_profile()
        out = self.ok("portfolio", "list")
        self.assertIn("Launch Playbook", out)
        self.assertIn("portfolio.py migrate", out)

    def test_migrate_prefills_from_the_brief_and_leaves_the_rest_open(self):
        self.old_profile(("Launch Playbook", "Side Project"))
        entries = json.loads(self.ok("portfolio", "migrate"))["portfolio"]
        launch, side = entries
        self.assertEqual(launch["id"], "launch-playbook")
        self.assertEqual(launch["own_part"], "built and ran it for six releases.")
        self.assertIn("11% to 16%", launch["proof"])
        self.assertEqual(launch["skills"], ["launches", "go-to-market", "measuring results"])
        self.assertEqual(launch["link"], "https://example.com/dana-levi/launch-playbook", "the link in its proof line")
        self.assertIsNone(side["link"])
        for open_field in (launch["shareable"], launch["fits"][0], side["own_part"], side["proof"]):
            self.assertRegex(open_field, r"^<.+>$", "what the brief does not say stays a placeholder")

    def test_migrated_entries_load_once_filled_in(self):
        self.old_profile()
        text = self.ok("portfolio", "migrate")
        self.profile.pop("hooks")
        self.profile["portfolio"] = json.loads(text)["portfolio"]
        self.save()
        self.refused("validate", "--check-profile", why=("unfilled placeholder",))
        for e in self.profile["portfolio"]:
            e["shareable"], e["fits"] = False, ["product marketing"]
        self.save()
        self.ok("validate", "--check-profile")
        self.assertIn("CATALOG OK", self.ok("portfolio", "check"))

    def test_migrate_with_a_catalog_has_nothing_to_do(self):
        self.catalog(LAUNCH)
        self.assertIn("nothing to migrate", self.ok("portfolio", "migrate"))


REPOS = [
    {"name": "launch-kit", "html_url": "https://github.com/dana-example/launch-kit", "fork": False,
     "archived": False, "description": "Checklists and dashboards for product launches", "language": "Python",
     "topics": ["go-to-market", "analytics"], "stargazers_count": 4, "pushed_at": "2026-10-01T10:00:00Z"},
    {"name": "dotfiles", "html_url": "https://github.com/dana-example/dotfiles", "fork": True,
     "archived": False, "description": None, "language": None, "topics": [], "stargazers_count": 0,
     "pushed_at": "2025-01-01T10:00:00Z"},
    {"name": "old-site", "html_url": "https://github.com/dana-example/old-site", "fork": False,
     "archived": True, "description": "My old site", "language": "HTML", "topics": [], "stargazers_count": 0,
     "pushed_at": "2022-01-01T10:00:00Z"},
]


class GitHub(Sandbox):
    """`github <user>`: the owner's public repositories as entries to confirm, never written."""

    def with_reply(self, reply):
        common, calls = importlib.import_module("_common"), []

        def fake(url, **k):
            calls.append(url)
            if isinstance(reply, Exception):
                raise reply
            return reply
        patch = mock.patch.object(common, "http", fake)
        patch.start()
        self.addCleanup(patch.stop)
        return calls

    def test_public_repos_become_suggestions(self):
        """Onboarding runs it before profile.json exists; it writes nothing."""
        (self.root / "profile" / "profile.json").unlink()
        calls = self.with_reply(REPOS)
        out = self.ok("portfolio", "github", "dana-example")
        self.assertTrue(calls[0].startswith("https://api.github.com/users/dana-example/repos?"), calls)
        self.assertIn("launch-kit  https://github.com/dana-example/launch-kit", out)
        self.assertIn("left out: dotfiles (a fork), old-site (archived)", out)
        self.assertIn("Suggestions only", out)
        entries = json.loads(out[out.index("{"):])["portfolio"]
        self.assertEqual([e["id"] for e in entries], ["launch-kit"])
        e = entries[0]
        self.assertEqual(e["link"], "https://github.com/dana-example/launch-kit")
        self.assertEqual(e["what"], "Checklists and dashboards for product launches")
        self.assertEqual(e["skills"], ["Python", "go-to-market", "analytics"])
        for open_field in (e["shareable"], e["own_part"], e["proof"]):
            self.assertRegex(open_field, r"^<.+>$", "the owner fills these in, never the script")
        self.assertFalse((self.root / "profile" / "profile.json").exists())

    def test_bad_user_names_and_replies_hard_fail(self):
        self.catalog(LAUNCH)
        common = importlib.import_module("_common")
        self.refused("portfolio", "github", "dana example", why=("not a GitHub user name",))
        self.with_reply(common.NetError("GET https://api.github.com/users/x/repos HTTP 404: Not Found", 404))
        self.refused("portfolio", "github", "nobody-here", why=("GitHub has no user 'nobody-here'",))

    def test_a_reply_that_is_not_a_list_hard_fails(self):
        self.catalog(LAUNCH)
        self.with_reply({"message": "API rate limit exceeded"})
        self.refused("portfolio", "github", "dana-example", why=("API rate limit exceeded",))


class Record(Sandbox):
    """messages.md records the project chosen for this job (`portfolio:`) and the link the owner
    approved for it (`portfolio_link:`); validate.py holds the texts to that record."""
    LINK = LAUNCH["link"]
    LINE = "CV attached. LinkedIn: linkedin.com/in/dana-levi-example"

    def setUp(self):
        super().setUp()
        self.catalog(LAUNCH, {**CHURN, "link": "https://github.com/dana-example/churn-study"}, PRICING)
        self.folder = self.root / "outreach" / "acme"
        self.folder.mkdir()
        shutil.copy(self.root / "profile" / "cv.pdf", self.folder / "cv.pdf")
        text = (REPO / "examples" / "acme-robotics" / "messages.md").read_text(encoding="utf-8")
        for k in ("portfolio", "portfolio_link"):  # start from the record-free shape
            text = "\n".join(l for l in text.splitlines() if not l.startswith(f"{k}:")) + "\n"
        text = text.replace(f"{self.LINE}. Launch Playbook write-up: {self.LINK}", self.LINE)
        (self.folder / "messages.md").write_text(text, encoding="utf-8")

    def edit(self, old, new, count=1):
        p = self.folder / "messages.md"
        t = p.read_text(encoding="utf-8")
        self.assertIn(old, t)
        p.write_text(t.replace(old, new, count), encoding="utf-8")

    def record(self, portfolio="launch-playbook", link=None):
        self.edit("hook_rationale:", f"portfolio: {portfolio}\nportfolio_link: {link or 'none'}\nhook_rationale:")

    def cite(self, url, where=LINE):
        self.edit(where, f"{where}. Launch Playbook write-up: {url}")

    def validate(self):
        return self.run_cmd("validate", str(self.folder / "messages.md"))

    def passes(self):
        code, out, err = self.validate()
        self.assertEqual(code, 0, out + err)

    def fails(self, *why):
        code, out, err = self.validate()
        self.assertEqual(code, 1, out + err)
        for w in why:
            self.assertIn(w, out)

    def test_no_record_and_no_project_link_passes(self):
        self.passes()

    def test_the_approved_link_cited_in_t1_passes(self):
        self.record(link=self.LINK)
        self.cite(self.LINK)
        self.passes()

    def test_the_record_names_a_real_entry_matching_the_hook(self):
        self.record("no-such-project")
        self.fails("portfolio 'no-such-project' is not an id in profile.json → portfolio")
        self.edit("portfolio: no-such-project", "portfolio: churn-study")
        self.fails("portfolio 'churn-study' is Churn Study, but hook is Launch Playbook")

    def test_the_recorded_link_is_the_entry_link_and_shareable(self):
        self.record(link="https://example.com/other")
        self.fails("portfolio_link https://example.com/other is not Launch Playbook's link")
        self.edit("portfolio: launch-playbook", "portfolio: churn-study")
        self.edit("hook: Launch Playbook", "hook: Churn Study")
        self.edit("portfolio_link: https://example.com/other", "portfolio_link: https://github.com/dana-example/churn-study")
        self.fails("Churn Study's link is not shareable")

    def test_an_approved_link_must_be_cited_in_t1(self):
        self.record(link=self.LINK)
        self.fails(f"[T1] the approved project link {self.LINK} missing")

    def test_a_project_link_without_approval_fails(self):
        self.cite(self.LINK)
        self.fails(f"[T1] link {self.LINK} is not approved for this job")

    def test_a_private_link_never_appears_anywhere(self):
        self.edit("I would be glad to do a short call this week.",
                  "Code: github.com/dana-example/churn-study. I would be glad to do a short call this week.")
        self.fails("[T4] link github.com/dana-example/churn-study is Churn Study's, which profile.json marks not shareable")

    def test_any_other_link_in_an_email_fails(self):
        self.edit("Happy to answer any questions.", "Blog: https://example.org/blog/post-1. Happy to answer any questions.")
        self.fails("[T2] link https://example.org/blog/post-1 is not approved for this job")

    def test_tech_names_and_addresses_are_not_links(self):
        self.edit("Happy to answer any questions.",
                  "I work in Node.js/React, e.g. dashboards, and reply from dana.levi@example.com. "
                  "Happy to answer any questions.")
        self.passes()

    def test_an_older_profile_cannot_record_a_project(self):
        self.profile.pop("portfolio")
        self.profile["hooks"] = ["Launch Playbook", "Churn Study", "Pricing Page Test"]
        self.save()
        self.passes()
        self.record()
        self.fails("profile.json has no portfolio catalog")


class Examples(Sandbox):
    """The fictional example shows the whole shape: a catalog, and an application recording its pick."""

    def test_the_example_profile_has_a_complete_catalog(self):
        self.assertNotIn("hooks", self.profile)
        self.assertIn("CATALOG OK", self.ok("portfolio", "check"))

    def test_the_example_application_records_and_cites_its_project(self):
        text = (REPO / "examples" / "acme-robotics" / "messages.md").read_text(encoding="utf-8")
        link = next(e["link"] for e in self.profile["portfolio"] if e["id"] == "launch-playbook")
        self.assertIn("portfolio: launch-playbook\n", text)
        self.assertIn(f"portfolio_link: {link}\n", text)
        folder = self.root / "outreach" / "acme"
        folder.mkdir()
        shutil.copy(self.root / "profile" / "cv.pdf", folder / "cv.pdf")
        (folder / "messages.md").write_text(text, encoding="utf-8")
        self.assertTrue(self.ok("validate", str(folder / "messages.md")).startswith("PASS"))

    def test_the_template_profile_shows_a_catalog_entry(self):
        tpl = json.loads((REPO / "profile" / "profile.example.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", tpl)
        keys = set(tpl["portfolio"][0])
        self.assertTrue({"id", "name", "link", "shareable", "own_part", "proof", "skills", "fits"} <= keys)


if __name__ == "__main__":
    unittest.main()
