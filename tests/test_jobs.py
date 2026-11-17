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


if __name__ == "__main__":
    unittest.main()
