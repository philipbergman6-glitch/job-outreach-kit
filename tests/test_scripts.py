"""Tests for network.py, cv.py, hunter.py, file encodings and isolated-mode startup. Stdlib only,
no network: each test works in a throwaway copy of scripts/, outside calls replaced by fakes."""
import contextlib
import importlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "network", "triage", "validate", "accounts", "cv", "hunter")
CSV_HEAD = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"


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




class FakeReply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Hunter(Sandbox):
    """hunter.py goes through _common.http: the kit's User-Agent, a wait and retry on 429, one
    HARD-FAIL line naming Hunter on an error, and the API key never printed."""
    KEY = "test-key-not-real-123"
    DOMAIN = {"data": {"domain": "acme.com", "pattern": "{first}.{last}", "organization": "Acme",
                       "emails": [{"value": "dana.levi@acme.com", "confidence": 94, "first_name": "Dana",
                                   "last_name": "Levi", "position": "VP Marketing"}]}}

    def setUp(self):
        super().setUp()
        (self.root / ".env").write_text(f"HUNTER_API_KEY={self.KEY}\n", encoding="utf-8")
        self.calls = []
        self.replies = []
        p = mock.patch.object(urllib.request.OpenerDirector, "open", self.urlopen)  # every request, pinned or not
        p.start()
        self.addCleanup(p.stop)
        s = mock.patch("time.sleep", lambda secs: None)
        s.start()
        self.addCleanup(s.stop)

    def urlopen(self, req, data=None, timeout=None):  # replaces OpenerDirector.open
        self.calls.append(req)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return FakeReply(json.dumps(r).encode())

    def error(self, code, body=b"", headers=None):
        return urllib.error.HTTPError("https://api.hunter.io/v2/x", code, "err", headers or {}, io.BytesIO(body))

    def test_domain_search_sends_the_kit_user_agent_and_prints_the_pattern(self):
        import _common
        self.replies = [self.DOMAIN]
        code, out, err = self.run_cmd("hunter", "domain", "acme.com")
        self.assertEqual(code, 0, err)
        self.assertIn("pattern={first}.{last}", out)
        self.assertIn("dana.levi@acme.com", out)
        self.assertEqual(self.calls[0].get_header("User-agent"), _common.UA)
        self.assertIn("domain=acme.com", self.calls[0].full_url)

    def test_a_429_is_waited_out_and_retried(self):
        self.replies = [self.error(429, b"slow down", {"Retry-After": "1"}), self.DOMAIN]
        code, out, err = self.run_cmd("hunter", "domain", "acme.com")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.calls), 2)

    def test_an_api_error_is_one_line_naming_hunter_without_the_key(self):
        self.replies = [self.error(401, b'{"errors":[{"details":"No user found for the API key supplied"}]}')]
        err = self.refused("hunter", "verify", "dana@acme.com", why=("Hunter", "401", "No user found"))
        self.assertNotIn(self.KEY, err)

    def test_a_certificate_failure_names_the_fix(self):
        import ssl
        self.replies = [urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))]
        err = self.refused("hunter", "quota", why=("Hunter", "Install Certificates"))
        self.assertNotIn(self.KEY, err)

    def test_missing_key_and_bad_usage_hard_fail(self):
        (self.root / ".env").write_text("OTHER=1\n", encoding="utf-8")
        self.refused("hunter", "quota", why=("HUNTER_API_KEY",))
        self.refused("hunter", "find", "acme.com", "Dana", why=("Usage",))
        self.assertEqual(self.calls, [])

    def test_find_and_quota_print_their_fields(self):
        self.replies = [{"data": {"email": "dana.levi@acme.com", "score": 91, "verification": {"status": "valid"},
                                  "position": "VP"}},
                        {"data": {"requests": {"searches": {"used": 3, "available": 25},
                                               "verifications": {"used": 1, "available": 50}},
                                  "reset_date": "2026-12-01"}}]
        out = self.run_cmd("hunter", "find", "acme.com", "Dana", "Levi")[1]
        self.assertIn("email=dana.levi@acme.com score=91", out)
        self.assertIn('"status": "valid"', out)
        out = self.run_cmd("hunter", "quota")[1]
        self.assertIn("searches 3/25", out)
        self.assertIn("reset=2026-12-01", out)

class IsolatedMode(unittest.TestCase):
    """python3 -I (the safe way to run a script near downloaded files) leaves the script's own
    folder off the import path; every script must still find _common beside it."""
    SCRIPTS = ("accounts", "cv", "emails", "hunter", "jobs", "network", "search", "triage", "validate")

    def test_each_script_starts_under_dash_I(self):
        with tempfile.TemporaryDirectory() as cwd:  # an unrelated folder, as a user's shell would be
            for name in self.SCRIPTS:
                r = subprocess.run([sys.executable, "-I", str(REPO / "scripts" / f"{name}.py"), "--help"],
                                   cwd=cwd, capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 0, f"{name}.py: {r.stderr[-400:]}")
                self.assertNotIn("ModuleNotFoundError", r.stderr, name)

    def test_the_folder_is_not_added_twice(self):
        r = subprocess.run([sys.executable, "-c", "import runpy, sys; sys.argv = ['triage.py', 'format']; "
                            f"sys.path.insert(0, {str(REPO / 'scripts')!r}); "
                            f"runpy.run_path({str(REPO / 'scripts' / 'triage.py')!r}, run_name='__main__'); "
                            f"print(sys.path.count({str(REPO / 'scripts')!r}), file=sys.stderr)"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr.strip().splitlines()[-1], "1")

if __name__ == "__main__":
    unittest.main()
