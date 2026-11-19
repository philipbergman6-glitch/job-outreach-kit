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
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "validate", "accounts", "tracker", "mail", "hunter", "network", "cv")


class FakeSMTP:
    sent = []
    fail_at = None  # index of the message that the server refuses
    drop_at = None  # index of the message after which the connection drops

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
        if FakeSMTP.drop_at == len(FakeSMTP.sent) - 1:  # delivered, then the line broke
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")


class Kit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach").mkdir()
        shutil.copy(REPO / "examples" / "cv.pdf", self.root / "profile" / "cv.pdf")
        shutil.copy(REPO / "examples" / "cv.txt", self.root / "profile" / "cv.txt")
        shutil.copy(REPO / "examples" / "brief.md", self.root / "profile" / "brief.md")
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
        FakeSMTP.sent, FakeSMTP.fail_at, FakeSMTP.drop_at = [], None, None
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

    def tailor(self, cv_from=True, record=True):
        """Make acme's snapshot a CV tailored for this job, as apply.md step 0.8 leaves it."""
        folder = self.root / "outreach" / "acme"
        shutil.copy(folder / "cv.pdf", folder / "cv-acme.pdf")
        shutil.copy(self.root / "profile" / "cv.txt", folder / "cv-acme.txt")
        (folder / "cv.pdf").unlink()
        if record:
            (folder / "cv-tailoring.md").write_text(
                "# CV tailoring: Acme Robotics\nFrom: cv.pdf\n1. Launch Playbook bullet moved to the top.\n"
                "Owner approved: 2026-11-19\n", encoding="utf-8")
        self.edit("acme", "cv: cv.pdf", "cv: cv-acme.pdf" + ("\ncv_from: cv.pdf" if cv_from else ""))

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
        self.real_now = real = getattr(self, "real_now", self.mail.now)
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

    def test_address_must_be_plain(self):
        """Brackets, a comma or mailto: would slip past do-not-contact and the repeat check."""
        for bad in ("<tom.reed@example.com>", "tom.reed@example.com,", "mailto:tom.reed@example.com",
                    "Tom Reed <tom.reed@example.com>", "tom.reed@example"):
            with self.subTest(bad=bad):
                try:
                    self.fails("rec_email: tom.reed@example.com", f"rec_email: {bad}", "is not an address")
                finally:
                    self.edit("acme", f"rec_email: {bad}\n", "rec_email: tom.reed@example.com\n")

    def test_unknown_heading_is_refused(self):
        """A miscased heading would fold that text into the email above it."""
        p = self.root / "outreach" / "acme" / "messages.md"
        with p.open("a", encoding="utf-8") as f:
            f.write("\n## N2 Nudge Recruiter\nHi Tom,\n")
        self.refused("validate", str(p), why="N2 Nudge Recruiter")

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

    def test_tailored_cv_passes(self):
        self.tailor()
        self.ok("validate", str(self.root / "outreach" / "acme" / "messages.md"))

    def fails_as_is(self, expect):
        code, out, _ = self.run_cmd("validate", str(self.root / "outreach" / "acme" / "messages.md"))
        self.assertEqual(code, 1, out)
        self.assertIn(expect, out)

    def test_tailored_cv_must_name_its_profile_cv(self):
        self.tailor(cv_from=False)
        self.fails_as_is("cv_from")

    def test_cv_from_none_means_not_tailored(self):
        self.tailor()
        self.edit("acme", "cv_from: cv.pdf", "cv_from: none")
        self.fails_as_is("cv 'cv-acme.pdf' is not a profile CV")

    def test_tailoring_record_must_name_the_same_source(self):
        self.tailor()
        rec = self.root / "outreach" / "acme" / "cv-tailoring.md"
        rec.write_text(rec.read_text(encoding="utf-8").replace("From: cv.pdf", "From: other.pdf"), encoding="utf-8")
        self.fails_as_is("cv-tailoring.md does not name cv.pdf")

    def test_snapshot_cv_must_be_a_pdf(self):
        self.tailor()
        folder = self.root / "outreach" / "acme"
        (folder / "cv-acme.pdf").rename(folder / "cv-acme.docx")
        self.edit("acme", "cv: cv-acme.pdf", "cv: cv-acme.docx")
        self.fails_as_is("must be a PDF")

    def test_tailored_cv_from_an_unknown_cv_fails(self):
        self.tailor()
        self.fails("cv_from: cv.pdf", "cv_from: other.pdf", "cv_from 'other.pdf' is not a profile CV")

    def test_tailored_cv_needs_its_tailoring_record(self):
        self.tailor(record=False)
        self.fails_as_is("cv-tailoring.md")

    def test_hiring_team_address(self):
        self.edit("acme", "rec_name: Tom Reed", "rec_name: Hiring Team")
        self.edit("acme", "Hi Tom,\n\nI submitted", "Hi Hiring Team,\n\nI submitted")
        p = self.root / "outreach" / "acme" / "messages.md"
        t = re.sub(r"(## T3 connection note recruiter\n).*?(\n## T4)", r"\1\nnone\n\2", p.read_text(encoding="utf-8"), flags=re.S)
        p.write_text(t, encoding="utf-8")
        self.ok("validate", str(p))


