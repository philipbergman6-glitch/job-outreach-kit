"""Tests for scripts/jobs.py. No network: fetches are replaced by canned replies shaped like
the real APIs (checked live on 2026-11-17)."""
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import jobs  # noqa: E402

REAL_HTTP = jobs.http

TODAY = date(2026, 11, 17)

GH = {"jobs": [
    {"id": 1, "title": "AI Engineer", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
     "location": {"name": "Tel Aviv, Israel"}, "first_published": "2026-11-10T10:00:00-04:00",
     "updated_at": "2026-11-12T10:00:00-04:00", "company_name": "Acme",
     "content": "&lt;p&gt;Build &lt;b&gt;LLM&lt;/b&gt; agents.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"},
    {"id": 2, "title": "Account Executive", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/2",
     "location": {"name": "Remote (US)"}, "first_published": "2025-01-01T10:00:00-04:00",
     "updated_at": "2026-11-01T10:00:00-04:00", "content": "Sell."}]}
LEVER = [{"id": "ab-1", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/acme/ab-1",
          "applyUrl": "https://jobs.lever.co/acme/ab-1/apply", "createdAt": 1762905600000,
          "categories": {"location": "Berlin", "commitment": "Full-time"}, "workplaceType": "hybrid",
          "descriptionPlain": "We build things.", "lists": [{"text": "You have", "content": "<li>Go</li>"}],
          "additionalPlain": "Visa sponsorship available.",
          "salaryRange": {"min": 60000, "max": 75000, "currency": "EUR", "interval": "per-year-salary"}}]
ASHBY = {"jobs": [{"id": "x1", "title": "ML Engineer", "location": "Europe", "isRemote": True,
                   "workplaceType": "Remote", "publishedAt": "2026-11-15T20:13:45.158+00:00",
                   "jobUrl": "https://jobs.ashbyhq.com/acme/x1", "applyUrl": "https://jobs.ashbyhq.com/acme/x1/a",
                   "descriptionPlain": "Train models.", "isListed": True,
                   "compensation": {"compensationTierSummary": "$240K – $320K • Offers Equity"}}]}


COMEET_PAGE = ('<html><script>var COMPANY_DATA = {"name": "Acme", "company_uid": "57.000", '
               '"token": "0123456789ABCDEF0123456789ABCDEF", "slug": "acme"};'  # public-sample-key: not a secret
               'var COMPANY_POSITIONS_DATA = null;</script></html>')
COMEET = [{"uid": "F6.B68", "name": "Creative Strategist", "department": "Marketing",
           "location": {"name": "Tel-Aviv, Israel", "country": "IL", "is_remote": True},
           "workplace_type": "Hybrid", "time_updated": "2026-11-16T11:21:21Z",
           "url_active_page": "https://acme.io/careers",
           "url_comeet_hosted_page": "https://www.comeet.com/jobs/acme/57.000/creative-strategist/F6.B68",
           "email": "jobs-x@applynow.io",
           "details": [{"name": "Description", "value": "<p>Write <b>briefs</b>.</p>", "order": 1},
                       {"name": "Requirements", "value": None, "order": 2}]},
          {"uid": "AA.001", "name": "", "url_comeet_hosted_page": "https://www.comeet.com/jobs/acme/57.000/x/AA.001"}]

WORKABLE = {"name": "Acme", "jobs": [
    {"title": "Area Manager", "shortcode": "54185009AA", "telecommuting": False, "country": "Australia",
     "city": "Sydney", "state": "New South Wales", "url": "https://apply.workable.com/j/54185009AA",
     "published_on": "2026-10-02", "description": "<p>Run the <b>area</b>.</p>"},
    {"title": "", "shortcode": "X"}]}
RECRUITEE = {"offers": [
    {"id": 2819061, "title": "Technical Lead (.Net)", "company_name": "Auditdata", "location": "Remote job",
     "country": "Poland", "remote": True, "hybrid": False, "on_site": False, "status": "published",
     "published_at": "2026-11-10 15:35:48 UTC", "careers_url": "https://acme.recruitee.com/o/technical-lead-net-3",
     "description": "<p>Lead the team.</p>", "requirements": "<ul><li>C#</li></ul>",
     "salary": {"min": 5000, "max": 7000, "period": "month", "currency": "EUR"}}]}
