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


if __name__ == "__main__":
    unittest.main()