class FactCheck(Kit):
    """Numbers and scope verbs in the messages and the tailored CV must trace to the profile CV's
    text or brief.md. Narrow on purpose: spelled-out numbers, years, the phone and links pass."""
    def path(self):
        return str(self.root / "outreach" / "acme" / "messages.md")

    def fails(self, old, new, expect):
        self.edit("acme", old, new)
        code, out, _ = self.run_cmd("validate", self.path())
        self.assertEqual(code, 1, out)
        self.assertIn(expect, out)

    def test_a_number_in_no_source_fails(self):
        self.fails("It raised trial-to-paid conversion from 11% to 16%",
                   "It raised trial-to-paid conversion from 11% to 19%", "19")

    def test_years_and_spelled_numbers_pass(self):
        self.edit("acme", "and have five years in B2B marketing.",
                  "and have worked in B2B marketing since 2021, five years in all.")
        self.ok("validate", self.path())

    def test_a_verb_that_climbs_above_its_source_fails(self):
        """The CV says "Helped run the pricing page A/B test"; leading it is a bigger claim."""
        self.fails("Owning launches end to end, as the job description asks, is the work I do now.",
                   "I also led the pricing page A/B test that lifted demo requests by 9%.", "led")

    def test_the_same_tier_as_the_source_passes(self):
        self.edit("acme", "Owning launches end to end, as the job description asks, is the work I do now.",
                  "I also helped run the pricing page A/B test that lifted demo requests by 9%.")
        self.ok("validate", self.path())

    def test_someone_elses_verb_and_nouns_are_not_claims(self):
        self.edit("acme", "Owning launches end to end, as the job description asks, is the work I do now.",
                  "The growth team led the pricing page A/B test, and I helped run it. It generated sales leads.")
        self.ok("validate", self.path())

    def test_digits_for_a_spelled_number_and_dates_pass(self):
        self.edit("acme", "and have five years in B2B marketing.", "and have 5 years in B2B marketing.")
        self.edit("acme", "Owning launches end to end, as the job description asks, is the work I do now.",
                  "I applied on 19 November.")
        self.ok("validate", self.path())

    def test_a_figure_from_the_job_description_passes(self):
        (self.root / "outreach" / "acme" / "jd.md").write_text("You will launch 3 product lines a year.",
                                                                encoding="utf-8")
        self.edit("acme", "Owning launches end to end, as the job description asks, is the work I do now.",
                  "Your posting names 3 product lines a year.")
        self.ok("validate", self.path())

    def test_tailored_cv_text_is_checked(self):
        self.tailor()
        p = self.root / "outreach" / "acme" / "cv-acme.txt"
        p.write_text(p.read_text(encoding="utf-8") + "\nGrew pipeline by 40% in one quarter.\n", encoding="utf-8")
        code, out, _ = self.run_cmd("validate", self.path())
        self.assertEqual(code, 1, out)
        self.assertIn("cv-acme.txt", out)
        self.assertIn("40", out)

    def test_tailored_cv_needs_its_text(self):
        self.tailor()
        (self.root / "outreach" / "acme" / "cv-acme.txt").unlink()
        code, out, _ = self.run_cmd("validate", self.path())
        self.assertEqual(code, 1, out)
        self.assertIn("cv-acme.txt", out)

    def test_profile_cv_needs_its_text(self):
        (self.root / "profile" / "cv.txt").unlink()
        self.refused("validate", "--check-profile", why="cv.txt")

    def test_brief_is_required(self):
        (self.root / "profile" / "brief.md").unlink()
        self.refused("validate", self.path(), why="brief.md")


TRACED = ("I built and ran Launch Playbook, a repeatable launch process, for six releases. "
          "Trial-to-paid conversion rose from 11% to 16% over two quarters.")


