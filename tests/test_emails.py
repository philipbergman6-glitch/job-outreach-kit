"""Tests for scripts/emails.py. No network: every outside call is replaced by a fake."""
import contextlib
import io
import smtplib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import emails  # noqa: E402

REAL_HTTP, REAL_SMTP, REAL_SYSDNS = emails.http, emails.smtp_factory, emails.system_dns


def no_system_dns(domain, kind):
    raise emails.NetError(f"nslookup -type={kind} {domain}: test has no resolver")


class Restore(unittest.TestCase):
    """Put back whatever a test replaced, so test order never matters. The system resolver
    is faked by default so no test reaches the network."""
    def setUp(self):
        emails.system_dns = no_system_dns

    def tearDown(self):
        emails.http, emails.smtp_factory, emails.system_dns = REAL_HTTP, REAL_SMTP, REAL_SYSDNS


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

    def test_letters_with_no_accent_mark_are_spelled_out(self):
        """NFKD leaves Ł, ø and ß whole, so they used to vanish: 'ukasz', 'rsted', 'gro'."""
        self.assertEqual(emails.candidates("Łukasz", "Groß", "x.io")[0], "lukasz.gross@x.io")
        self.assertEqual(emails.candidates("Søren", "Ørsted", "x.io")[0], "soren.orsted@x.io")

    def test_last_name_of_several_words(self):
        c = emails.candidates("Maria", "de la Cruz", "x.io")
        self.assertIn("maria.delacruz@x.io", c)
        self.assertIn("maria.cruz@x.io", c)

    def test_stray_hyphen_is_ignored(self):
        self.assertEqual(emails.candidates("Dana", "Levi-", "x.io")[0], "dana.levi@x.io")

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

    def test_null_mx_means_no_mail(self):
        """RFC 7505: "0 ." says the domain takes no mail; it is not a server named ''."""
        emails.http = lambda url, **k: {"Status": 0, "Answer": [{"data": "0 ."}]} if "MX" in url else {"Status": 0}
        self.assertEqual(emails.dns_mail("acme.com")[0], [])

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

    def test_blocked_doh_falls_back_to_the_system_resolver(self):
        def blocked(url, **k):
            raise emails.NetError(f"GET {url}: ssl/tls alert handshake failure")
        emails.http = blocked
        asked = []
        def sysdns(domain, kind):
            asked.append(kind)
            if kind == "MX":
                return {"Status": 0, "Answer": [{"data": "10 aspmx.l.google.com."}]}
            return {"Status": 0, "Answer": [{"data": '"v=spf1 include:_spf.google.com ~all"'}]}
        emails.system_dns = sysdns
        mx, spf = emails.dns_mail("acme.com")
        self.assertEqual((mx, spf, asked), (["aspmx.l.google.com"], ["_spf.google.com"], ["MX", "TXT"]))

    def test_proxy_refused_doh_still_falls_back_to_the_system_resolver(self):
        def refused(url, **k):
            raise emails.NetBlocked("the internet is blocked on this network: dns.google was refused")
        emails.http = refused
        emails.system_dns = lambda d, k: {"Status": 0, "Answer": [{"data": "10 aspmx.l.google.com."}]
                                          if k == "MX" else []}
        self.assertEqual(emails.dns_mail("acme.com")[0], ["aspmx.l.google.com"])

    def test_proxy_refused_doh_and_no_resolver_names_the_blocked_network(self):
        def refused(url, **k):
            raise emails.NetBlocked("the internet is blocked on this network: dns.google was refused")
        emails.http = refused  # the default system_dns here fails too
        with self.assertRaises(emails.NetBlocked) as c:
            emails.dns_mail("acme.com")
        self.assertIn("internet is blocked", str(c.exception))

    def test_system_resolver_nxdomain_hard_fails(self):
        def blocked(url, **k):
            raise emails.NetError("blocked")
        emails.http = blocked
        emails.system_dns = lambda d, k: {"Status": 3}
        with self.assertRaises(SystemExit):
            emails.dns_mail("acme.com")


