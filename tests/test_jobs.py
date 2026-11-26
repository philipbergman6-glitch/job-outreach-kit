"""Tests for scripts/jobs.py. No network: fetches are replaced by canned replies shaped like
the real APIs (checked live on 2026-11-17)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _common  # noqa: E402
import jobs  # noqa: E402

REAL_HTTP = jobs.http
REAL_SLEEP = jobs.time.sleep

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
                raise jobs.NetError("HTTP 404", status=404)
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
            raise jobs.NetError("HTTP 404", status=404)
        jobs.http = http
        hits = jobs.find("Northwind")
        self.assertEqual(hits[0][1], "greenhouse:northwind")
        self.assertIn("small board", hits[0][2])

    def test_a_board_with_no_jobs_is_not_a_hit(self):
        """SmartRecruiters answers 200 with nothing for any name at all."""
        def http(url, **k):
            if "smartrecruiters" in url:
                return {"content": [], "totalFound": 0}
            raise jobs.NetError("HTTP 404", status=404)
        jobs.http = http
        self.assertEqual(jobs.find("Northwind"), [])

    def test_multi_word_names_try_joined_then_dashed(self):
        seen = []

        def http(url, **k):
            seen.append(url)
            raise jobs.NetError("HTTP 404", status=404)
        jobs.http = http
        jobs.find("North Wind")
        gh = [u for u in seen if "greenhouse" in u]
        self.assertEqual([u.split("/boards/")[1].split("/")[0] for u in gh], ["northwind", "north-wind"])


def gone(status, reply=""):
    return jobs.NetError(f"HTTP {status}", status=status, reply=reply)


class Alive(unittest.TestCase):
    """open / closed / unknown. Closed only on the board's own word: a per-job 404/410 where that
    is proof, a closed flag, or a complete board list without this job. Anything else: unknown."""
    def tearDown(self):
        jobs.http = REAL_HTTP

    def answer(self, *replies):
        """Each call gets the next reply; an exception is raised."""
        it, seen = iter(replies), []

        def http(url, **k):
            seen.append(url)
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r
        jobs.http = http
        return seen

    def test_greenhouse_per_job(self):
        seen = self.answer({"id": 7, "title": "AI Engineer"})
        self.assertEqual(jobs.alive("https://job-boards.greenhouse.io/acme/jobs/7")[0], "open")
        self.assertEqual(seen, ["https://boards-api.greenhouse.io/v1/boards/acme/jobs/7"])
        self.answer(gone(404))
        self.assertEqual(jobs.alive("https://job-boards.greenhouse.io/acme/jobs/7")[0], "closed")

    def test_lever_404_is_not_proof(self):
        """Lever's API hides some live (confidential) postings."""
        self.answer(gone(404))
        state, why = jobs.alive("https://jobs.lever.co/acme/0b2f6a3e-1111-2222-3333-444455556666")
        self.assertEqual(state, "unknown")
        self.assertIn("page", why)

    def test_smartrecruiters_reads_the_active_flag(self):
        self.answer({"id": "744000162462500", "active": False})
        self.assertEqual(jobs.alive("https://jobs.smartrecruiters.com/Acme/744000162462500-analyst")[0], "closed")
        self.answer(gone(404))
        self.assertEqual(jobs.alive("https://jobs.smartrecruiters.com/Acme/744000162462500-analyst")[0], "unknown")

    def test_workday_withdrawn_and_missing(self):
        url = "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/Engineer_JR1"
        seen = self.answer({"jobPostingInfo": {"title": "Engineer"}})
        self.assertEqual(jobs.alive(url)[0], "open")
        self.assertEqual(seen, ["https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/job/US-CA/Engineer_JR1"])
        self.answer(gone(403, '{"httpStatus":403,"errorCode":"S22"}'))
        self.assertEqual(jobs.alive(url)[0], "closed")
        self.answer(gone(403, "<html>blocked</html>"))
        self.assertEqual(jobs.alive(url)[0], "unknown")
        self.answer(gone(404))
        self.assertEqual(jobs.alive(url)[0], "closed")

    def test_workable_per_job(self):
        self.answer({"shortcode": "54185009AA", "state": "published"})
        self.assertEqual(jobs.alive("https://apply.workable.com/acme/j/54185009AA/")[0], "open")
        self.answer(gone(404))
        self.assertEqual(jobs.alive("https://apply.workable.com/acme/j/54185009AA/")[0], "closed")

    def test_board_list_decides_for_list_only_boards(self):
        url = "https://jobs.ashbyhq.com/acme/x1"
        self.answer(ASHBY)
        self.assertEqual(jobs.alive(url)[0], "open")
        self.answer({"jobs": []})
        state, why = jobs.alive(url)
        self.assertEqual(state, "closed")
        self.assertIn("not among", why)
        self.answer(gone(500))
        self.assertEqual(jobs.alive(url)[0], "unknown")

    def test_comeet_board_list(self):
        self.answer(COMEET_PAGE, COMEET)
        self.assertEqual(jobs.alive("https://www.comeet.com/jobs/acme/57.000/creative-strategist/F6.B68")[0], "open")
        self.answer(COMEET_PAGE, COMEET)
        self.assertEqual(jobs.alive("https://www.comeet.com/jobs/acme/57.000/old-role/F6.B00")[0], "closed")

    def test_any_other_page_is_closed_only_on_404_or_410(self):
        self.answer(gone(410))
        self.assertEqual(jobs.alive("https://acme.com/careers/42")[0], "closed")
        self.answer("<html>Sorry, this job is no longer available</html>")
        self.assertEqual(jobs.alive("https://acme.com/careers/42")[0], "unknown")
        self.answer(gone(503))
        self.assertEqual(jobs.alive("https://acme.com/careers/42")[0], "unknown")