class Answers(Kit):
    """Drafted answers to free-text form questions: traced to the CV or brief like the messages,
    approved by the owner before they go in a form, and only approved ones kept in the bank."""
    def write(self, *entries, where="outreach/acme/answers.md"):
        p = self.root / where
        p.write_text("# Form answers\n\n" + "\n\n".join(entries) + "\n", encoding="utf-8")
        return str(p)

    def entry(self, answer=TRACED, approved="no", limit=None, q="Tell us about a launch you are proud of."):
        return f"## {q}\nApproved: {approved}\n" + (f"Limit: {limit}\n" if limit else "") + answer

    def fails(self, path, expect):
        code, out, _ = self.run_cmd("validate", "--answers", path)
        self.assertEqual(code, 1, out)
        self.assertIn(expect, out)

    def test_a_traced_draft_passes_and_waits_for_approval(self):
        out = self.ok("validate", "--answers", self.write(self.entry(), self.entry(approved="2026-11-19", q="Why us?")))
        self.assertIn("PASS", out)
        self.assertIn("1 waiting for the owner", out)

    def test_a_figure_in_no_source_fails(self):
        self.fails(self.write(self.entry(TRACED.replace("16%", "26%"))), "26")

    def test_a_verb_above_its_source_fails(self):
        self.fails(self.write(self.entry("I led the pricing page A/B test that lifted demo requests by 9%.")), "led")

    def test_a_figure_from_the_job_description_passes(self):
        (self.root / "outreach" / "acme" / "jd.md").write_text("You will launch 3 product lines a year.",
                                                                encoding="utf-8")
        self.ok("validate", "--answers", self.write(self.entry(TRACED + " Your 3 product lines suit that.")))

    def test_negotiation_figures_come_from_the_brief_and_the_offer(self):
        """flow/offer.md: a negotiation point quotes the offer and the owner's figure, written to
        brief.md first. form_answers is no source: the Truth rule names the CV and brief only."""
        self.profile["form_answers"]["salary_expectation"] = "38,000 ILS a month"
        self.save_profile()
        brief = self.root / "profile" / "brief.md"
        brief.write_text(brief.read_text(encoding="utf-8") + "\n## Offer\n- Expectation: 34,000 ILS a month\n",
                         encoding="utf-8")
        (self.root / "outreach" / "acme" / "offer.md").write_text("Base salary: 30,000 ILS a month.",
                                                                   encoding="utf-8")
        point = self.entry("The offer's base is 30,000 ILS a month; I asked for 34,000.", q="Base salary")
        self.ok("validate", "--answers", self.write(point, where="outreach/acme/negotiation.md"))
        self.fails(self.write(point.replace("34,000", "38,000"), where="outreach/acme/negotiation.md"), "38000")

    def test_a_placeholder_fails(self):
        self.fails(self.write(self.entry(TRACED + " I admire [COMPANY].")), "placeholder")

    def test_phone_digits_are_no_source(self):
        """The example phone is +972 50 000 0000: '50' must not pass as a figure from the CV."""
        self.fails(self.write(self.entry(TRACED + " A 50% rise came next.")), "50")

    def test_messages_and_answers_in_one_call_are_refused(self):
        self.refused("validate", str(self.root / "outreach" / "acme" / "messages.md"), "--answers",
                     self.write(self.entry()), why="one")

    def test_an_answer_over_the_form_limit_fails(self):
        self.fails(self.write(self.entry(limit=50)), "50")

    def test_the_bank_keeps_only_approved_answers(self):
        self.fails(self.write(self.entry(), where="profile/answers.md"), "approved")
        self.ok("validate", "--answers", self.write(self.entry(approved="2026-11-19"), where="profile/answers.md"))

    def test_a_malformed_file_is_refused(self):
        self.refused("validate", "--answers", self.write("## A question\n" + TRACED), why="Approved")
        self.refused("validate", "--answers", self.write(self.entry(answer="")), why="empty")
        self.refused("validate", "--answers", self.write(self.entry(approved="yes")), why="Approved")
        self.refused("validate", "--answers", str(self.root / "outreach" / "acme" / "nope.md"), why="nope.md")
        self.refused("validate", "--answers", self.write(self.entry(), "##Second question\nApproved: no\n" + TRACED),
                     why="##Second")
        self.refused("validate", "--answers", self.write("An answer with no question.\n\n" + self.entry()),
                     why="before the first")
        self.refused("validate", "--answers", self.write(self.entry(approved="2026-13-40 (Acme)")), why="2026-13-40")


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

    def test_tailored_cv_is_the_attachment(self):
        self.tailor()
        self.green_light("acme")
        self.ok("mail", "send", "acme")
        self.assertEqual(len(FakeSMTP.sent), 2)
        for m in FakeSMTP.sent:
            self.assertEqual([a.get_filename() for a in m.iter_attachments()], ["cv-acme.pdf"])

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
        self.green_light("acme", extra=("--only", "hm"))
        self.ok("mail", "send", "acme")
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com"])
        self.green_light("acme", extra=("--only", "rec"))  # T2's "I also wrote to Maya" is now true
        self.ok("mail", "send", "acme")
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com", "tom.reed@example.com"])

    def test_recruiter_email_alone_cannot_claim_the_manager_email(self):
        """T2 says "I also wrote to Maya": sent before T1, that would be untrue."""
        self.refused("mail", "preview", "acme", "--no-open", "--only", "rec", why="Maya Stone")
        self.assertFalse((self.root / "outreach" / "preview.html").exists())

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

    def test_do_not_contact_address_with_an_apostrophe(self):
        with (self.root / "outreach" / "do-not-contact.md").open("a", encoding="utf-8") as f:
            f.write("'o'brien@example.com' asked 2026-01-01\n")
        self.edit("acme", "rec_email: tom.reed@example.com", "rec_email: o'brien@example.com")
        self.refused("mail", "preview", "acme", "--no-open", why="do-not-contact")

    def test_dropped_connection_after_delivery_never_resends(self):
        """The server may have taken the email before the line broke: the record keeps 'sending',
        so a retry cannot send it a second time."""
        self.green_light("acme")
        FakeSMTP.drop_at = 0
        self.refused("mail", "send", "acme", why="may have gone")
        FakeSMTP.drop_at = None
        self.assertEqual([(r["key"], r.get("state")) for r in self.sent_rows("acme")], [("hm", "sending")])
        self.ok("mail", "send", "acme")  # the retry sends only Tom's
        self.assertEqual([m["To"] for m in FakeSMTP.sent], ["maya.stone@example.com", "tom.reed@example.com"])
        self.refused("mail", "preview", "acme", "--no-open", "--only", "hm", why="never confirmed")

    def test_folder_outside_outreach_is_refused(self):
        """Outside outreach/, a folder escapes the log check, the ledger and the daily cap."""
        other = self.root / "elsewhere" / "acme"
        shutil.copytree(self.root / "outreach" / "acme", other)
        self.refused("mail", "preview", str(other), "--no-open", why="outreach/")
        self.assertEqual(FakeSMTP.sent, [])

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
        self.green_light("acme", extra=("--only", "hm"))
        self.ok("mail", "send", "acme")
        self.edit("acme", "rec_email: tom.reed@example.com", "rec_email: maya.stone@example.com")
        self.edit("acme", "hm_email: maya.stone@example.com", "hm_email: none")
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
        err = self.refused("mail", "preview", "acme", "--no-open", why="damaged")
        self.assertIn("Tell the owner", err)  # the assistant never opens a state file
        self.assertNotIn("with the owner", err)

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
        self.refused("mail", "preview", "acme", "--no-open", why="nudge waits 7 days")
        self.mail.now = self.real_now
        self.shift_clock(days=8)
        self.green_light("acme")
        self.ok("mail", "send", "acme")
        nudge = FakeSMTP.sent[-1]
        self.assertEqual(nudge["In-Reply-To"], first_id)
        self.assertTrue(nudge["Subject"].startswith("Re: "))
        self.assertEqual(list(nudge.iter_attachments()), [])
        self.assertEqual(len(FakeSMTP.sent), 3)


    def test_one_nudge_per_person_across_applications(self):
        """flow/messages.md: "One nudge per person, ever", not once per application."""
        nudge = ("\n## N1 nudge manager\n\nHi Maya,\n\nI wrote last week about the Senior Product "
                 "Marketing Manager role. I am still very interested and would be glad to do a "
                 "short call whenever suits you.\n\nBest regards,\nDana Levi\n050-000-0000\n")
        self.green_light("acme", extra=("--only", "hm"))
        self.ok("mail", "send", "acme")
        with (self.root / "outreach" / "acme" / "messages.md").open("a", encoding="utf-8") as f:
            f.write(nudge)
        self.shift_clock(days=8)
        self.green_light("acme", extra=("--only", "hm-nudge"))
        self.ok("mail", "send", "acme")
        self.app("acme-two", role="Product Marketing Lead",
                 edit=lambda t: t.replace("tom.reed@", "t.reed@") + nudge.replace("Senior Product Marketing Manager",
                                                                                  "Product Marketing Lead"))
        self.green_light("acme-two", extra=("--only", "hm", "--repeat-ok"))
        self.ok("mail", "send", "acme-two")
        self.mail.now = self.real_now
        self.shift_clock(days=16)
        self.refused("mail", "preview", "acme-two", "--no-open", "--only", "hm-nudge", why="one nudge per person")