BREEZY = [{"id": "5480ceb9beff", "friendly_id": "5480ceb9beff-account-manager", "name": "Account Manager",
           "url": "https://acme.breezy.hr/p/5480ceb9beff-account-manager",
           "published_date": "2026-10-19T13:35:11.590Z", "salary": "$50,000 – $95,000 / year",
           "location": {"name": "Birmingham, AL", "is_remote": False}, "company": {"name": "Atlas RFID"}}]
BREEZY_PAGE = ('<html><script type="application/ld+json">{"@type":"WebSite","name":"Breezy HR"}</script>'
               '<script type="application/ld+json">{"@type":"JobPosting","title":"Account Manager",'
               '"datePosted":"2025-08-15","description":"&lt;p&gt;Grow accounts.&lt;/p&gt;"}</script></html>')
PERSONIO = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs><position><id>2886454</id><office>Vienna</office><name>Finance &amp; Accounting Manager</name>
<jobDescriptions><jobDescription><name>Deine Aufgaben</name><value><![CDATA[<ul><li>Buchhaltung</li></ul>]]></value>
</jobDescription></jobDescriptions><createdAt>2026-11-12T13:32:47+00:00</createdAt></position>
<position><id>9</id><name></name></position></workzag-jobs>"""
RIPPLING = {"items": [{"id": "1b1dbd89", "name": "Solutions Architect ",
                       "url": "https://ats.rippling.com/acme/jobs/1b1dbd89",
                       "locations": [{"name": "Remote (United States)", "country": "United States"}]}],
            "page": 0, "pageSize": 20, "totalItems": 1, "totalPages": 1}
RIPPLING_PAGE = ('<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"apiData":'
                 '{"jobPost":{"createdOn":"2026-09-10T15:59:50.605000-07:00","description":{"company":"<p>We sell.</p>",'
                 '"role":"<p>Design systems.</p>"}}}}}}</script></html>')


class Detect(unittest.TestCase):
    def test_each_board_is_recognised(self):
        cases = {
            "https://job-boards.greenhouse.io/gongio/jobs/4723250006": ("greenhouse", "gongio"),
            "https://boards.greenhouse.io/embed/job_board?for=catonetworks": ("greenhouse", "catonetworks"),
            "https://jobs.lever.co/palantir/6ed76ce8": ("lever", "palantir"),
            "https://jobs.ashbyhq.com/linear/d3bc1ced": ("ashby", "linear"),
            "https://jobs.smartrecruiters.com/BoschGroup/744000162069969-x": ("smartrecruiters", "BoschGroup"),
            "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/x": (
                "workday", "nvidia.wd5/NVIDIAExternalCareerSite"),
            "https://www.comeet.com/jobs/guardio/57.000": ("comeet", "guardio/57.000"),
            "https://www.comeet.com/jobs/briefcam/E3.00B/devops-engineer/A1.234": ("comeet", "briefcam/E3.00B"),
            "https://comeet.co/jobs/tripleten/98.008/": ("comeet", "tripleten/98.008"),
            "https://apply.workable.com/amer-sports/j/54185009AA/": ("workable", "amer-sports"),
            "https://auditdata.recruitee.com/o/technical-lead-net-3": ("recruitee", "auditdata"),
            "https://atlas-rfid.breezy.hr/p/5480ceb9beff-account-manager": ("breezy", "atlas-rfid"),
            "https://anyline-gmbh.jobs.personio.de/job/2886454": ("personio", "anyline-gmbh"),
            "https://ats.rippling.com/duplocloud/jobs/1b1dbd89": ("rippling", "duplocloud"),
            "https://jobs.eu.lever.co/aavelabs/abc-1": ("lever", "eu/aavelabs"),
        }
        for url, want in cases.items():
            self.assertEqual(jobs.detect(url), want, url)

    def test_unknown_board(self):
        self.assertEqual(jobs.detect("https://acme.com/careers"), (None, None))


class Normalise(unittest.TestCase):
    def test_greenhouse(self):
        j = jobs.from_greenhouse(GH["jobs"][0], "acme")
        self.assertEqual(j["posted"], date(2026, 11, 10))
        self.assertEqual(j["location"], "Tel Aviv, Israel")
        self.assertIn("Build LLM agents.", j["text"])
        self.assertIn("- Python", j["text"])
        self.assertEqual(j["company"], "Acme")

    def test_lever_salary_and_sponsorship(self):
        j = jobs.from_lever(LEVER[0], "acme")
        self.assertEqual(j["salary"], "60,000–75,000 EUR per year")
        self.assertEqual(j["posted"], date(2025, 11, 12))
        self.assertIn("Visa sponsorship available.", j["text"])
        self.assertIn("- Go", j["text"])
        self.assertEqual(j["sponsorship"], "mentioned")

    def test_lever_open_ended_salary_does_not_crash(self):
        x = dict(LEVER[0], salaryRange={"min": 60000, "max": None, "currency": "EUR", "interval": "per-year-salary"})
        self.assertEqual(jobs.from_lever(x, "acme")["salary"], "60,000–? EUR per year")

    def test_ashby(self):
        j = jobs.from_ashby(ASHBY["jobs"][0], "acme")
        self.assertTrue(j["remote"])
        self.assertEqual(j["salary"], "$240K – $320K • Offers Equity")
        self.assertEqual(j["posted"], date(2026, 11, 15))

    def test_workday_relative_dates(self):
        self.assertEqual(jobs.workday_posted("Posted Today", TODAY), TODAY)
        self.assertEqual(jobs.workday_posted("Posted Yesterday", TODAY), TODAY - timedelta(days=1))
        self.assertEqual(jobs.workday_posted("Posted 11 Days Ago", TODAY), TODAY - timedelta(days=11))
        self.assertEqual(jobs.workday_posted("Posted 30+ Days Ago", TODAY), TODAY - timedelta(days=31))
        self.assertIsNone(jobs.workday_posted("whenever", TODAY))

    def test_sponsorship_wording(self):
        self.assertEqual(jobs.sponsorship("We are unable to sponsor visas."), "no")
        self.assertEqual(jobs.sponsorship("Visa sponsorship is available"), "mentioned")
        self.assertEqual(jobs.sponsorship("Build things."), "")


class Filter(unittest.TestCase):
    def test_title_location_and_age(self):
        js = [jobs.from_greenhouse(x, "acme") for x in GH["jobs"]]
        keep = jobs.keep(js, title=r"engineer", location=r"israel|remote", days=30, today=TODAY)
        self.assertEqual([j["title"] for j in keep], ["AI Engineer"])

    def test_undated_jobs_are_kept_and_flagged(self):
        j = dict(jobs.from_greenhouse(GH["jobs"][0], "acme"), posted=None)
        self.assertEqual(len(jobs.keep([j], title="", location="", days=30, today=TODAY)), 1)

    def test_bad_regex_is_refused(self):
        with self.assertRaises(SystemExit):
            jobs.keep([], title="(", location="", days=30, today=TODAY)


class Fetch(unittest.TestCase):
    def tearDown(self):
        jobs.http = REAL_HTTP

    def test_list_greenhouse_through_the_fetcher(self):
        jobs.http = lambda url, **k: GH
        got = jobs.fetch("greenhouse", "acme")
        self.assertEqual(len(got), 2)

    def test_save_writes_a_jd_file_with_front_matter(self):
        j = jobs.from_greenhouse(GH["jobs"][0], "acme")
        with tempfile.TemporaryDirectory() as d:
            p = jobs.save(j, Path(d))
            t = p.read_text(encoding="utf-8")
            self.assertTrue(t.startswith("---\nurl: https://job-boards.greenhouse.io/acme/jobs/1\n"))
            self.assertIn("posted: 2026-11-10", t)
            self.assertIn("Build LLM agents.", t)
            self.assertEqual(p.name, "acme-1.md")


class Comeet(unittest.TestCase):
    """Comeet's positions API needs the company uid and a token, both printed in the public
    job-list page (checked live on 2026-11-19)."""
    def tearDown(self):
        jobs.http = REAL_HTTP

    def fake(self, page=COMEET_PAGE, positions=COMEET):
        calls = []

        def http(url, **k):
            calls.append((url, k))
            return page if "/careers-api/" not in url else positions
        jobs.http = http
        return calls

    def test_reads_the_token_from_the_page_then_the_api(self):
        calls = self.fake()
        got = jobs.fetch("comeet", "acme/57.000")
        self.assertEqual(calls[0][0], "https://www.comeet.com/jobs/acme/57.000")
        self.assertFalse(calls[0][1].get("as_json", True))
        self.assertEqual(calls[1][0], "https://www.comeet.co/careers-api/2.0/company/57.000/positions"
                                      "?token=0123456789ABCDEF0123456789ABCDEF&details=true")  # public-sample-key: not a secret
        self.assertEqual(len(got), 1, "a row without a title is dropped")
        j = got[0]
        self.assertEqual(j["title"], "Creative Strategist")
        self.assertEqual(j["url"], "https://www.comeet.com/jobs/acme/57.000/creative-strategist/F6.B68")
        self.assertEqual(j["location"], "Tel-Aviv, Israel (Hybrid)")
        self.assertFalse(j["remote"], "Comeet marks hybrid jobs is_remote; workplace_type decides")
        self.assertEqual(j["posted"], date(2026, 11, 16))
        self.assertIn("Write briefs.", j["text"])
        self.assertEqual(j["apply_email"], "jobs-x@applynow.io")

    def test_page_without_a_token_hard_fails(self):
        self.fake(page="<html>nothing here</html>")
        with self.assertRaises(SystemExit):
            jobs.fetch("comeet", "acme/57.000")

    def test_token_of_another_company_is_not_used(self):
        self.fake(page=COMEET_PAGE.replace("57.000", "11.111"))
        with self.assertRaises(SystemExit):
            jobs.fetch("comeet", "acme/57.000")

    def test_reply_that_is_not_a_list_hard_fails(self):
        self.fake(positions={"error": "bad token"})
        with self.assertRaises(SystemExit):
            jobs.fetch("comeet", "acme/57.000")

    def test_bad_board_name_hard_fails(self):
        with self.assertRaises(SystemExit):
            jobs.fetch("comeet", "acme")

    def test_saved_file_carries_the_apply_address(self):
        self.fake()
        j = jobs.fetch("comeet", "acme/57.000")[0]
        with tempfile.TemporaryDirectory() as d:
            t = jobs.save(j, Path(d)).read_text(encoding="utf-8")
        self.assertIn("apply_email: jobs-x@applynow.io\n", t)


class MoreBoards(unittest.TestCase):
    """One public GET each, no key (reply shapes checked live on 2026-11-19)."""
    def tearDown(self):
        jobs.http = REAL_HTTP

    def serve(self, replies):
        seen = []

        def http(url, **k):
            seen.append(url)
            self.assertTrue(k.get("pinned"), url)
            for prefix, reply in replies.items():
                if url.startswith(prefix):
                    return reply
            self.fail(f"unexpected fetch {url}")
        jobs.http = http
        return seen

    def test_workable(self):
        seen = self.serve({"https://apply.workable.com/api/v1/widget/accounts/acme?details=true": WORKABLE})
        got = jobs.fetch("workable", "acme")
        self.assertEqual(len(got), 1)
        j = got[0]
        self.assertEqual((j["title"], j["location"], j["posted"]), ("Area Manager", "Sydney, New South Wales, Australia",
                                                                    date(2026, 10, 2)))
        self.assertEqual(j["url"], "https://apply.workable.com/acme/j/54185009AA/")
        self.assertFalse(j["remote"])
        self.assertIn("Run the area.", j["text"])

    def test_recruitee(self):
        self.serve({"https://acme.recruitee.com/api/offers/": RECRUITEE})
        j = jobs.fetch("recruitee", "acme")[0]
        self.assertEqual(j["company"], "Auditdata")
        self.assertEqual(j["posted"], date(2026, 11, 10))
        self.assertTrue(j["remote"])
        self.assertEqual(j["salary"], "5,000–7,000 EUR per month")
        self.assertIn("Lead the team.", j["text"])
        self.assertIn("- C#", j["text"])

    def test_breezy_lists_then_reads_the_page(self):
        self.serve({"https://acme.breezy.hr/json": BREEZY,
                    "https://acme.breezy.hr/p/5480ceb9beff-account-manager": BREEZY_PAGE})
        j = jobs.fetch("breezy", "acme")[0]
        self.assertEqual((j["posted"], j["salary"], j["company"]), (date(2026, 10, 19), "$50,000 – $95,000 / year",
                                                                    "Atlas RFID"))
        self.assertEqual(j["text"], "")
        jobs.detail(j)
        self.assertIn("Grow accounts.", j["text"])

    def test_job_page_without_text_hard_fails(self):
        self.serve({"https://acme.breezy.hr/json": BREEZY, "https://acme.breezy.hr/p/": "<html>moved</html>"})
        j = jobs.fetch("breezy", "acme")[0]
        with self.assertRaises(SystemExit):
            jobs.detail(j)

    def test_personio_xml(self):
        self.serve({"https://acme.jobs.personio.de/xml": PERSONIO})
        got = jobs.fetch("personio", "acme")
        self.assertEqual(len(got), 1, "a position without a name is dropped")
        j = got[0]
        self.assertEqual(j["url"], "https://acme.jobs.personio.de/job/2886454")
        self.assertEqual(j["title"], "Finance & Accounting Manager")
        self.assertEqual(j["posted"], date(2026, 11, 12))
        self.assertIn("- Buchhaltung", j["text"])

    def test_rippling_lists_then_reads_the_page(self):
        self.serve({"https://ats.rippling.com/api/v2/board/acme/jobs": RIPPLING,
                    "https://ats.rippling.com/acme/jobs/1b1dbd89": RIPPLING_PAGE})
        j = jobs.fetch("rippling", "acme")[0]
        self.assertEqual((j["title"], j["location"]), ("Solutions Architect", "Remote (United States)"))
        self.assertTrue(j["remote"])
        jobs.detail(j)
        self.assertIn("Design systems.", j["text"])
        self.assertEqual(j["posted"], date(2026, 9, 10))

    def test_malformed_replies_hard_fail(self):
        for ats, prefix, bad in (("workable", "https://apply.workable.com/", {"error": "x"}),
                                 ("recruitee", "https://acme.recruitee.com/", ["x"]),
                                 ("breezy", "https://acme.breezy.hr/", {"x": 1}),
                                 ("personio", "https://acme.jobs.personio.de/", "<html>not xml"),
                                 ("rippling", "https://ats.rippling.com/", [])):
            self.serve({prefix: bad})
            with self.assertRaises(SystemExit, msg=ats):
                jobs.fetch(ats, "acme")

    def test_board_names_are_one_safe_word(self):
        for ats in ("workable", "recruitee", "breezy", "personio", "rippling"):
            with self.assertRaises(SystemExit, msg=ats):
                jobs.fetch(ats, "acme/../x")


class LeverEU(unittest.TestCase):
    def tearDown(self):
        jobs.http = REAL_HTTP

    def test_eu_board_reads_the_eu_api(self):
        seen = []
        jobs.http = lambda url, **k: seen.append(url) or LEVER
        j = jobs.fetch("lever", "eu/aavelabs")[0]
        self.assertEqual(seen, ["https://api.eu.lever.co/v0/postings/aavelabs?mode=json"])
        self.assertEqual(j["company"], "aavelabs")


REGISTRY = """# header line one
# header line two
#paid\tlever\thashtagpaid
Similarweb\tgreenhouse\tsimilarweb
Acme Robotics\tgreenhouse\tacmerobotics
Acme Robotics\tcomeet\tacme/57.000
Müller & Söhne GmbH\tpersonio\tmueller
"""


class Find(unittest.TestCase):
    """Company name -> job board: the employer registry first, then guessed board names."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Path(self.tmp.name) / "employers.tsv"
        self.reg.write_text(REGISTRY, encoding="utf-8")
        self.real_reg = jobs.REGISTRY
        jobs.REGISTRY = self.reg

    def tearDown(self):
        jobs.http, jobs.REGISTRY = REAL_HTTP, self.real_reg
        self.tmp.cleanup()

    def no_network(self):
        jobs.http = lambda url, **k: self.fail(f"registry hit must not fetch {url}")

    def test_registry_exact_name(self):
        self.no_network()
        self.assertEqual(jobs.find("Similarweb"), [("registry", "greenhouse:similarweb", "Similarweb")])

    def test_registry_lists_every_board_of_a_company(self):
        self.no_network()
        self.assertEqual([h[1] for h in jobs.find("acme robotics")], ["greenhouse:acmerobotics", "comeet:acme/57.000"])

    def test_registry_ignores_legal_suffixes_accents_and_punctuation(self):
        self.no_network()
        self.assertEqual(jobs.find("Similarweb Ltd.")[0][1], "greenhouse:similarweb")
        self.assertEqual(jobs.find("Muller & Sohne")[0][1], "personio:mueller")
        self.assertEqual(jobs.find("#paid")[0][1], "lever:hashtagpaid", "a name starting with # is data")

    def test_guess_stops_at_the_first_board_with_jobs(self):
        seen = []

        def http(url, **k):
            seen.append(url)
            if "greenhouse" in url:
                raise jobs.NetError("HTTP 404")
            if "ashbyhq" in url:
                return {"jobs": [dict(ASHBY["jobs"][0], id=f"x{i}") for i in range(6)]}
            self.fail(f"probed past the first hit: {url}")
        jobs.http = http
        hits = jobs.find("Northwind")
        self.assertEqual(hits[0][:2], ("guessed", "ashby:northwind"))
        self.assertIn("6 open", hits[0][2])
        self.assertIn("verify", hits[0][2])
        self.assertNotIn("small board", hits[0][2])
        self.assertTrue(seen[0].startswith("https://boards-api.greenhouse.io/v1/boards/northwind/"))

    def test_small_guessed_board_is_flagged(self):
        def http(url, **k):
            if "greenhouse" in url:
                return GH
            raise jobs.NetError("HTTP 404")
        jobs.http = http
        hits = jobs.find("Northwind")
        self.assertEqual(hits[0][1], "greenhouse:northwind")
        self.assertIn("small board", hits[0][2])

    def test_a_board_with_no_jobs_is_not_a_hit(self):
        """SmartRecruiters answers 200 with nothing for any name at all."""
        def http(url, **k):
            if "smartrecruiters" in url:
                return {"content": [], "totalFound": 0}
            raise jobs.NetError("HTTP 404")
        jobs.http = http
        self.assertEqual(jobs.find("Northwind"), [])

    def test_multi_word_names_try_joined_then_dashed(self):
        seen = []

        def http(url, **k):
            seen.append(url)
            raise jobs.NetError("HTTP 404")
        jobs.http = http
        jobs.find("North Wind")
        gh = [u for u in seen if "greenhouse" in u]
        self.assertEqual([u.split("/boards/")[1].split("/")[0] for u in gh], ["northwind", "north-wind"])