class Nslookup(unittest.TestCase):
    MAC_MX = ("Server:\t\t208.67.222.222\nAddress:\t208.67.222.222#53\n\nNon-authoritative answer:\n"
              "acme.com\tmail exchanger = 10 alt1.aspmx.l.google.com.\n"
              "acme.com\tmail exchanger = 5 aspmx.l.google.com.\n\nAuthoritative answers can be found from:\n")
    WIN_MX = ("Server:  dns.example\nAddress:  10.0.0.1\n\nNon-authoritative answer:\n"
              "acme.com        MX preference = 5, mail exchanger = aspmx.l.google.com\n")
    MAC_TXT = ('Non-authoritative answer:\nacme.com\ttext = "v=spf1 include:_spf.google.com" " ~all"\n'
               'acme.com\ttext = "google-site-verification=abc"\n')
    WIN_TXT = 'Non-authoritative answer:\nacme.com        text =\n\n        "v=spf1 include:spf.protection.outlook.com -all"\n'

    def test_mx_both_layouts(self):
        self.assertEqual([a["data"] for a in emails.parse_nslookup(self.MAC_MX, "MX")["Answer"]],
                         ["10 alt1.aspmx.l.google.com.", "5 aspmx.l.google.com."])
        self.assertEqual(emails.parse_nslookup(self.WIN_MX, "MX")["Answer"], [{"data": "5 aspmx.l.google.com"}])

    def test_txt_both_layouts(self):
        mac = emails.parse_nslookup(self.MAC_TXT, "TXT")["Answer"]
        self.assertEqual(mac[0]["data"], '"v=spf1 include:_spf.google.com" " ~all"')
        win = emails.parse_nslookup(self.WIN_TXT, "TXT")["Answer"]
        self.assertEqual(win, [{"data": '"v=spf1 include:spf.protection.outlook.com -all"'}])

    def test_nxdomain_no_answer_and_failure(self):
        self.assertEqual(emails.parse_nslookup("** server can't find zz.com: NXDOMAIN", "MX"), {"Status": 3})
        self.assertEqual(emails.parse_nslookup("*** dns.example can't find zz.com: Non-existent domain", "MX"),
                         {"Status": 3})
        self.assertEqual(emails.parse_nslookup("*** Can't find acme.com: No answer", "MX"),
                         {"Status": 0, "Answer": []})
        self.assertIsNone(emails.parse_nslookup(";; connection timed out; no servers could be reached", "MX"))