class SentOutside(Kit):
    """A first email the owner sent by hand (hm_sent): the CV follow-up and nudges reply to it."""
    MID = "<CAabc123+x=y@mail.gmail.com>"
    C1 = ("\n## C1 CV follow-up manager\n\nHi Maya,\n\nFollowing up on my email about the Senior Product "
          "Marketing Manager role: CV attached as a PDF, so you have it directly.\n\nBest regards,\n"
          "Dana Levi\n050-000-0000\n")
    N1 = ("\n## N1 nudge manager\n\nHi Maya,\n\nI wrote last week about the Senior Product "
          "Marketing Manager role. I am still very interested and would be glad to do a "
          "short call whenever suits you.\n\nBest regards,\nDana Levi\n050-000-0000\n")

    def outside(self, sent=None, *sections):
        sent = f"{date.today().isoformat()} {self.MID}" if sent is None else sent
        self.edit("acme", "hm_email_confidence: High", f"hm_email_confidence: High\nhm_sent: {sent}")
        with (self.root / "outreach" / "acme" / "messages.md").open("a", encoding="utf-8") as f:
            f.write("".join(sections))

    def test_cv_follow_up_replies_with_the_cv(self):
        self.outside(None, self.C1)
        out = self.ok("mail", "status", "acme")
        self.assertIn("sent outside this script", out)
        self.green_light("acme", extra=("--only", "hm-cv"))
        self.ok("mail", "send", "acme")
        msg = FakeSMTP.sent[-1]
        self.assertEqual(msg["To"], "maya.stone@example.com")
        self.assertEqual(msg["In-Reply-To"], self.MID)
        self.assertTrue(msg["Subject"].startswith("Re: "))
        self.assertEqual([a.get_filename() for a in msg.iter_attachments()], ["cv.pdf"])
        self.refused("mail", "preview", "acme", "--no-open", "--only", "hm-cv", why="already sent")
        self.refused("mail", "preview", "acme", "--no-open", "--only", "hm", why="sent outside this script")

    def test_cv_follow_up_needs_hm_sent(self):
        with (self.root / "outreach" / "acme" / "messages.md").open("a", encoding="utf-8") as f:
            f.write(self.C1)
        self.refused("mail", "preview", "acme", "--no-open", why="set hm_sent")

    def test_cv_follow_up_needs_a_message_id(self):
        self.outside(date.today().isoformat(), self.C1)
        self.refused("mail", "preview", "acme", "--no-open", "--only", "hm-cv", why="no <Message-ID>")

    def test_bad_hm_sent_fails_validation(self):
        self.outside("last tuesday")
        self.refused("mail", "preview", "acme", "--no-open", why="hm_sent")

    def test_nudge_replies_to_the_hand_sent_email_and_can_carry_the_cv(self):
        self.profile["nudge_attaches_cv"] = True
        self.save_profile()
        self.outside(None, self.N1)
        self.refused("mail", "preview", "acme", "--no-open", "--only", "hm-nudge", why="nudge waits")
        self.shift_clock(days=8)
        self.green_light("acme", extra=("--only", "hm-nudge"))
        self.ok("mail", "send", "acme")
        msg = FakeSMTP.sent[-1]
        self.assertEqual(msg["In-Reply-To"], self.MID)
        self.assertEqual([a.get_filename() for a in msg.iter_attachments()], ["cv.pdf"])

    def test_hand_sent_first_email_is_history_not_checked(self):
        """T1 went out by hand with other wording: its text is a record, not checked again."""
        self.edit("acme", "CV attached", "My CV is with the application")
        self.refused("mail", "preview", "acme", "--no-open", why="must say the CV is attached")
        self.outside(None, self.C1)
        self.refused("mail", "preview", "acme", "--no-open", why="[T2] must say the CV is attached")
        self.edit("acme", "rec_email_confidence: Medium", f"rec_email_confidence: Medium\nrec_sent: {date.today()}")
        self.ok("mail", "preview", "acme", "--no-open", "--only", "hm-cv")

    def test_nudge_attaches_cv_must_be_a_bool(self):
        self.profile["nudge_attaches_cv"] = "yes"
        self.save_profile()
        self.refused("mail", "status", "acme", why="nudge_attaches_cv")


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