class ReviewFixes(unittest.TestCase):
    def tearDown(self):
        jobs.http = REAL_HTTP

    def test_workday_board_must_be_tenant_instance_site(self):
        jobs.http = lambda url, **k: self.fail(f"must not fetch {url}")
        for bad in ("evil.example#/x", "nvidia", "nvidia.wd5/a/b?x"):
            with self.assertRaises(SystemExit, msg=bad):
                jobs.fetch("workday", bad)

    def test_malformed_rows_are_dropped_on_every_board(self):
        for ats, reply in (("greenhouse", {"jobs": [{"id": 1, "title": "x"}] + GH["jobs"][:1]}),
                           ("ashby", {"jobs": [{"id": "a"}] + ASHBY["jobs"]}),
                           ("lever", [{"id": "z"}] + LEVER),
                           ("smartrecruiters", {"content": [{"id": "1"}], "totalFound": 1})):
            jobs.http = lambda url, r=reply, **k: r
            got = jobs.fetch(ats, "acme")
            self.assertTrue(all(j["title"] and j["url"] for j in got), ats)

    def test_unlisted_ashby_posting_is_not_called_closed(self):
        unlisted = dict(ASHBY["jobs"][0], isListed=False)
        jobs.http = lambda url, **k: {"jobs": [unlisted]}
        self.assertEqual(jobs.fetch("ashby", "acme"), [], "the search list skips unlisted jobs")
        self.assertEqual(jobs.alive("https://jobs.ashbyhq.com/acme/x1")[0], "open")

    def test_comeet_page_without_token_is_unknown_not_a_crash(self):
        jobs.http = lambda url, **k: "<html>no token</html>"
        self.assertEqual(jobs.alive("https://www.comeet.com/jobs/acme/57.000/x/F6.B68")[0], "unknown")

    def test_personio_com_boards(self):
        self.assertEqual(jobs.detect("https://acme.jobs.personio.com/job/2886454"), ("personio", "com/acme"))
        seen = []
        jobs.http = lambda url, **k: seen.append(url) or PERSONIO
        j = jobs.fetch("personio", "com/acme")[0]
        self.assertEqual(seen, ["https://acme.jobs.personio.com/xml"])
        self.assertEqual(j["url"], "https://acme.jobs.personio.com/job/2886454")

    def test_personio_xml_that_is_not_the_feed_hard_fails(self):
        jobs.http = lambda url, **k: "<?xml version='1.0'?><error>maintenance</error>"
        with self.assertRaises(SystemExit):
            jobs.fetch("personio", "acme")


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


