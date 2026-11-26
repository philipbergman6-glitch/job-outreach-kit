"""Tests for network.py, cv.py, hunter.py, file encodings and isolated-mode startup. Stdlib only,
no network: each test works in a throwaway copy of scripts/, outside calls replaced by fakes."""
import contextlib
import importlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "network", "triage", "validate", "accounts", "cv", "hunter")
CSV_HEAD = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach" / "jobs").mkdir(parents=True)
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

    def refused(self, mod, *argv, why=()):
        code, out, err = self.run_cmd(mod, *argv)
        self.assertEqual(code, 2, f"expected a hard-fail, got exit {code}\n{out}{err}")
        self.assertIn("HARD-FAIL", err)
        self.assertNotIn("unexpected", err)
        for w in why:
            self.assertIn(w, err)
        return err


class Encodings(Sandbox):
    """Excel and Windows Notepad save in a legacy code page, not UTF-8."""
    ROW = "Noa,Cohen,https://www.linkedin.com/in/noa-example,,Café Société,VP,03 Mar 2024\n"

    def csv(self, data):
        p = self.root / "profile" / "connections.csv"
        p.write_bytes(data)
        return p

    def test_a_windows_1252_csv_export_is_read(self):
        self.csv((CSV_HEAD + self.ROW).encode("cp1252"))
        code, out, err = self.run_cmd("network", "match", "Café Société")
        self.assertEqual(code, 0, out + err)
        self.assertIn("| exact | Noa Cohen |", out)

    def test_utf8_with_and_without_bom_and_utf16_are_read(self):
        for data in ((CSV_HEAD + self.ROW).encode("utf-8"), (CSV_HEAD + self.ROW).encode("utf-8-sig"),
                     (CSV_HEAD + self.ROW).encode("utf-16")):
            self.csv(data)
            code, out, err = self.run_cmd("network", "match", "Café Société")
            self.assertEqual(code, 0, out + err)
            self.assertIn("Noa Cohen", out)

    def test_a_csv_in_no_known_encoding_names_the_file_and_the_fix(self):
        self.csv(CSV_HEAD.encode() + b"Noa,Cohen,x,,Acme \x81\x8d,VP,03 Mar 2024\n")
        self.refused("network", "match", "Acme", why=("connections.csv", "UTF-8"))

    def test_a_shortlist_not_in_utf8_names_the_file_and_the_fix(self):
        p = self.root / "outreach" / "triage-2026-11-17.md"
        p.write_bytes("## Dropped\n| Company | Role | Link | JD file | Reason | Quote |\n|---|---|---|---|---|---|\n"
                      "| Café | x | https://c.io/1 | - | stale | - |\n".encode("cp1252"))
        self.refused("triage", "check", str(p), why=("triage-2026-11-17.md", "UTF-8"))

    def test_a_profile_not_in_utf8_names_the_file(self):
        p = self.root / "profile" / "profile.json"
        p.write_bytes('{"name": "José"}'.encode("cp1252"))
        self.refused("validate", "--check-profile", "--profile", str(p), why=("profile.json", "UTF-8"))


if __name__ == "__main__":
    unittest.main()