class Due(Kit):
    """tracker.py due: dated follow-ups become waiting / urgent / overdue; an application whose one
    nudge is spent and still has no reply goes cold. Never a second nudge."""
    TODAY = date(2026, 12, 1)

    @staticmethod
    def log(company, role="PMM", emails="2026-11-01", status="sent"):
        return (f"| 2026-11-01 | {company} | {role} | https://x/{company}/{role} | greenhouse | cv.pdf | | {emails} | "
                f"{status} | outreach/{company.lower()}-{role.lower()}/ |\n")

    def tables(self, log, replies, follow):
        out = self.root / "outreach"
        (out / "log.md").write_text("| Date | Company | Role | JD URL | Apply channel | CV | Contacts | Emails | Status | "
                                    "Folder |\n|---|---|---|---|---|---|---|---|---|---|\n" + log, encoding="utf-8")
        (out / "replies.md").write_text("| Company | Role | Got back? | Reply date | Reply from | Outcome | Notes |\n"
                                        "|---|---|---|---|---|---|---|\n" + replies, encoding="utf-8")
        (out / "followups.md").write_text("# Follow-ups\n\n| Added | Company | Role | Trigger | Action | Text source | Done |\n"
                                          "|---|---|---|---|---|---|---|\n" + follow, encoding="utf-8")

    def due(self):
        tracker = importlib.import_module("tracker")
        return {(r["Company"], r["Action"]): r for r in tracker.due(self.TODAY)}

    def test_dated_rows_by_how_late_they_are(self):
        self.tables(self.log("Acme", emails="held") + self.log("Beta", emails="held") + self.log("Gamma", emails="held")
                    + self.log("Delta", emails="held"), "",
                    "| 2026-11-20 | Acme | PMM | 2026-12-05 | N1 nudge manager | messages.md | |\n"
                    "| 2026-11-20 | Beta | PMM | 2026-11-30 | N1 nudge manager | messages.md | |\n"
                    "| 2026-11-20 | Gamma | PMM | 2026-11-25 | N2 nudge recruiter | messages.md | |\n"
                    "| 2026-11-20 | Delta | PMM | 2026-11-20 | N1 nudge manager | messages.md | 2026-11-21 |\n")
        d = self.due()
        self.assertEqual(d[("Acme", "N1 nudge manager")]["State"], "waiting")
        self.assertEqual(d[("Beta", "N1 nudge manager")]["State"], "urgent")
        self.assertEqual(d[("Gamma", "N2 nudge recruiter")]["State"], "overdue")
        self.assertNotIn(("Delta", "N1 nudge manager"), d, "a done row is finished")

    def test_event_rows_wait_on_their_trigger(self):
        self.tables(self.log("Acme", emails="held"), "",
                    "| 2026-11-20 | Acme | PMM | Maya accepted the LinkedIn invite | T4 message | messages.md | |\n")
        r = self.due()[("Acme", "T4 message")]
        self.assertEqual(r["State"], "waiting")
        self.assertIn("accepted", r["Due"])

    def test_a_reply_makes_the_nudge_moot(self):
        self.tables(self.log("Acme"), "| Acme | PMM | Yes | 2026-11-12 | Maya | Interview | |\n",
                    "| 2026-11-10 | Acme | PMM | 2026-11-17 | N1 nudge manager | messages.md | |\n")
        r = self.due()[("Acme", "N1 nudge manager")]
        self.assertEqual(r["State"], "answered")
        self.assertIn("mark it done", r["Next"])

    def test_a_row_that_only_mentions_nudge_is_not_a_nudge(self):
        """"no nudge if silent" on a feedback-request row: the rejection already in replies.md must
        not mark it answered. A nudge row's Action starts with the nudge (N1 / N2 / Nudge)."""
        self.tables(self.log("Acme"), "| Acme | PMM | Yes | 2026-11-12 | ATS | Rejected | |\n",
                    "| 2026-11-12 | Acme | PMM | Maya replies to the feedback request | Log it; no nudge if silent | | |\n"
                    "| 2026-11-10 | Acme | PMM | 2026-11-17 | Nudge Maya: reply on thread 1a2b | | |\n")
        d = self.due()
        self.assertEqual(d[("Acme", "Log it; no nudge if silent")]["State"], "waiting")
        self.assertEqual(d[("Acme", "Nudge Maya: reply on thread 1a2b")]["State"], "answered")

    def test_yes_in_any_letter_case_is_a_reply(self):
        self.tables(self.log("Acme"), "| Acme | PMM | yes | 2026-11-12 | Maya | Pending | |\n",
                    "| 2026-11-10 | Acme | PMM | 2026-11-17 | N1 nudge manager | messages.md | |\n")
        self.assertEqual(self.due()[("Acme", "N1 nudge manager")]["State"], "answered")

    def test_a_reply_for_another_role_does_not_end_this_application(self):
        self.tables(self.log("Acme") + self.log("Acme", role="Analyst"),
                    "| Acme | PMM | No | | | Pending | |\n| Acme | Analyst | Yes | 2026-11-03 | Tom | Rejected | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | |\n")
        d = self.due()
        self.assertEqual(d[("Acme", "N1 nudge manager")]["State"], "overdue", "the PMM nudge is still owed")
        self.assertNotIn(("Acme", "Analyst"), d)

    def test_another_roles_open_nudge_does_not_hold_this_one_back(self):
        self.tables(self.log("Acme") + self.log("Acme", role="Analyst", emails="2026-11-28"),
                    "| Acme | PMM | No | | | Pending | |\n| Acme | Analyst | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge PMM | messages.md | 2026-11-08 |\n"
                    "| 2026-11-28 | Acme | Analyst | 2026-12-05 | N1 nudge Analyst | messages.md | |\n")
        self.assertEqual(self.due()[("Acme", "PMM")]["State"], "cold")

    def test_spent_nudge_and_no_reply_goes_cold(self):
        self.tables(self.log("Acme"), "| Acme | PMM | Auto-ack only | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | 2026-11-09 |\n")
        r = self.due()[("Acme", "PMM")]
        self.assertEqual(r["State"], "cold")
        self.assertIn("no second nudge", r["Next"])
        self.assertIn("closed", r["Next"])

    def test_a_closed_application_is_finished(self):
        self.tables(self.log("Acme", status="closed"), "| Acme | PMM | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | 2026-11-09 |\n"
                    "| 2026-11-01 | Acme | PMM | Maya accepted the LinkedIn invite | T4 message | messages.md | |\n")
        self.assertEqual(self.due(), {})

    def test_recently_nudged_is_not_cold_yet(self):
        self.tables(self.log("Acme"), "| Acme | PMM | No | | | Pending | |\n",
                    "| 2026-11-01 | Acme | PMM | 2026-11-08 | N1 nudge manager | messages.md | 2026-11-25 |\n")
        self.assertNotIn(("Acme", "PMM"), self.due())

    def test_two_send_dates_count_from_the_first(self):
        self.tables(self.log("Acme", emails="2026-11-01; 2026-11-02"), "| Acme | PMM | No | | | Pending | |\n", "")
        self.assertEqual(self.due()[("Acme", "PMM")]["State"], "cold")

    def test_clock_times_are_not_dates(self):
        self.tables(self.log("Acme", emails="2026-11-01 sent 14:08-14:10Z"), "| Acme | PMM | No | | | Pending | |\n", "")
        self.assertEqual(self.due()[("Acme", "PMM")]["State"], "cold")

    def test_command_prints_a_table(self):
        self.tables(self.log("Beta", emails="held"), "",
                    "| 2026-11-20 | Beta | PMM | 2026-11-30 | N1 nudge manager | messages.md | |\n")
        out = self.ok("tracker", "due")
        self.assertIn("| State |", out)
        self.assertIn("Beta", out)

    def test_bad_input_is_named_not_skipped(self):
        cases = (("2026-13-40", "", "2026-13-40"), ("2026/11/08", "", "2026/11/08"), ("2026-11-8", "", "2026-11-8"),
                 ("2026-11-30", "No", "Done"), ("2026-11-30", "-", "Done"))
        for trigger, done, why in cases:
            with self.subTest(trigger=trigger, done=done):
                self.tables(self.log("Beta", emails="held"), "",
                            f"| 2026-11-20 | Beta | PMM | {trigger} | N1 nudge manager | messages.md | {done} |\n")
                self.refused("tracker", "due", why=why)

    def test_rows_must_name_a_logged_application(self):
        self.tables(self.log("Acme"), "", "| 2026-11-20 | Acme Inc | PMM | 2026-11-30 | N1 nudge | messages.md | |\n")
        self.refused("tracker", "due", why="Acme Inc")
        self.tables(self.log("Acme"), "| Acme Inc | PMM | Yes | | | Interview | |\n", "")
        self.refused("tracker", "due", why="Acme Inc")
        self.tables(self.log("Acme"), "", "| | | | | | | |\n")
        self.refused("tracker", "due", why="empty")

    def test_old_followups_table_is_explained(self):
        (self.root / "outreach" / "followups.md").write_text(
            "| Added | Company | Trigger | Action | Text source | Done |\n|---|---|---|---|---|---|\n", encoding="utf-8")
        self.refused("tracker", "due", why="Role")