class ReviewFindings(unittest.TestCase):
    """Bugs found in the 2026-11-19 review."""
    def tearDown(self):
        jobs.http = REAL_HTTP
        jobs.time.sleep = REAL_SLEEP

    def test_a_real_less_than_sign_survives(self):
        self.assertEqual(jobs.text_of("<p>Requires &lt;3 years or &gt;5 in Go</p><p>Python</p>"),
                         "Requires <3 years or >5 in Go\nPython")
        self.assertIn("Build LLM agents.", jobs.text_of(GH["jobs"][0]["content"]))  # escaped HTML still read

    def test_sponsorship_not_available_is_no(self):
        self.assertEqual(jobs.sponsorship("Visa sponsorship is not available for this role."), "no")
        self.assertEqual(jobs.sponsorship("We are not sponsoring visas."), "no")

    def test_missing_location_does_not_stop_the_board(self):
        x = dict(LEVER[0], categories={"location": None})
        self.assertEqual(jobs.from_lever(x, "acme")["location"], "")
        self.assertEqual(jobs.from_ashby(dict(ASHBY["jobs"][0], location=None), "acme")["location"], "")
        self.assertEqual(jobs.from_greenhouse(dict(GH["jobs"][0], location={"name": None}), "acme")["location"], "")

    def test_long_ids_never_share_a_file(self):
        base = dict(ats="workday", board="nvidia.wd5/X", company="nvidia", title="t", location="", remote=None,
                    posted=None, salary="", sponsorship="", url="u")
        long = "Senior-Principal-Software-Engineer--Distributed-Systems-and-Infrastructure_JR"
        with tempfile.TemporaryDirectory() as d:
            p1 = jobs.save(dict(base, id=long + "2001234", text="first"), Path(d))
            p2 = jobs.save(dict(base, id=long + "2009999", text="second"), Path(d))
            self.assertNotEqual(p1, p2)
            self.assertIn("first", p1.read_text(encoding="utf-8"))
            short = jobs.save(dict(base, id="JR1", text="x"), Path(d))
            self.assertEqual(short.name, "nvidia-jr1.md")  # short names unchanged

    def workday(self, total):
        seen = []

        def http(url, body=None, **k):
            seen.append(body["offset"])
            n = min(20, max(0, total - body["offset"]))
            return {"total": total if body["offset"] == 0 else 0,  # Workday reports 0 after page 1
                    "jobPostings": [{"title": f"J{body['offset'] + i}", "externalPath": f"/job/x/J_{body['offset'] + i}"}
                                    for i in range(n)]}
        jobs.http, jobs.time.sleep = http, lambda s: None
        return seen

    def test_workday_reads_past_the_second_page(self):
        seen = self.workday(90)
        self.assertEqual(len(jobs.fetch("workday", "nvidia.wd5/NVIDIAExternalCareerSite")), 90)
        self.assertEqual(seen, [0, 20, 40, 60, 80])

    def test_workday_says_when_it_stops_short(self):
        self.workday(5000)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = jobs.fetch("workday", "nvidia.wd5/NVIDIAExternalCareerSite")
        self.assertLess(len(got), 5000)
        self.assertIn("5000", err.getvalue())
        self.assertIn("--search", err.getvalue())

    def test_find_needs_a_latin_name_to_guess_from(self):
        jobs.http = lambda url, **k: self.fail(f"must not fetch {url}")
        with self.assertRaises(SystemExit):
            jobs.find("אלביט מערכות")

    def test_list_names_the_undated_jobs_kept_past_days(self):
        undated = jobs.from_rippling({"id": "1", "name": "Old", "url": "https://ats.rippling.com/a/jobs/1"}, "a")
        self.assertEqual(jobs.undated_note([undated], 30), "1 kept with no posting date (--days cannot judge them)")
        self.assertEqual(jobs.undated_note([], 30), "")



class OddReplies(unittest.TestCase):
    """A board whose reply has nulls or odd shapes in it: that board fails alone, the rest go on."""
    def tearDown(self):
        jobs.http = REAL_HTTP
        jobs.time.sleep = REAL_SLEEP

    def test_null_location_on_any_board_reads_as_empty(self):
        jobs.time.sleep = lambda s: None
        wd = {"total": 1, "jobPostings": [{"title": "Data Engineer", "externalPath": "/job/x/Data-Engineer_R1",
                                           "locationsText": None, "postedOn": "Posted Today"}]}
        jobs.http = lambda url, **k: wd
        self.assertEqual(jobs.fetch("workday", "acme.wd5/Ext")[0]["location"], "")
        br = [dict(BREEZY[0], location={"name": None, "is_remote": None})]
        jobs.http = lambda url, **k: br
        self.assertEqual(jobs.fetch("breezy", "acme")[0]["location"], "")
        jobs.http = lambda url, **k: {"jobs": [dict(ASHBY["jobs"][0], location=None)]}
        js = jobs.keep(jobs.fetch("ashby", "acme"), "", "Europe", 3650)
        self.assertEqual(js, [], "a null place matches no place filter, and does not crash keep()")

    def test_odd_reply_is_a_clear_board_failure_not_a_crash(self):
        jobs.http = lambda url, **k: {"jobs": [dict(GH["jobs"][0], location="Tel Aviv")]}  # a string, not {name}
        with self.assertRaises(jobs.NetError) as c:
            jobs.read_board("greenhouse", "acme")
        self.assertIn("shape", str(c.exception))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            jobs.fetch("greenhouse", "acme")
        self.assertIn("greenhouse board 'acme'", err.getvalue())

    def test_find_reports_a_failing_board_and_tries_the_next(self):
        def http(url, **k):
            if "greenhouse" in url:
                return {"jobs": [dict(GH["jobs"][0], location="Tel Aviv")]}
            if "ashbyhq" in url:
                return ASHBY
            raise jobs.NetError("HTTP 404", status=404)
        jobs.http = http
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            hits = jobs.find("Northwind")
        self.assertEqual(hits[0][1], "ashby:northwind")
        self.assertIn("greenhouse:northwind", err.getvalue())
        self.assertNotIn("lever", err.getvalue(), "a plain 404 (no such board) is not reported")

    def test_find_still_stops_on_a_blocked_network(self):
        def http(url, **k):
            raise _common.NetBlocked("the internet is blocked")
        jobs.http = http
        with self.assertRaises(_common.NetBlocked):
            jobs.find("Northwind")

    def test_remote_in_the_place_beats_a_weak_false_flag(self):
        """Ashby's isRemote and Workable's telecommuting say False when unset."""
        a = jobs.from_ashby(dict(ASHBY["jobs"][0], isRemote=False, location="Remote - EMEA"), "acme")
        self.assertIs(a["remote"], True)
        w = jobs.from_workable(dict(WORKABLE["jobs"][0], city="Remote"), "acme")
        self.assertIs(w["remote"], True)
        self.assertIs(jobs.from_workable(WORKABLE["jobs"][0], "acme")["remote"], False)
        self.assertIs(jobs.from_ashby(dict(ASHBY["jobs"][0], isRemote=False), "acme")["remote"], False)

