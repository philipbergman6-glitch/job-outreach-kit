"""Tests for scripts/emails.py. No network: every outside call is replaced by a fake."""
import smtplib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import emails  # noqa: E402

REAL_HTTP, REAL_SMTP = emails.http, emails.smtp_factory


class Restore(unittest.TestCase):
    """Put back whatever a test replaced, so test order never matters."""
    def tearDown(self):
        emails.http, emails.smtp_factory = REAL_HTTP, REAL_SMTP


class Names(unittest.TestCase):
    def test_normalise_strips_accents_case_and_apostrophes(self):
        self.assertEqual(emails.norm("José"), "jose")
        self.assertEqual(emails.norm("O'Brien"), "obrien")
        self.assertEqual(emails.norm("Müller"), "muller")

    def test_candidates_start_with_the_common_patterns(self):
        c = emails.candidates("Dana", "Levi", "acme.com")
        self.assertEqual(c[0], "dana.levi@acme.com")
        self.assertIn("dana@acme.com", c[:3])
        self.assertIn("dlevi@acme.com", c[:4])
        self.assertEqual(len(c), len(set(c)))

    def test_compound_last_name_gives_both_forms(self):
        c = emails.candidates("Ana", "Ben-David", "x.io")
        self.assertIn("ana.bendavid@x.io", c)
        self.assertIn("ana.ben-david@x.io", c)

    def test_bad_input_is_refused(self):
        with self.assertRaises(SystemExit):
            emails.candidates("", "Levi", "acme.com")
        with self.assertRaises(SystemExit):
            emails.candidates("Dana", "Levi", "not a domain")


class Infer(unittest.TestCase):
    def test_pattern_inferred_from_known_people(self):
        known = [("Yossi", "Cohen", "ycohen@acme.com"), ("Rina", "Mor", "rmor@acme.com")]
        pats = emails.infer(known, "acme.com")
        self.assertEqual(pats[0][0], "{f}{last}")
        self.assertEqual(pats[0][1], 2)
        c = emails.candidates("Dana", "Levi", "acme.com", known=known)
        self.assertEqual(c[0], "dlevi@acme.com")

    def test_other_domains_and_generic_boxes_are_ignored(self):
        known = [("Yossi", "Cohen", "yossi@gmail.com"), ("Jobs", "Team", "jobs@acme.com")]
        self.assertEqual(emails.infer(known, "acme.com"), [])

    def test_parse_known_accepts_name_angle_form(self):
        self.assertEqual(emails.parse_known("Yossi Cohen <ycohen@acme.com>"),
                         ("Yossi", "Cohen", "ycohen@acme.com"))
        with self.assertRaises(SystemExit):
            emails.parse_known("ycohen@acme.com")


class Scrape(unittest.TestCase):
    def test_finds_plain_mailto_obfuscated_and_cloudflare(self):
        cf = "".join(f"{b:02x}" for b in [0x42] + [c ^ 0x42 for c in b"hr@acme.com"])
        html = ('<a href="mailto:jobs%40acme.com">Jobs</a> Write to dana.levi@acme.com. '
                'Or yossi [at] acme [dot] com, rina(at)acme.com, '
                f'<span class="__cf_email__" data-cfemail="{cf}">[email protected]</span> '
                'and noise@other.com, &#100;&#64;acme.com, image@2x.png')
        found = emails.extract(html, "acme.com")
        for a in ("jobs@acme.com", "dana.levi@acme.com", "yossi@acme.com", "rina@acme.com",
                  "hr@acme.com", "d@acme.com"):
            self.assertIn(a, found)
        self.assertNotIn("noise@other.com", found)

    def test_subdomain_mail_counts(self):
        self.assertIn("a@mail.acme.com", emails.extract("a@mail.acme.com", "acme.com"))

    def test_generic_boxes_are_flagged(self):
        self.assertTrue(emails.is_generic("careers@acme.com"))
        self.assertFalse(emails.is_generic("dana@acme.com"))


class Dns(Restore):
    def test_mail_provider_from_mx(self):
        self.assertEqual(emails.provider_of(["aspmx.l.google.com"]), "Google Workspace")
        self.assertEqual(emails.provider_of(["acme-com.mail.protection.outlook.com"]), "Microsoft 365")
        self.assertEqual(emails.provider_of(["mx1-us1.ppe-hosted.com"]), "Proofpoint")
        self.assertEqual(emails.provider_of(["mx.example.net"]), "other")

    def test_doh_answer_parsed(self):
        def fake(url, **k):
            if "type=MX" in url:
                return {"Status": 0, "Answer": [{"data": "20 alt1.aspmx.l.google.com."},
                                                {"data": "10 aspmx.l.google.com."}]}
            return {"Status": 0, "Answer": [{"data": '"v=spf1 include:_spf.google.com include:mail.zendesk.com ~all"'}]}
        emails.http = fake
        mx, spf = emails.dns_mail("acme.com")
        self.assertEqual(mx, ["aspmx.l.google.com", "alt1.aspmx.l.google.com"])
        self.assertIn("_spf.google.com", spf)

    def test_domain_with_no_mx(self):
        emails.http = lambda url, **k: {"Status": 0}
        mx, spf = emails.dns_mail("acme.com")
        self.assertEqual(mx, [])

    def test_nonexistent_domain_and_dns_failure_hard_fail(self):
        emails.http = lambda url, **k: {"Status": 3}
        with self.assertRaises(SystemExit):
            emails.dns_mail("acme.com")
        emails.http = lambda url, **k: {"Status": 2}  # SERVFAIL on both resolvers
        with self.assertRaises(SystemExit):
            emails.dns_mail("acme.com")