NOTES = ('Notes:\n"When exporting your connection data, you may notice that some of the email addresses '
         'are missing."\n\n')
CSV_HEAD = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"


class Network(Kit):
    """LinkedIn's Connections.csv matched against a company, in tiers, for the R1 referral ask."""
    def connections(self, *rows, notes=True, head=CSV_HEAD):
        text = (NOTES if notes else "") + head + "".join(r + "\n" for r in rows)
        (self.root / "profile" / "connections.csv").write_text(text, encoding="utf-8-sig")

    def match(self, *companies):
        return self.run_cmd("network", "match", *companies)

    def test_exact_strong_and_weak_tiers(self):
        self.connections(
            "Noa,Cohen,https://www.linkedin.com/in/noa-example,,Acme Robotics Ltd.,VP Marketing,03 Mar 2024",
            "Avi,Mor,https://www.linkedin.com/in/avi-example,,Acme Robotics Israel,Engineer,11/02/2023",
            "Lior,Bar,https://www.linkedin.com/in/lior-example,,Acme Holdings Group,Analyst,01 Jan 2022",
            "Tal,Ron,https://www.linkedin.com/in/tal-example,,Contoso Analytics,Designer,01 Jan 2022")
        code, out, _ = self.match("Acme Robotics")
        self.assertEqual(code, 0, out)
        rows = {l.split("|")[2].strip(): l.split("|")[1].strip() for l in out.splitlines() if l.startswith("| ") and "Tier" not in l}
        self.assertEqual(rows, {"Noa Cohen": "exact", "Avi Mor": "strong", "Lior Bar": "weak"})
        self.assertIn("VP Marketing", out)
        self.assertIn("https://www.linkedin.com/in/noa-example", out)
        self.assertLess(out.index("Noa Cohen"), out.index("Avi Mor"))
        self.assertLess(out.index("Avi Mor"), out.index("Lior Bar"))

    def test_a_shorter_or_generic_name_is_not_strong(self):
        """A person at plain "Acme" may work at another Acme: weak, so the owner is asked. A name
        made only of generic words ("Bank") matches nothing."""
        self.connections("Noa,Cohen,https://www.linkedin.com/in/noa-example,,Acme,VP,03 Mar 2024",
                         "Avi,Mor,https://www.linkedin.com/in/avi-example,,Bank,Teller,03 Mar 2024")
        code, out, _ = self.match("Acme Robotics", "Bank Leumi")
        self.assertEqual(code, 0, out)
        self.assertIn("| weak | Noa Cohen |", out)
        self.assertNotIn("Avi Mor", out)

    def test_a_web_suffix_is_a_strong_match(self):
        self.connections("Dan,Gal,https://www.linkedin.com/in/dan-example,,monday.com,PM,01 Jan 2024")
        code, out, _ = self.match("Monday")
        self.assertEqual(code, 0, out)
        self.assertIn("| strong | Dan Gal |", out)

    def test_short_and_non_latin_names_match(self):
        """Three-letter names (IBM, SAP) and Hebrew names used to match nothing at all."""
        self.connections("Noa,Cohen,https://www.linkedin.com/in/noa-example,,IBM Israel,VP,03 Mar 2024",
                         "Avi,Mor,https://www.linkedin.com/in/avi-example,,SAP Labs,Engineer,03 Mar 2024",
                         "Tal,Ron,https://www.linkedin.com/in/tal-example,,אלביט מערכות,Designer,01 Jan 2022")
        code, out, _ = self.match("IBM", "SAP", "אלביט מערכות")
        self.assertEqual(code, 0, out)
        self.assertIn("| strong | Noa Cohen |", out)
        self.assertIn("| strong | Avi Mor |", out)
        self.assertIn("| exact | Tal Ron |", out)

    def test_generic_words_alone_do_not_match(self):
        self.connections("Tal,Ron,https://www.linkedin.com/in/tal-example,,Contoso Analytics,Designer,01 Jan 2022")
        code, out, _ = self.match("Northwind Analytics")
        self.assertEqual(code, 1, out)
        self.assertIn("no connection", out)

    def test_several_companies_and_no_notes_preamble(self):
        self.connections("Noa,Cohen,https://www.linkedin.com/in/noa-example,,Acme Robotics,VP,03 Mar 2024",
                         "Tal,Ron,https://www.linkedin.com/in/tal-example,,Contoso Analytics,Designer,01 Jan 2022",
                         notes=False)
        code, out, _ = self.match("Acme Robotics", "Contoso Analytics", "Globex")
        self.assertEqual(code, 0, out)
        for name in ("Noa Cohen", "Tal Ron", "Globex"):
            self.assertIn(name, out)

    def test_emails_are_not_printed(self):
        self.connections("Noa,Cohen,https://www.linkedin.com/in/noa-example,noa@example.com,Acme Robotics,VP,03 Mar 2024")
        self.assertNotIn("noa@example.com", self.match("Acme Robotics")[1])

    def test_bad_input_is_refused(self):
        self.refused("network", "match", "Acme", why="ONBOARDING.md")
        self.connections("Noa,Cohen,x,,Acme,VP,03 Mar 2024", head="First Name,Last Name,Employer\n")
        self.refused("network", "match", "Acme", why="Company")
        self.connections("Noa,Cohen,https://www.linkedin.com/in/noa-example,,Acme,VP,03 Mar 2024")
        self.refused("network", "match", "  ", why="company")


LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # straight to 127.0.0.1


class CvServe(Kit):
    """cv.py serve hands one CV page to the browser's Save as PDF: that file only, on this
    computer only, for one load, so the browser never needs file:// access."""
    def page(self, name="cv-acme.html"):
        p = self.root / "outreach" / "acme" / name
        p.write_text("<!doctype html><title>CV</title><p>Dana Levi, Tel Aviv</p>", encoding="utf-8")
        return p

    def url(self, *args):
        out = self.ok("cv", "serve", *args)
        return re.search(r"http://127\.0\.0\.1:\d+/\S+", out).group()

    def gone(self, url, within=3.0):
        end = time.time() + within
        while time.time() < end:
            try:
                LOCAL.open(url, timeout=1)
            except urllib.error.URLError:
                return True
            time.sleep(0.1)
        return False

    def test_serves_that_page_once_then_stops(self):
        url = self.url(str(self.page()), "--seconds", "20")
        with self.assertRaises(urllib.error.HTTPError) as other:
            LOCAL.open(url.rsplit("/", 1)[0] + "/messages.md", timeout=2)
        self.assertEqual(other.exception.code, 404)
        other.exception.close()
        reply = LOCAL.open(url, timeout=2)
        self.assertIn("text/html", reply.headers["Content-Type"])
        self.assertIn("Dana Levi", reply.read().decode("utf-8"))
        self.assertTrue(self.gone(url), "the server must stop after the page loads once")

    def test_stops_when_its_time_runs_out(self):
        url = self.url(str(self.page()), "--seconds", "1")
        time.sleep(1.5)
        self.assertTrue(self.gone(url))

    def test_bad_input_is_refused(self):
        self.refused("cv", "serve", str(self.root / "outreach" / "acme" / "nope.html"), why="nope.html")
        self.refused("cv", "serve", str(self.root / "outreach" / "acme" / "messages.md"), why=".html")
        self.refused("cv", "serve", str(self.page()), "--seconds", "0", why="seconds")
        self.refused("cv", "serve", str(self.page()), "--seconds", "nan", why="seconds")
        self.refused("cv", "serve", str(self.page()), "--seconds", "inf", why="seconds")


if __name__ == "__main__":
    unittest.main()
