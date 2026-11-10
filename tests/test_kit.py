"""Tests for the scripts. Stdlib only. Run from the repo root:

    python3 -m unittest discover tests -v

Each test builds a throwaway copy of the kit in a temp folder; no email is sent and no
network is used (the mail server is replaced by a fake)."""
import contextlib
import importlib
import io
import json
import re
import shutil
import smtplib
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "validate", "tracker", "mail", "hunter")


class FakeSMTP:
    sent = []
    fail_at = None  # index of the message that the server refuses

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **k):
        pass

    def login(self, user, password):
        FakeSMTP.login_seen = (user, password)

    def send_message(self, msg):
        if FakeSMTP.fail_at == len(FakeSMTP.sent):
            raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no such user")})
        FakeSMTP.sent.append(msg)


class Kit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach").mkdir()
        shutil.copy(REPO / "examples" / "cv.pdf", self.root / "profile" / "cv.pdf")
        prof = json.loads((REPO / "examples" / "profile.json").read_text(encoding="utf-8"))
        prof["cvs"] = [{"file": "profile/cv.pdf", "use_when": "default"}]
        self.profile = prof
        self.save_profile()
        (self.root / ".env").write_text(
            "MAIL_ADDRESS=dana.levi@example.com\nMAIL_APP_PASSWORD=abcd efgh ijkl mnop\n", encoding="utf-8")
        for m in MODS:
            sys.modules.pop(m, None)
        sys.path.insert(0, str(self.root / "scripts"))
        self.mail = importlib.import_module("mail")
        self.real_smtp = (smtplib.SMTP_SSL, smtplib.SMTP)
        smtplib.SMTP_SSL = smtplib.SMTP = FakeSMTP
        FakeSMTP.sent, FakeSMTP.fail_at = [], None
        self.run_cmd("tracker", "init")
        self.app("acme")

    def tearDown(self):
        smtplib.SMTP_SSL, smtplib.SMTP = self.real_smtp
        sys.path.remove(str(self.root / "scripts"))
        for m in MODS:
            sys.modules.pop(m, None)
        self.tmp.cleanup()

    # ----- helpers -----
    def save_profile(self):
        (self.root / "profile" / "profile.json").write_text(json.dumps(self.profile), encoding="utf-8")

    def app(self, slug, role=None, status="submitted", applied=None, edit=None):
        """Create outreach/<slug>/ from the example, with a log row."""
        folder = self.root / "outreach" / slug
        folder.mkdir()
        shutil.copy(self.root / "profile" / "cv.pdf", folder / "cv.pdf")
        text = (REPO / "examples" / "acme-robotics" / "messages.md").read_text(encoding="utf-8")
        text = text.replace("applied: 2026-01-12", f"applied: {applied or date.today().isoformat()}")
        if role:
            text = text.replace("Senior Product Marketing Manager", role)
        if edit:
            text = edit(text)
        (folder / "messages.md").write_text(text, encoding="utf-8")
        with (self.root / "outreach" / "log.md").open("a", encoding="utf-8") as f:
            f.write(f"| {date.today()} | Acme Robotics | {role or 'Senior Product Marketing Manager'} | "
                    f"https://example.com/job | greenhouse | cv.pdf | | | {status} | outreach/{slug}/ |\n")
        return folder

    def edit(self, slug, old, new):
        p = self.root / "outreach" / slug / "messages.md"
        t = p.read_text(encoding="utf-8")
        self.assertIn(old, t)
        p.write_text(t.replace(old, new), encoding="utf-8")

    def run_cmd(self, mod, *argv):
        """Run a script's main(); return (exit code, stdout, stderr)."""
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

    def refused(self, mod, *argv, why=""):
        code, out, err = self.run_cmd(mod, *argv)
        self.assertEqual(code, 2, f"expected a hard-fail, got exit {code}\n{out}{err}")
        self.assertIn("HARD-FAIL", err)
        self.assertNotIn("Traceback", err)
        self.assertIn(why, err)
        return err

    def page_code(self):
        html = (self.root / "outreach" / "preview.html").read_text(encoding="utf-8")
        return re.search(r"send (\d{6})", html).group(1)

    def green_light(self, *slugs, extra=()):
        out = self.ok("mail", "preview", *slugs, "--no-open", *extra)
        self.assertNotIn(self.page_code(), out, "the approval code must not reach the assistant's output")
        self.ok("mail", "approve", "--code", self.page_code(), "--quote", "send")

    def shift_clock(self, **delta):
        real = self.mail.now
        self.mail.now = lambda: real() + timedelta(**delta)

    def sent_rows(self, slug):
        p = self.root / "outreach" / slug / "sent.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


