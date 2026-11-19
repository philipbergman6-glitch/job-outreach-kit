"""Tests for accounts.py (permissions + pace), triage.py (shortlist checks), search.py and the
email-provider adapters. No network. Each test works in a throwaway copy of scripts/."""
import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODS = ("_common", "validate", "accounts", "triage", "search", "emails", "tracker")


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "kit"
        shutil.copytree(REPO / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "profile").mkdir()
        (self.root / "outreach" / "jobs").mkdir(parents=True)
        shutil.copy(REPO / "examples" / "cv.pdf", self.root / "profile" / "cv.pdf")
        shutil.copy(REPO / "examples" / "cv.txt", self.root / "profile" / "cv.txt")
        shutil.copy(REPO / "examples" / "brief.md", self.root / "profile" / "brief.md")
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


class Accounts(Sandbox):
    def test_no_permission_means_denied(self):
        code, out, _ = self.run_cmd("accounts", "check", "linkedin", "read_people")
        self.assertEqual(code, 3)
        self.assertIn("DENIED", out)

    def test_allowed_use_is_logged_and_capped(self):
        self.profile["accounts"] = {"linkedin": {"read_people": True, "invites": False}}
        self.profile["account_caps"] = {"linkedin": {"read_people": 2}}
        self.save()
        for i in range(2):
            code, out, err = self.run_cmd("accounts", "record", "LinkedIn", "read_people", f"opened profile {i}")
            self.assertEqual(code, 0, err)
            self.assertIn(f"{i + 1} of 2", out)
        code, out, _ = self.run_cmd("accounts", "record", "linkedin", "read_people", "one more")
        self.assertEqual(code, 3)
        self.assertIn("limit", out)
        log = (self.root / "outreach" / "accounts-log.md").read_text(encoding="utf-8")
        self.assertEqual(log.count("read_people"), 2)

    def test_said_no_is_denied(self):
        self.profile["accounts"] = {"jobify360": {"search_jobs": True, "apply": False}}
        self.save()
        self.assertEqual(self.run_cmd("accounts", "check", "jobify360", "apply")[0], 3)
        self.assertEqual(self.run_cmd("accounts", "check", "jobify360", "search_jobs")[0], 0)

    def test_the_mailbox_is_a_use_of_its_own(self):
        """Reading replies and saving drafts in the owner's webmail needs its own yes."""
        self.assertIn("ONBOARDING.md step 7", self.run_cmd("accounts", "check", "gmail", "mailbox")[1])
        self.profile["accounts"] = {"gmail": {"mailbox": True}}
        self.save()
        code, out, _ = self.run_cmd("accounts", "record", "gmail", "mailbox", "searched replies from acme.com")
        self.assertEqual(code, 0, out)

    def test_site_names_match_in_any_case(self):
        self.profile["accounts"] = {"LinkedIn": {"read_people": True}}
        self.save()
        self.assertEqual(self.run_cmd("accounts", "check", "linkedin", "read_people")[0], 0)

    def test_bad_permissions_hard_fail(self):
        self.profile["accounts"] = {"linkedin": {"scrape_everything": True}}
        self.save()
        code, _, err = self.run_cmd("accounts", "status")
        self.assertEqual(code, 2)
        self.assertIn("not a use", err)
        self.profile["accounts"] = {"linkedin": {"read_people": "yes"}}
        self.save()
        self.assertIn("true or false", self.run_cmd("accounts", "status")[2])


TRIAGE = """# Triage 2026-11-17: greenhouse, 10 postings read, 2 kept

## A: direct fit
| # | Company | Role | Location | Posted | Salary | Visa | Score | Apply path | Link | JD file | Why it fits | Quote |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Acme | AI Engineer | Tel Aviv | {posted} | - | - | {score} | greenhouse | https://acme.io/jobs/1 | acme-1.md | Agents hook | "{quote}" |

## Dropped
| Company | Role | Link | JD file | Reason | Quote |
|---|---|---|---|---|---|
| Beta | Engineer | https://beta.io/j/2 | beta-2.md | deal-breaker: on-site | "{dquote}" |
| Gamma | Analyst | https://g.io/3 | - | already applied | - |
"""