class FakeServer:
    """Plays an SMTP server. accept: set of addresses that exist; catch_all: accept anything;
    reject: (code, text) for unknown mailboxes."""
    accept, catch_all, refuse_connect, null_sender_ok = set(), False, False, True
    reject = (550, b"5.1.1 user unknown")
    rcpts = []

    def __init__(self, host, port, timeout=None, local_hostname=None):
        if FakeServer.refuse_connect:
            raise OSError("timed out")

    def ehlo(self, *a):
        return 250, b"ok"

    def mail(self, sender):
        if sender == "" and not FakeServer.null_sender_ok:
            return 550, b"5.7.1 sender rejected"
        return 250, b"ok"

    def rcpt(self, addr):
        FakeServer.rcpts.append(addr)
        if FakeServer.catch_all or addr in FakeServer.accept:
            return 250, b"ok"
        return FakeServer.reject

    def quit(self):
        pass

    def close(self):
        pass


class Probe(Restore):
    def setUp(self):
        FakeServer.accept, FakeServer.catch_all, FakeServer.refuse_connect = {"dana@acme.com"}, False, False
        FakeServer.null_sender_ok, FakeServer.rcpts = True, []
        FakeServer.reject = (550, b"5.1.1 user unknown")
        emails.smtp_factory = FakeServer

    def test_existing_and_missing_on_a_strict_domain(self):
        r = emails.probe(["dana@acme.com", "dana.levi@acme.com"], ["mx.acme.com"])
        self.assertEqual(r["catch_all"], False)
        self.assertEqual(r["results"]["dana@acme.com"], "exists")
        self.assertEqual(r["results"]["dana.levi@acme.com"], "missing")

    def test_catch_all_proves_nothing(self):
        FakeServer.catch_all = True
        r = emails.probe(["dana@acme.com"], ["mx.acme.com"])
        self.assertTrue(r["catch_all"])
        self.assertEqual(r["results"]["dana@acme.com"], "unknown (accept-all domain)")

    def test_blocked_port_is_reported_not_raised(self):
        FakeServer.refuse_connect = True
        r = emails.probe(["dana@acme.com"], ["mx.acme.com"])
        self.assertIn("port 25", r["error"])

    def test_greylisted_test_address_means_unknown_not_strict(self):
        FakeServer.reject = (450, b"4.2.0 greylisted, try again later")
        r = emails.probe(["dana@acme.com"], ["mx.acme.com"])
        self.assertIsNone(r["catch_all"])
        self.assertNotEqual(r["results"]["dana@acme.com"], "exists")
        self.assertNotEqual(emails.grade("dana@acme.com", {"probe": r["results"]["dana@acme.com"],
                                                           "catch_all": r["catch_all"]}), "High")

    def test_policy_block_is_not_a_missing_mailbox(self):
        FakeServer.reject = (550, b"5.7.1 Client host rejected: blocked using Spamhaus")
        r = emails.probe(["dana.levi@acme.com"], ["mx.acme.com"])
        self.assertIsNone(r["catch_all"])
        self.assertNotEqual(r["results"]["dana.levi@acme.com"], "missing")

    def test_falls_back_when_null_sender_refused(self):
        FakeServer.null_sender_ok = False
        r = emails.probe(["dana@acme.com"], ["mx.acme.com"])
        self.assertEqual(r["results"]["dana@acme.com"], "exists")


class Verdict(unittest.TestCase):
    def test_published_address_is_high(self):
        v = emails.grade("dana@acme.com", {"site": True})
        self.assertEqual(v, "High")

    def test_probe_on_strict_domain_is_high(self):
        self.assertEqual(emails.grade("x@acme.com", {"probe": "exists", "catch_all": False}), "High")

    def test_provider_valid_is_high_but_catch_all_caps_it(self):
        self.assertEqual(emails.grade("x@acme.com", {"providers": {"hunter": "valid"}}), "High")
        self.assertEqual(emails.grade("x@acme.com", {"providers": {"hunter": "valid"}, "catch_all": True}), "Medium")

    def test_two_sources_agree_is_medium(self):
        self.assertEqual(emails.grade("x@acme.com", {"pattern_votes": 2}), "Medium")
        self.assertEqual(emails.grade("x@acme.com", {"providers": {"tomba": "found"}, "pattern_votes": 1}), "Medium")

    def test_guess_alone_is_low_and_probe_missing_is_low(self):
        self.assertEqual(emails.grade("x@acme.com", {}), "Low")
        self.assertEqual(emails.grade("x@acme.com", {"pattern_votes": 3, "probe": "missing"}), "Low")


if __name__ == "__main__":
    unittest.main()