class NonAsciiLinks(unittest.TestCase):
    """A Hebrew job title in a link used to crash the request with an ascii codec error."""
    def test_non_ascii_is_percent_encoded_and_ascii_left_alone(self):
        import _common
        self.assertEqual(_common.ascii_url("https://jobs.example.org.il/p/מפתח?id=1"),
                         "https://jobs.example.org.il/p/%D7%9E%D7%A4%D7%AA%D7%97?id=1")
        same = "https://a.example.com/x%20y?q=a+b&r=1#top"
        self.assertEqual(_common.ascii_url(same), same)

    def test_http_sends_the_encoded_url(self):
        import urllib.request
        import _common
        seen = []
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"{}"
        real = urllib.request.urlopen
        urllib.request.urlopen = lambda req, timeout=0: (seen.append(req.full_url), Reply())[1]
        try:
            _common.http("https://jobs.example.org.il/p/ג׳וניור")
        finally:
            urllib.request.urlopen = real
        self.assertTrue(seen[0].isascii() and "%D7%92" in seen[0])



class BlockedNetwork(unittest.TestCase):
    """A proxy that refuses every site (a Claude cloud session, a work network) ends the run with
    one plain explanation; no command turns it into 'nothing found' or 'check the board name'."""

    def setUp(self):
        # every request, plain or pinned, goes through OpenerDirector.open: no real network is used
        def refuse(*a, **k):
            raise urllib.error.URLError(OSError("Tunnel connection failed: 403 Forbidden"))
        for p in (mock.patch.object(urllib.request.OpenerDirector, "open", refuse),
                  mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"})):
            p.start()
            self.addCleanup(p.stop)

    def test_cloud_session_names_the_local_fix(self):
        with self.assertRaises(_common.NetBlocked) as c:
            jobs.http("https://boards-api.greenhouse.io/v1/boards/acme/jobs")
        self.assertIn("boards-api.greenhouse.io", str(c.exception))
        self.assertIn("'Local'", str(c.exception))
        self.assertIn("Do not ask them to allow sites", str(c.exception))

    def test_other_network_names_the_network(self):
        os.environ.pop("CLAUDE_CODE_REMOTE", None)
        with self.assertRaises(_common.NetBlocked) as c:
            jobs.http("https://api.lever.co/v0/postings/acme")
        self.assertIn("home network", str(c.exception))
        self.assertNotIn("Local", str(c.exception))

    def test_find_does_not_report_no_board(self):
        with self.assertRaises(_common.NetBlocked):
            jobs.find("Some Startup Name")

    def test_fetch_does_not_blame_the_board_name(self):
        with self.assertRaises(_common.NetBlocked):
            jobs.fetch("greenhouse", "acme")

    def test_a_proxy_that_cannot_reach_the_site_is_not_a_block(self):
        def unreachable(*a, **k):
            raise urllib.error.URLError(OSError("Tunnel connection failed: 502 Bad Gateway"))
        with mock.patch.object(urllib.request.OpenerDirector, "open", unreachable), \
                self.assertRaises(jobs.NetError) as c:
            jobs.http("https://api.lever.co/v0/postings/acme")
        self.assertNotIsInstance(c.exception, _common.NetBlocked)

    def test_a_board_404_is_still_an_ordinary_net_error(self):
        def missing(*a, **k):
            raise urllib.error.HTTPError("https://x", 404, "Not Found", {}, io.BytesIO(b"no such board"))
        with mock.patch.object(urllib.request.OpenerDirector, "open", missing), \
                self.assertRaises(jobs.NetError) as c:
            jobs.http("https://boards-api.greenhouse.io/v1/boards/nope/jobs")
        self.assertNotIsInstance(c.exception, _common.NetBlocked)


if __name__ == "__main__":
    unittest.main()