class Triage(Sandbox):
    def write(self, posted=None, score="5", quote="build LLM agents in Python", dquote="five days a week in the office"):
        jobs = self.root / "outreach" / "jobs"
        (jobs / "acme-1.md").write_text("---\nurl: x\n---\nYou will build LLM agents\nin Python’s ecosystem.", encoding="utf-8")
        (jobs / "beta-2.md").write_text("Work five days a week in the office.", encoding="utf-8")
        p = self.root / "outreach" / "triage-2026-11-17.md"
        p.write_text(TRIAGE.format(posted=posted or (date.today() - timedelta(days=3)).isoformat(),
                                   score=score, quote=quote, dquote=dquote), encoding="utf-8")
        return str(p)

    def test_good_shortlist_passes(self):
        code, out, err = self.run_cmd("triage", "check", self.write())
        self.assertEqual(code, 0, out + err)
        self.assertIn("PASS (1 kept, 2 dropped)", out)

    def test_paraphrased_quote_fails(self):
        code, out, _ = self.run_cmd("triage", "check", self.write(quote="builds LLM agents in Python"))
        self.assertEqual(code, 1)
        self.assertIn("not found word for word", out)

    def test_curly_apostrophe_and_line_break_are_not_paraphrase(self):
        code, out, _ = self.run_cmd("triage", "check", self.write(quote="LLM agents in Python's ecosystem"))
        self.assertEqual(code, 0, out)

    def test_score_must_match_tier_and_age_limit(self):
        code, out, _ = self.run_cmd("triage", "check", self.write(score="3", posted="2026-01-01"))
        self.assertEqual(code, 1)
        self.assertIn("does not belong in tier A", out)
        self.assertIn("stale", out)

    def test_already_applied_or_passed_is_caught(self):
        (self.root / "outreach" / "log.md").write_text("| x | Acme | AI | https://acme.io/jobs/1/ |\n", encoding="utf-8")
        code, out, _ = self.run_cmd("triage", "check", self.write())
        self.assertIn("already applied", out)
        self.assertEqual(code, 1)

    def test_pass_records_and_is_then_skipped(self):
        p = self.write()
        self.assertEqual(self.run_cmd("triage", "pass", "https://acme.io/jobs/1?src=li", "too junior")[0], 0)
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertIn("passed before", out)

    def with_jd(self, extra, why="Agents hook"):
        p = self.write()
        jd = self.root / "outreach" / "jobs" / "acme-1.md"
        jd.write_text(jd.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
        if why != "Agents hook":
            Path(p).write_text(Path(p).read_text(encoding="utf-8").replace("Agents hook", why), encoding="utf-8")
        return self.run_cmd("triage", "check", p)

    def test_a_posting_that_asks_the_candidate_to_pay_must_be_dropped(self):
        for line in ("Successful applicants must pay a refundable deposit of $200 before training.",
                     "You will be charged a one-time registration fee to join the program.",
                     "New hires need to purchase their own starter kit."):
            code, out, _ = self.with_jd(line)
            self.assertEqual(code, 1, line)
            self.assertIn("asks the candidate to pay", out)
            self.assertIn(line.rstrip("."), out)

    def test_employer_paid_costs_and_payments_jobs_pass(self):
        for line in ("We cover your training fees and certification costs.",
                     "Equipment is provided at no cost to you.",
                     "You will build the engine that calculates processing fees our merchants pay."):
            code, out, _ = self.with_jd(line)
            self.assertEqual(code, 0, line + out)

    def test_a_refund_or_a_perk_elsewhere_does_not_hide_the_fee(self):
        for line in ("You must first pay a $150 security deposit, which will be reimbursed with your first paycheck.",
                     "Applicants must pay a $200 training fee; laptop provided."):
            code, out, _ = self.with_jd(line)
            self.assertEqual(code, 1, line)

    def test_no_note_in_the_row_clears_the_flag(self):
        code, out, _ = self.with_jd("You will be charged a one-time registration fee to join the program.",
                                    why="Agents hook; fee checked")
        self.assertEqual(code, 1, out)

    def test_ordinary_phrases_are_not_a_fee(self):
        for line in ("You must pay close attention to detail.", "You will be charged with leading our budget process.",
                     "Candidates must buy into our mission."):
            code, out, _ = self.with_jd(line)
            self.assertEqual(code, 0, line + out)

    def test_a_one_word_quote_proves_nothing(self):
        code, out, _ = self.run_cmd("triage", "check", self.write(quote="e"))
        self.assertEqual(code, 1)
        self.assertIn("too short", out)

    def test_jd_file_is_a_name_in_the_jobs_folder(self):
        p = self.write()
        Path(p).write_text(Path(p).read_text(encoding="utf-8").replace("| acme-1.md |", "| ../log.md |"), encoding="utf-8")
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertEqual(code, 1)
        self.assertIn("a file name", out)

    def test_jobs_told_apart_by_their_query_id(self):
        (self.root / "outreach" / "log.md").write_text("| x | Acme | AI | https://acme.io/careers?gh_jid=111 |\n", encoding="utf-8")
        p = self.write()
        Path(p).write_text(Path(p).read_text(encoding="utf-8").replace("https://acme.io/jobs/1", "https://acme.io/careers?gh_jid=222&utm_source=li"), encoding="utf-8")
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertEqual(code, 0, out)
        Path(p).write_text(Path(p).read_text(encoding="utf-8").replace("gh_jid=222", "gh_jid=111"), encoding="utf-8")
        self.assertIn("already applied", self.run_cmd("triage", "check", p)[1])

    def test_a_dropped_scam_row_passes(self):
        p = self.write(dquote="must pay a refundable deposit")
        (self.root / "outreach" / "jobs" / "beta-2.md").write_text(
            "Successful applicants must pay a refundable deposit.", encoding="utf-8")
        t = Path(p).read_text(encoding="utf-8").replace("deal-breaker: on-site", "scam: asks the candidate to pay")
        Path(p).write_text(t, encoding="utf-8")
        code, out, _ = self.run_cmd("triage", "check", p)
        self.assertEqual(code, 0, out)

    def test_wrong_columns_hard_fail(self):
        p = self.root / "outreach" / "t.md"
        p.write_text("## A: x\n| # | Company |\n|---|---|\n| 1 | Acme |\n", encoding="utf-8")
        code, _, err = self.run_cmd("triage", "check", str(p))
        self.assertEqual(code, 2)
        self.assertIn("columns", err)


class Search(Sandbox):
    def test_no_key_is_a_clear_hard_fail(self):
        code, _, err = self.run_cmd("search", "people", "head of data at Acme")
        self.assertEqual(code, 2)
        self.assertIn("optional", err)

    def test_exa_people_request_and_output(self):
        (self.root / ".env").write_text("EXA_API_KEY=k\n", encoding="utf-8")
        search = importlib.import_module("search")
        seen = {}

        def fake(url, **k):
            seen.update(k, url=url)
            return {"results": [{"title": "Dana Levi - Head of Data - Acme", "url": "https://linkedin.com/in/dl",
                                 "publishedDate": "2026-10-01T00:00:00Z", "highlights": ["Leads data at Acme"]}]}
        search.http = fake
        code, out, err = self.run_cmd("search", "people", "head of data at Acme")
        self.assertEqual(code, 0, err)
        self.assertEqual(seen["body"]["category"], "people")
        self.assertEqual(seen["headers"]["x-api-key"], "k")
        self.assertIn("[2026-10-01] Dana Levi - Head of Data - Acme | https://linkedin.com/in/dl", out)


    def test_unsupported_options_hard_fail_instead_of_being_ignored(self):
        (self.root / ".env").write_text("EXA_API_KEY=k\n", encoding="utf-8")
        code, _, err = self.run_cmd("search", "people", "head of data at Acme", "--fresh", "pm")
        self.assertEqual(code, 2)
        self.assertIn("--fresh works only with Brave", err)
        self.assertIn("--site does not apply", self.run_cmd("search", "company", "x", "--site", "a.com")[2])


class Providers(Sandbox):
    def test_adapters_read_each_reply_shape(self):
        emails = importlib.import_module("emails")
        replies = {
            "prospeo": {"person": {"email": {"email": "d@acme.com", "status": "VERIFIED"}}},
            "hunter": {"data": {"email": "d@acme.com", "verification": {"status": "accept_all"}}},
            "apollo": {"person": {"email": "d@acme.com", "email_status": "verified", "match_confidence": "high"}},
            "tomba": {"data": {"email": "d@acme.com", "verification": {"status": "valid"}, "accept_all": True}},
            "anymailfinder": {"email": "d@acme.com", "email_status": "valid"},
            "findymail": {"contact": {"email": "d@acme.com"}},
        }
        want = {"prospeo": "valid", "hunter": "found", "apollo": "valid", "tomba": "found",
                "anymailfinder": "valid", "findymail": "found"}
        for name, (keys, find_fn, _) in emails.PROVIDERS.items():
            emails.http = lambda url, _r=replies[name], **k: _r
            got = find_fn({k: "x" for k in keys}, "Dana", "Levi", "acme.com")
            self.assertEqual(got, ("d@acme.com", want[name]), name)

    def test_not_found_shapes(self):
        emails = importlib.import_module("emails")
        from _common import NetError

        def prospeo_miss(url, **k):
            raise NetError('POST https://api.prospeo.io/enrich-person HTTP 400: {"error":true,"error_code":"NO_MATCH"}')
        emails.http = prospeo_miss
        self.assertEqual(emails._prospeo_find({"PROSPEO_API_KEY": "x"}, "D", "L", "acme.com"), (None, ""))
        emails.http = lambda url, **k: {"person": {"match_confidence": "none"}}
        self.assertEqual(emails._apollo_find({"APOLLO_API_KEY": "x"}, "D", "L", "acme.com"), (None, ""))
        emails.http = lambda url, **k: {"email": None, "email_status": "not_found"}
        self.assertEqual(emails._anymail_find({"ANYMAILFINDER_API_KEY": "x"}, "D", "L", "acme.com"), (None, ""))


class Referral(Sandbox):
    def test_r1_section_is_parsed_apart_and_not_checked(self):
        folder = self.root / "outreach" / "acme"
        folder.mkdir()
        shutil.copy(self.root / "profile" / "cv.pdf", folder / "cv.pdf")
        text = (REPO / "examples" / "acme-robotics" / "messages.md").read_text(encoding="utf-8")
        (folder / "messages.md").write_text(text + "\n## R1 referral ask\n\nHey Moshe! short.\n", encoding="utf-8")
        validate = importlib.import_module("validate")
        meta, secs = validate.parse(folder / "messages.md")
        self.assertIn("R1", secs)
        self.assertNotIn("Moshe", secs["T4"][1])
        v, _ = validate.check(folder / "messages.md", validate.load_profile())
        self.assertFalse([x for x in v if "R1" in x], v)


class Profile(Sandbox):
    def test_word_cv_is_refused_with_export_steps(self):
        shutil.copy(self.root / "profile" / "cv.pdf", self.root / "profile" / "cv.docx")
        self.profile["cvs"] = [{"file": "profile/cv.docx", "use_when": "default"}]
        self.save()
        code, _, err = self.run_cmd("validate", "--check-profile")
        self.assertEqual(code, 2)
        self.assertIn("Save As > PDF", err)

    def test_second_language_picks_its_own_rules(self):
        self.profile["languages"] = {"Hebrew": {"greeting": "שלום {first},", "closing": "בברכה,",
                                                "subject": "מועמדות לתפקיד {role}, {name}",
                                                "attachment_phrases": ["קורות החיים מצורפים"],
                                                "today_words": ["היום"]}}
        self.save()
        validate = importlib.import_module("validate")
        prof = validate.load_profile()
        he = validate.messages_for(prof, {"language": "Hebrew"})
        self.assertEqual(he["greeting"], "שלום {first},")
        self.assertIn("CV attached", he["attachment_phrases"])  # defaults still apply
        self.assertIn("קורות החיים מצורפים", he["attachment_phrases"])
        self.assertEqual(validate.messages_for(prof, {})["greeting"], "Hi {first},")
        with self.assertRaises(SystemExit):
            validate.messages_for(prof, {"language": "French"})

    def test_language_hook_names_and_signature(self):
        hook = self.profile["hooks"][0]
        self.profile["languages"] = {"Hebrew": {"greeting": "שלום {first},", "hook_names": {hook: "ספר ההשקה"},
                                                "signature_name": "דנה לוי"}}
        self.save()
        validate = importlib.import_module("validate")
        he = validate.messages_for(validate.load_profile(), {"language": "Hebrew"})
        self.assertEqual(he["_hook_names"][hook], "ספר ההשקה")
        self.assertEqual(he["_signature_name"], "דנה לוי")
        self.profile["languages"]["Hebrew"]["hook_names"] = {"No Such Hook": "x"}
        self.save()
        self.assertIn("not in 'hooks'", self.run_cmd("validate", "--check-profile")[2])

    def test_bad_language_settings_hard_fail(self):
        self.profile["languages"] = {"Hebrew": {"salutation": "x"}}
        self.save()
        code, _, err = self.run_cmd("validate", "--check-profile")
        self.assertEqual(code, 2)
        self.assertIn("unknown languages.Hebrew keys", err)


if __name__ == "__main__":
    unittest.main()