class Validator(Kit):
    def test_example_passes(self):
        out = self.ok("validate", str(REPO / "examples/acme-robotics/messages.md"))
        self.assertTrue(out.startswith("PASS"))

    def fails(self, old, new, expect):
        self.edit("acme", old, new)
        code, out, _ = self.run_cmd("validate", "outreach/acme/messages.md".replace("outreach", str(self.root / "outreach")))
        self.assertEqual(code, 1, out)
        self.assertIn(expect, out)

    def test_bracket_placeholder(self):
        self.fails("the warehouse product line", "[specific product line from JD]", "placeholder")

    def test_xx_placeholder(self):
        self.fails("from 11% to 16% over two quarters, and", "by XX% over two quarters, and", "placeholder")

    def test_banned_any_case(self):
        self.fails("I would bring the same process", "Passionately, I would bring the same process", "banned 'passionate'")

    def test_same_address_twice(self):
        self.fails("rec_email: tom.reed@example.com", "rec_email: maya.stone@example.com", "same address")

    def test_bad_applied_date(self):
        self.fails(f"applied: {date.today().isoformat()}", "applied: last Monday", "YYYY-MM-DD")

    def test_no_recruiter(self):
        p = self.root / "outreach" / "acme" / "messages.md"
        t = p.read_text(encoding="utf-8")
        t = t.replace("rec_name: Tom Reed", "rec_name: none").replace("rec_email: tom.reed@example.com", "rec_email: none")
        t = re.sub(r"(## T2 recruiter email\n).*?(\n## T3 connection note manager)", r"\1none\n\2", t, flags=re.S)
        t = re.sub(r"(## T3 connection note recruiter\n).*?(\n## T4)", r"\1\nnone\n\2", t, flags=re.S)
        p.write_text(t, encoding="utf-8")
        out = self.ok("validate", str(p))
        self.assertIn("T2=none", out)

    def test_known_name_without_address(self):
        self.edit("acme", "hm_email: maya.stone@example.com", "hm_email: none")
        self.edit("acme", " I also wrote to Maya Stone.", "")
        p = self.root / "outreach" / "acme" / "messages.md"
        t = re.sub(r"(## T1 manager email\n).*?(\n## T2)", r"\1none\n\2", p.read_text(encoding="utf-8"), flags=re.S)
        p.write_text(t, encoding="utf-8")
        self.assertIn("T1=none", self.ok("validate", str(p)))

    def test_hiring_team_address(self):
        self.edit("acme", "rec_name: Tom Reed", "rec_name: Hiring Team")
        self.edit("acme", "Hi Tom,\n\nI submitted", "Hi Hiring Team,\n\nI submitted")
        p = self.root / "outreach" / "acme" / "messages.md"
        t = re.sub(r"(## T3 connection note recruiter\n).*?(\n## T4)", r"\1\nnone\n\2", p.read_text(encoding="utf-8"), flags=re.S)
        p.write_text(t, encoding="utf-8")
        self.ok("validate", str(p))


class ProfileCheck(Kit):
    def bad(self, why="", **messages):
        self.profile["messages"] = messages
        self.save_profile()
        self.refused("validate", "--check-profile", why=why)

    def test_good(self):
        self.assertIn("PROFILE OK", self.ok("validate", "--check-profile"))

    def test_subject_placeholder(self):
        self.bad(subject="{Company} application", why="messages.subject")

    def test_greeting_placeholder(self):
        self.bad(greeting="Hi {name},", why="messages.greeting")

    def test_word_limits_text(self):
        self.bad(word_limits={"T1": "120-180"}, why="word_limits")

    def test_bad_regex(self):
        self.bad(opener_regex="(applied", why="regular expression")

    def test_messages_not_object(self):
        self.profile["messages"] = ["x"]
        self.save_profile()
        self.refused("validate", "--check-profile", why="messages")

    def test_empty_signature_phone(self):
        self.profile["signature_phone"] = ""
        self.save_profile()
        self.refused("validate", "--check-profile", why="signature_phone")

    def test_inline_flag_in_regex(self):
        self.profile["messages"] = {"opener_regex": "(?i)(applied|submitted an application)"}
        self.save_profile()
        self.assertTrue(self.ok("validate", str(self.root / "outreach/acme/messages.md")).startswith("PASS"))

    def test_blank_name(self):
        self.profile["name"] = "   "
        self.save_profile()
        self.refused("validate", "--check-profile", why="'name'")

    def test_empty_link(self):
        self.profile["links"] = {"LinkedIn": ""}
        self.save_profile()
        self.refused("validate", "--check-profile", why="links")