class PinnedHost(unittest.TestCase):
    """Board reads stay on the board's own host, over HTTPS."""
    def tearDown(self):
        jobs.http = REAL_HTTP

    def test_detail_link_off_the_board_is_refused(self):
        jobs.http = lambda url, **k: self.fail("must not fetch")
        j = {"ats": "smartrecruiters", "board": "Acme", "text": "", "url": "https://jobs.smartrecruiters.com/Acme/1",
             "detail": "https://evil.example.net/v1/companies/Acme/postings/1"}
        with self.assertRaises(SystemExit):
            jobs.detail(j)

    def test_plain_http_is_refused(self):
        import _common
        with self.assertRaises(_common.NetError):
            _common.http("http://boards-api.greenhouse.io/v1/boards/x/jobs", pinned=True)

    def test_redirect_to_another_host_is_refused(self):
        import urllib.request
        import _common
        h = _common.SameHostRedirect()
        req = urllib.request.Request("https://api.example.com/a")
        with self.assertRaises(_common.NetError):
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.example.net/a")
        self.assertIsNotNone(h.redirect_request(req, None, 302, "Found", {}, "https://api.example.com/b"))

    def test_redirect_to_plain_http_is_refused(self):
        import urllib.request
        import _common
        h = _common.SameHostRedirect()
        req = urllib.request.Request("https://api.example.com/a")
        with self.assertRaises(_common.NetError):
            h.redirect_request(req, None, 302, "Found", {}, "http://api.example.com/b")


if __name__ == "__main__":
    unittest.main()