class CertificateTrouble(Restore):
    """A python.org Python on macOS has no certificates until Install Certificates.command runs:
    every https call fails. The owner must hear that, not 'check the internet connection'."""
    def test_http_names_the_certificate_fix(self):
        import ssl
        import urllib.error
        import urllib.request
        import _common
        real = urllib.request.urlopen
        def broken(*a, **k):
            raise urllib.error.URLError(ssl.SSLCertVerificationError(
                1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate"))
        urllib.request.urlopen = broken
        try:
            with self.assertRaises(_common.NetError) as cm:
                _common.http("https://example.com/x")
        finally:
            urllib.request.urlopen = real
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(cm.exception))
        self.assertIn("Install Certificates.command", str(cm.exception))

    def test_dns_failure_shows_the_real_cause(self):
        import contextlib
        import io
        def fail(url, **k):
            raise emails.NetError("GET https://dns.google/resolve: certificate verify failed (Install Certificates.command)")
        emails.http = fail
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            emails.dns_mail("acme.com")
        self.assertIn("certificate verify failed", err.getvalue())


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
        super().setUp()
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


class Find(Restore):
    """emails.py find, end to end, with DNS, the mail server and the finders faked."""
    def setUp(self):
        FakeServer.accept, FakeServer.catch_all, FakeServer.refuse_connect = {"dana@acme.com"}, False, False
        FakeServer.null_sender_ok, FakeServer.rcpts = True, []
        FakeServer.reject = (550, b"5.1.1 user unknown")
        emails.smtp_factory = FakeServer
        emails.http = lambda url, **k: ({"Status": 0, "Answer": [{"data": "10 mx.acme.com."}]}
                                        if "MX" in url else {"Status": 0})
        self.real_configured = emails.configured

    def tearDown(self):
        emails.configured = self.real_configured
        super().tearDown()

    def find(self, providers=None, no_probe=False, finder=None):
        if finder:
            emails.configured = lambda only=None: {"apollo": ({}, finder, None)}
        a = type("A", (), dict(domain="acme.com", known=[], first="Dana", last="Levi", no_site=True,
                               providers=providers, all_providers=False, no_probe=no_probe))()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            emails.cmd_find(a)
        return out.getvalue()

    def test_finder_answer_at_another_domain_is_dropped(self):
        out = self.find(no_probe=True, finder=lambda *x: ("email_not_unlocked@domain.com", "valid"))
        self.assertNotIn("BEST email_not_unlocked", out)
        self.assertIn("not at acme.com", out)
        self.assertNotIn("domain.com", " ".join(FakeServer.rcpts))

    def test_unclear_probe_is_not_called_strict(self):
        FakeServer.reject = (450, b"4.2.0 greylisted, try again later")
        out = self.find()
        self.assertNotIn("domain is strict", out)
        self.assertIn("unclear", out)

    def test_unknown_provider_name_is_refused(self):
        with self.assertRaises(SystemExit):
            self.find(providers="huntr")


class ProbeCommand(Restore):
    """emails.py probe on the command line: the domain verdict printed must match probe()."""
    def setUp(self):
        super().setUp()
        FakeServer.accept, FakeServer.catch_all, FakeServer.refuse_connect = {"dana@acme.com"}, False, False
        FakeServer.null_sender_ok, FakeServer.rcpts = True, []
        FakeServer.reject = (550, b"5.1.1 user unknown")
        emails.smtp_factory = FakeServer
        emails.http = lambda url, **k: ({"Status": 0, "Answer": [{"data": "10 mx.acme.com."}]}
                                        if "MX" in url else {"Status": 0})

    def run_probe(self, *addrs):
        out, old = io.StringIO(), sys.argv
        sys.argv = ["emails.py", "probe", *addrs]
        try:
            with contextlib.redirect_stdout(out):
                emails.main()
        finally:
            sys.argv = old
        return out.getvalue()

    def test_strict_domain_is_called_strict(self):
        out = self.run_probe("dana@acme.com")
        self.assertIn("domain: strict", out)
        self.assertIn("dana@acme.com  exists", out)

    def test_accept_all_domain_is_called_accept_all(self):
        FakeServer.catch_all = True
        self.assertIn("domain: accept-all", self.run_probe("dana@acme.com"))

    def test_unclear_test_answer_is_unknown_never_strict(self):
        FakeServer.reject = (450, b"4.2.0 greylisted, try again later")
        out = self.run_probe("dana@acme.com")
        self.assertNotIn("strict", out)
        self.assertIn("domain: unknown", out)

    def test_addresses_at_two_domains_are_refused(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_probe("dana@acme.com", "dana@other.com")


class GitHub(Restore):
    """emails.py github: author addresses at the domain in the org's recent public commits."""
    def setUp(self):
        super().setUp()
        self.real_env = emails.env_optional
        emails.env_optional = lambda *names: {}  # never the real .env
        self.seen = []

    def tearDown(self):
        emails.env_optional = self.real_env
        super().tearDown()

    def fake(self, repos, commits):
        def http(url, headers=None, **k):
            self.seen.append((url, headers or {}))
            if "/orgs/" in url:
                if isinstance(repos, Exception):
                    raise repos
                return repos
            name = url.split("/repos/")[1].split("/commits")[0]
            r = commits[name]
            if isinstance(r, Exception):
                raise r
            return r
        emails.http = http

    @staticmethod
    def commit(name, email):
        return {"commit": {"author": {"name": name, "email": email}}}

    def test_authors_at_the_domain_and_its_subdomains_only(self):
        self.fake([{"full_name": "acme/a", "fork": False}, {"full_name": "acme/fork", "fork": True},
                   {"full_name": "acme/b", "fork": False}],
                  {"acme/a": [self.commit("Dana Levi", "Dana.Levi@acme.com"), self.commit("Bot", "bot@users.noreply.github.com"),
                              self.commit("Avi", "avi@eng.acme.com"), self.commit("Eve", "eve@notacme.com")],
                   "acme/b": emails.NetError("HTTP 409: Git Repository is empty.")})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            people = emails.github("acme", "acme.com")
        self.assertEqual(people, {"dana.levi@acme.com": "Dana Levi", "avi@eng.acme.com": "Avi"})
        self.assertNotIn("acme/fork", " ".join(u for u, _ in self.seen), "forks hold other people's commits")
        self.assertIn("skipped acme/b", err.getvalue())

    def test_at_most_five_repos_are_read(self):
        repos = [{"full_name": f"acme/r{i}", "fork": False} for i in range(8)]
        self.fake(repos, {f"acme/r{i}": [] for i in range(8)})
        emails.github("acme", "acme.com")
        self.assertEqual(sum("/commits" in u for u, _ in self.seen), 5)

    def test_the_token_is_sent_when_configured(self):
        emails.env_optional = lambda *names: {"GITHUB_TOKEN": "fake-token-for-tests"}  # public-sample-key: not a secret
        self.fake([], {})
        emails.github("acme", "acme.com")
        self.assertEqual(self.seen[0][1].get("Authorization"), "Bearer fake-token-for-tests")

    def test_unknown_org_or_odd_reply_hard_fails_naming_the_org(self):
        for repos in (emails.NetError("HTTP 404: Not Found", status=404), {"message": "API rate limit exceeded"}):
            self.fake(repos, {})
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                emails.github("nope-org", "acme.com")
            self.assertIn("GitHub org 'nope-org'", err.getvalue())


class Providers(Restore):
    """emails.py providers: each finder configured or not, and its credits; one failing check
    does not hide the others."""
    def setUp(self):
        super().setUp()
        self.real_env = emails.env_optional

    def tearDown(self):
        emails.env_optional = self.real_env
        super().tearDown()

    def run_providers(self, env, replies):
        emails.env_optional = lambda *names: {n: env[n] for n in names if n in env}

        def http(url, **k):
            for part, r in replies.items():
                if part in url:
                    if isinstance(r, Exception):
                        raise r
                    return r
            raise AssertionError(f"unexpected request {url.split('?')[0]}")
        emails.http = http
        out, old = io.StringIO(), sys.argv
        sys.argv = ["emails.py", "providers"]
        try:
            with contextlib.redirect_stdout(out):
                emails.main()
        finally:
            sys.argv = old
        return out.getvalue()

    def test_configured_and_missing_finders_are_listed(self):
        out = self.run_providers({"HUNTER_API_KEY": "k", "TOMBA_API_KEY": "t"},
                                 {"api.hunter.io": {"data": {"requests": {"searches": {"used": 5, "available": 25}},
                                                             "reset_date": "2026-12-01"}}})
        self.assertRegex(out, r"hunter\s+configured\s+20 searches left, reset 2026-12-01")
        self.assertRegex(out, r"tomba\s+not configured \(add TOMBA_API_KEY, TOMBA_API_SECRET to .env\)")
        self.assertRegex(out, r"prospeo\s+not configured")
        self.assertNotIn("k", [w for w in out.split() if w == "k"], "a key value is never printed")

    def test_a_failing_or_odd_credit_check_is_named_and_the_list_goes_on(self):
        out = self.run_providers({"HUNTER_API_KEY": "k", "PROSPEO_API_KEY": "p"},
                                 {"api.hunter.io": {"errors": [{"details": "Unauthorized"}]},
                                  "api.prospeo.io": emails.NetError("HTTP 401: invalid key", status=401)})
        self.assertRegex(out, r"prospeo\s+configured\s+credit check failed: HTTP 401")
        self.assertRegex(out, r"hunter\s+configured\s+credit check failed")
        self.assertRegex(out, r"findymail\s+not configured")


class Verdict(unittest.TestCase):
    def test_published_address_is_high(self):
        v = emails.grade("dana@acme.com", {"site": True})
        self.assertEqual(v, "High")

    def test_probe_on_strict_domain_is_high(self):
        self.assertEqual(emails.grade("x@acme.com", {"probe": "exists", "catch_all": False}), "High")

    def test_provider_valid_is_high_only_on_a_strict_domain(self):
        """flow/apply.md: High when "a finder reports it valid on such a domain" (one that rejects
        unknown mailboxes). Unprobed (port 25 blocked, --no-probe) or accept-all: Medium."""
        valid = {"providers": {"hunter": "valid"}}
        self.assertEqual(emails.grade("x@acme.com", dict(valid, catch_all=False)), "High")
        self.assertEqual(emails.grade("x@acme.com", valid), "Medium")
        self.assertEqual(emails.grade("x@acme.com", dict(valid, catch_all=True)), "Medium")

    def test_two_sources_agree_is_medium(self):
        self.assertEqual(emails.grade("x@acme.com", {"pattern_votes": 2}), "Medium")
        self.assertEqual(emails.grade("x@acme.com", {"providers": {"tomba": "found"}, "pattern_votes": 1}), "Medium")

    def test_guess_alone_is_low_and_probe_missing_is_low(self):
        self.assertEqual(emails.grade("x@acme.com", {}), "Low")
        self.assertEqual(emails.grade("x@acme.com", {"pattern_votes": 3, "probe": "missing"}), "Low")


if __name__ == "__main__":
    unittest.main()