class SendGate(Kit):
    def test_happy_path_and_one_time_approval(self):
        self.refused("mail", "send", "acme", why="not approved")
        self.green_light("acme")
        self.ok("mail", "send", "acme")
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com", "tom.reed@example.com"])
        self.assertTrue(all(any(p.get_filename() == "cv.pdf" for p in m.iter_attachments()) for m in FakeSMTP.sent))
        self.assertEqual(FakeSMTP.login_seen[1], "abcdefghijklmnop")
        self.assertEqual([r["key"] for r in self.sent_rows("acme")], ["hm", "rec"])
        self.refused("mail", "send", "acme", why="not approved")
        self.refused("mail", "approve", "--code", "000000", "--quote", "send", why="no preview is waiting")
        self.assertEqual(len(FakeSMTP.sent), 2)

    def test_wrong_code_cancels_after_three_tries(self):
        self.ok("mail", "preview", "acme", "--no-open")
        wrong = "111111" if self.page_code() != "111111" else "222222"
        for _ in range(2):
            self.refused("mail", "approve", "--code", wrong, "--quote", "send", why="wrong code")
        self.refused("mail", "approve", "--code", wrong, "--quote", "send", why="cancelled")
        self.refused("mail", "approve", "--code", self.page_code(), "--quote", "send", why="no preview is waiting")

    def test_code_accepts_the_owners_phrase(self):
        self.ok("mail", "preview", "acme", "--no-open")
        self.ok("mail", "approve", "--code", f"send {self.page_code()}", "--quote", "send it")

    def test_edit_after_preview(self):
        self.ok("mail", "preview", "acme", "--no-open")
        self.edit("acme", "a short call.", "a short call this week.")
        self.refused("mail", "approve", "--code", self.page_code(), "--quote", "send", why="changed after the preview")

    def test_edit_after_approval(self):
        self.green_light("acme")
        self.edit("acme", "a short call.", "a short call this week.")
        self.refused("mail", "send", "acme", why="changed after approval")
        self.assertEqual(FakeSMTP.sent, [])

    def test_preview_expires(self):
        self.ok("mail", "preview", "acme", "--no-open")
        code = self.page_code()
        self.shift_clock(minutes=31)
        self.refused("mail", "approve", "--code", code, "--quote", "send", why="minutes old")

    def test_approval_expires_and_cannot_be_renewed(self):
        self.green_light("acme")
        code = self.page_code()
        self.shift_clock(minutes=31)
        self.refused("mail", "send", "acme", why="minutes old")
        self.refused("mail", "approve", "--code", code, "--quote", "send", why="no preview is waiting")

    def test_only_one_contact(self):
        self.green_light("acme", extra=("--only", "rec"))
        self.ok("mail", "send", "acme")
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["tom.reed@example.com"])

    def test_partial_failure_then_retry(self):
        self.green_light("acme")
        FakeSMTP.fail_at = 1
        self.refused("mail", "send", "acme", why="SMTP error")
        self.assertEqual([r["key"] for r in self.sent_rows("acme")], ["hm"])
        FakeSMTP.fail_at = None
        self.ok("mail", "send", "acme")
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com", "tom.reed@example.com"])
        self.refused("mail", "send", "acme", why="not approved")

    def test_same_person_second_application(self):
        self.green_light("acme")
        self.ok("mail", "send", "acme")
        self.app("acme-pmm", role="Product Marketing Manager")
        self.refused("mail", "preview", "acme-pmm", "--no-open", why="already emailed")
        self.ok("mail", "preview", "acme-pmm", "--no-open", "--repeat-ok")
        self.assertIn("already emailed", (self.root / "outreach" / "preview.html").read_text(encoding="utf-8"))

    def test_same_person_twice_in_one_batch(self):
        self.app("acme-pmm", role="Product Marketing Manager")
        self.refused("mail", "preview", "acme", "acme-pmm", "--no-open", why="one person gets")

    def test_batch_of_two(self):
        self.app("globex", edit=lambda t: t.replace("maya.stone@", "m.stone@").replace("tom.reed@", "t.reed@"))
        self.green_light("acme", "globex")
        self.ok("mail", "send", "acme", "globex")
        self.assertEqual(len(FakeSMTP.sent), 4)

    def test_do_not_contact(self):
        with (self.root / "outreach" / "do-not-contact.md").open("a", encoding="utf-8") as f:
            f.write("@example.com  asked 2026-01-01\n")
        self.refused("mail", "preview", "acme", "--no-open", why="do-not-contact")

    def test_application_not_in_yet(self):
        for n, status in enumerate(("handoff-pending", "Started", "", "in progress")):
            self.app(f"globex{n}", status=status,
                     edit=lambda t: t.replace("maya.stone@", "m.stone@").replace("tom.reed@", "t.reed@"))
            self.refused("mail", "preview", f"globex{n}", "--no-open", why="Status")

    def test_record_failure_never_resends(self):
        self.green_light("acme")
        real = self.mail.write_json
        calls = []

        def flaky(path, data):
            calls.append(path.name)
            if path.name == "sent.json" and calls.count("sent.json") == 2:  # the write after the send
                raise PermissionError(13, "locked")
            real(path, data)
        self.mail.write_json = flaky
        self.refused("mail", "send", "acme", why="WAS SENT")
        self.mail.write_json = real
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com"])
        self.ok("mail", "send", "acme")  # the retry sends only the email that has not gone
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com", "tom.reed@example.com"])
        self.refused("mail", "preview", "acme", "--no-open", "--only", "hm", why="never confirmed")
        self.refused("mail", "send", "acme", why="not approved")

    def test_one_send_at_a_time(self):
        self.green_light("acme")
        (self.root / "outreach" / "send.lock").write_text("", encoding="utf-8")
        self.refused("mail", "send", "acme", why="another send is running")
        self.assertEqual(FakeSMTP.sent, [])
        (self.root / "outreach" / "send.lock").unlink()
        self.ok("mail", "send", "acme")
        self.assertFalse((self.root / "outreach" / "send.lock").exists())

    def test_flags_on_the_wrong_command(self):
        self.green_light("acme")
        self.refused("mail", "send", "acme", "--only", "hm", why="belong to preview")
        self.assertEqual(FakeSMTP.sent, [])

    def test_cancel_and_new_preview_withdraw_the_approval(self):
        self.green_light("acme")
        self.ok("mail", "cancel")
        self.refused("mail", "send", "acme", why="not approved")
        self.green_light("acme")
        self.ok("mail", "preview", "acme", "--no-open", "--only", "hm")
        self.refused("mail", "send", "acme", why="not approved")
        self.assertEqual(FakeSMTP.sent, [])

    def test_moving_a_person_to_the_other_slot(self):
        self.green_light("acme", extra=("--only", "rec"))
        self.ok("mail", "send", "acme")
        self.edit("acme", "hm_email: maya.stone@example.com", "hm_email: tom.reed@example.com")
        self.edit("acme", "rec_email: tom.reed@example.com", "rec_email: none")
        self.refused("mail", "preview", "acme", "--no-open", why="already sent")

    def test_batch_fails_partway_then_retry_the_rest(self):
        self.app("globex", edit=lambda t: t.replace("maya.stone@", "m.stone@").replace("tom.reed@", "t.reed@"))
        self.green_light("acme", "globex")
        FakeSMTP.fail_at = 3
        self.refused("mail", "send", "acme", "globex", why="SMTP error")
        FakeSMTP.fail_at = None
        self.refused("mail", "send", "acme", "globex", why="already gone")
        self.ok("mail", "send", "globex")
        self.assertEqual(len(FakeSMTP.sent), 4)
        self.assertEqual(len({m["To"] for m in FakeSMTP.sent}), 4)

    def test_cv_changed_after_approval(self):
        self.green_light("acme")
        with (self.root / "outreach" / "acme" / "cv.pdf").open("ab") as f:
            f.write(b"x")
        self.refused("mail", "send", "acme", why="changed after approval")

    def test_do_not_contact_added_after_approval(self):
        self.green_light("acme")
        with (self.root / "outreach" / "do-not-contact.md").open("a", encoding="utf-8") as f:
            f.write("- Tom Reed <tom.reed@example.com>, asked 2026-01-01\n")
        self.refused("mail", "send", "acme", why="do-not-contact")
        self.assertEqual(FakeSMTP.sent, [])

    def test_do_not_contact_unreadable_line(self):
        with (self.root / "outreach" / "do-not-contact.md").open("a", encoding="utf-8") as f:
            f.write("that recruiter at Globex\n")
        self.refused("mail", "preview", "acme", "--no-open", why="line")

    def test_test_command_changes_nothing(self):
        self.green_light("acme")
        self.ok("mail", "test", "acme")
        self.assertEqual({m["To"] for m in FakeSMTP.sent}, {"dana.levi@example.com"})
        self.assertEqual(self.sent_rows("acme"), [])
        self.ok("mail", "send", "acme")

    def test_today_must_be_true(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.edit("acme", f"applied: {date.today().isoformat()}", f"applied: {yesterday}")
        self.refused("mail", "preview", "acme", "--no-open", why="says 'today'")

    def test_daily_cap(self):
        self.profile["max_emails_per_day"] = 1
        self.save_profile()
        self.refused("mail", "preview", "acme", "--no-open", why="daily cap")

    def test_damaged_record_is_not_a_traceback(self):
        (self.root / "outreach" / "acme" / "sent.json").write_text("{not json", encoding="utf-8")
        self.refused("mail", "preview", "acme", "--no-open", why="damaged")

    def test_nudge(self):
        self.green_light("acme")
        self.ok("mail", "send", "acme")
        first_id = self.sent_rows("acme")[0]["message_id"]
        with (self.root / "outreach" / "acme" / "messages.md").open("a", encoding="utf-8") as f:
            f.write("\n## N1 nudge manager\n\nHi Maya,\n\nI wrote last week about the Senior Product "
                    "Marketing Manager role. I am still very interested and would be glad to do a "
                    "short call whenever suits you.\n\nBest regards,\nDana Levi\n050-000-0000\n")
        self.refused("mail", "preview", "acme", "--no-open", why="nudge waits")
        self.shift_clock(days=6)
        self.green_light("acme")
        self.ok("mail", "send", "acme")
        nudge = FakeSMTP.sent[-1]
        self.assertEqual(nudge["In-Reply-To"], first_id)
        self.assertTrue(nudge["Subject"].startswith("Re: "))
        self.assertEqual(list(nudge.iter_attachments()), [])
        self.assertEqual(len(FakeSMTP.sent), 3)


class EnvFile(Kit):
    def test_tolerant_parsing(self):
        (self.root / ".env").write_text(
            "﻿export HUNTER_API_KEY=abc123  # my key\nMAIL_ADDRESS=\"a@b.co\"\nMAIL_APP_PASSWORD=pw # note\n",
            encoding="utf-8")
        vals = importlib.import_module("_common").env("HUNTER_API_KEY", "MAIL_ADDRESS", "MAIL_APP_PASSWORD")
        self.assertEqual((vals["HUNTER_API_KEY"], vals["MAIL_ADDRESS"], vals["MAIL_APP_PASSWORD"]),
                         ("abc123", "a@b.co", "pw"))

    def test_bad_port(self):
        with (self.root / ".env").open("a", encoding="utf-8") as f:
            f.write("SMTP_PORT=five\n")
        self.refused("mail", "test", "acme", why="SMTP_PORT")


class Tracker(Kit):
    def test_reply_pairs_by_role(self):
        self.app("acme-pmm", role="Product Marketing Manager", status="started")
        with (self.root / "outreach" / "replies.md").open("a", encoding="utf-8") as f:
            f.write("| Acme Robotics | Product Marketing Manager | Yes | 2026-01-20 | Tom | Interview | |\n")
        self.ok("tracker", "build")
        rows = (self.root / "outreach" / "applications.csv").read_text(encoding="utf-8-sig").splitlines()
        self.assertIn("Pending", rows[1])
        self.assertIn("Interview", rows[2])

    def test_unknown_reply_row(self):
        with (self.root / "outreach" / "replies.md").open("a", encoding="utf-8") as f:
            f.write("| Acme Robotics | Some Other Role | Yes | | | Interview | |\n")
        self.refused("tracker", "build", why="must match")

    def test_missing_separator(self):
        p = self.root / "outreach" / "log.md"
        lines = p.read_text(encoding="utf-8").splitlines()
        p.write_text("\n".join([lines[0]] + lines[2:]) + "\n", encoding="utf-8")
        self.refused("tracker", "build", why="separator")

    def test_formula_cells_are_neutralised(self):
        self.app("evil", role="=HYPERLINK(1)")
        self.ok("tracker", "build")
        self.assertIn("'=HYPERLINK(1)", (self.root / "outreach" / "applications.csv").read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
