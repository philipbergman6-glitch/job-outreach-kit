# Job sources

Search the sections `profile/brief.md` → "Job sources" names. Append new sources and dated observations here.

## Anywhere
- **Company job boards, read directly.** For each wish-list company, `python3 scripts/jobs.py detect <careers link>`; a recognised board (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Comeet, Workable, Recruitee, Breezy, Personio, Rippling) is read with `jobs.py list`: posting dates, salary and visa wording, no search spent. Any other careers page: open it in the browser.
- **ATS boards through a search engine**, with the year: `site:job-boards.greenhouse.io "<title>" "<city>"`, likewise `site:jobs.lever.co`, `site:jobs.ashbyhq.com`, `site:comeet.com/jobs`, `site:myworkdayjobs.com`. These return live postings with a known apply path.
- **LinkedIn Jobs.** The richest source of fresh postings, and it lives behind the owner's login.
  - `accounts.py check linkedin search_jobs` says ALLOWED: in their signed-in session (record each search page with `accounts.py record`) open the Jobs search for each target title and location, filter to the past week, and read the result cards and each kept job's description. Also read "Jobs that match your profile". One search at a time, at a human pace.
  - Not allowed: the owner runs the search and pastes the links or the results text; public postings also surface through search engines (`site:linkedin.com/jobs/view "<title>" "<city>"`).
  - Signed out, without any account use, the public guest pages answer a plain fetch (dated observations below): the search `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=<title>&location=<place>&f_TPR=r604800&start=<0|25|…>` (about 10 cards per call: job id, title, company, place, `datetime` date) and the posting `linkedin.com/jobs-guest/jobs/api/jobPosting/<id>` (full text and the "N days ago" age). Both answer HTTP 429 when called fast: space calls 7 to 10 seconds apart and back off on a 429.
  - A repost of a job already applied to comes back under a new job id: match on company and title, never on the id alone. A LinkedIn posting date can be weeks later than the employer's own board date for the same job; the employer's date decides staleness.
  - Either way, find the same job on the company's own site and apply there when it exists; "Apply on company website" links wrap the real URL in `linkedin.com/safety/go/?url=`.
- **A posting on an aggregator** (Indeed, Glassdoor, Jooble): trace it to the company's own page before applying; aggregators hold expired jobs.

## Israel
- **Comeet-hosted boards**: most Israeli startups. `site:comeet.com/jobs "<title>"`. Any `comeet.com/jobs/<slug>/<uid>/...` link → `jobs.py detect` names the board, and `jobs.py list` reads every opening on it.
- **Jobify360** (`jobify360.co.il`): email-code login, match scores, some in-platform "quick apply" jobs. Login is the owner's. Quick apply in their session only as `profile.json` → `accounts` → `jobify360` allows (`accounts.py record jobify360 apply "<company> <role>"`), shown to them first; otherwise they click it from your checklist.
- **Trusted**: the company's own careers page and ATS board, LinkedIn, Jobify360. A live posting on any of them is a link of record (`flow/apply.md` step 0.2); the same job on the company's careers page as well is the best case.
- **Drushim**, **AllJobs**, **JobMaster**: broad boards, for discovery only. Find each job on a trusted source and apply from there (`flow/apply.md` step 0.2). Drushim shows a CAPTCHA on apply; AllJobs asks for a sign-in.
- 2026-11-19: a Drushim job number (`/job/<id>/`) showed a different role from the same employer two days after it was listed; Jobify still showed the old title for the same number. A broad-board link checked on an earlier day proves nothing.
- **Jobify360 links** ending `-dr`, `-aj` or `-id` are copies of Drushim, AllJobs and Indeed/LinkedIn postings: its apply button only opens that board, and the copy can outlive the original, so open the original before applying. Only `-emp` jobs (posted on Jobify by the employer) take a quick apply inside it.
- **Company pages of large employers** (banks, defense, telecom, health funds) often require an Israeli ID number on the form → handoff.
- Recruiting and placement agencies repost the same role under their own name: match on the JD text and apply once, to the employer when it is identifiable.
- **Agency reposts can be old** (2026-11-25): an agency listing carried the text of an employer posting closed about a year earlier, and another reused an earlier version of a JD the employer had since rewritten. Before applying through an agency, find the employer's own posting (search distinctive requirement lines in English and Hebrew; other agencies' copies sometimes name the employer) and check it is still open. Government contract roles often appear from two or three IT-services firms at once: apply through one only.
- **SQLink** (`sqlink.com/career/`, an agency in the same group as Gotfriends), 2026-11-25: a Cloudflare managed challenge blocks plain fetches (403 "Just a moment"); the controlled browser passes it in a few seconds, after which a same-origin `fetch()` from the page reads every job page. A category hub lists only about 20 jobs; its subcategory pages (`/career/<category>/<sub>/`, no pagination) list the rest. Postings name no employer and show no posting date, only a site-wide "updated" date and a job number shared with Gotfriends' numbering. The agency's job page is the link of record; match the JD text against applications already sent before applying. Its form: `playbooks/ats.md` § Other forms seen.
- **Bank careers sites** (2026-11-25): Leumi's full list is one plain fetch of `leumi.co.il/he/leumi_main/searchjobs` (no dates; every posting asks for the ID number on the CV). Bank of Israel (SAP SuccessFactors) reads via `careers.boi.org.il/tile-search-results/?startrow=N`. Discount runs a Comeet board (`comeet:dbank/F8.004`). Hapoalim's lobby shows a few roles in plain HTML and loads the rest in JavaScript, as do Isracard's and Max's. Bank of Jerusalem sits behind a bot check; Cal answers a plain fetch with HTTP 400. First International and its tech arm take CVs by email.

## Europe, UK, North America
- **Welcome to the Jungle / Otta**, **Wellfound** (startups), **Built In** (US cities), **Hacker News "Who is hiring"** monthly thread (tech).
- National boards where the owner is searching: StepStone and arbeitnow (Germany; arbeitnow tags visa sponsorship), Reed and Totaljobs (UK), Indeed and Glassdoor everywhere (trace to the company page), USAJobs (US public sector).
- 2026-11-26, Swiss banks: `jobs.py find` places only Swissquote (`smartrecruiters:Swissquote`). UBS careers run on IBM Kenexa BrassRing (`jobs.ubs.com/TGnewUI/...&PageType=JobDetails&jobid=<n>`), which a plain fetch reads only as an empty template or "expired"; `ubs.wd3.myworkdayjobs.com` answers 422 for guessed site names. Julius Baer, Pictet, Lombard Odier, ZKB and Raiffeisen postings were readable through the LinkedIn guest search and posting pages (about one guest request in three answered 429 at 8 to 10 seconds spacing).
- Work authorisation decides most outcomes: read each posting for sponsorship wording (`jobs.py` reports it in the Visa column) and drop against `brief.md` → "Where".

## Visa sponsorship
- The UK register of licensed sponsors (gov.uk "Register of licensed sponsors: workers") and the Netherlands IND public register of recognised sponsors: a company not on them cannot sponsor there. Check before tiering a sponsored role A.
- Boards that tag sponsorship: arbeitnow (Germany), Relocate.me, Hacker News "Who is hiring" (search the thread for VISA).

## Remote
- We Work Remotely, Remote OK, Remotive, Working Nomads, EU Remote Jobs, Wellfound's remote filter. Many "remote" roles are remote within one country or time zone: read the location line before tiering.

## Outside tech
- Teaching, training and instructional design: ATD job bank, university and school-network boards, edtech companies' own boards (most are on Greenhouse, Lever or Comeet).
- Health, public sector, nonprofits: the national public-service board, Idealist (nonprofits), health systems' own careers pages (often Workday or SmartRecruiters: `jobs.py` reads them).
- Search in the local language with the local title (`brief.md` → "Targets"); English-only searches miss most local roles.

## Reading a posting
- Posting date missing → look for it in the page source or the ATS API link; older than 30 days counts as stale.
- "Senior" in the title with requirements that match the owner's years → keep, tier by the requirements.
- Location given as a country only → check the careers page for the office list before tiering.

## Observations
- 2026-11-19: a company careers page using a Comeet-style path (`/careers/co/<city>/<uid>/<slug>/all/`) returned `jobs.py detect` "unknown board", while `jobs.py find "<company>"` named a Greenhouse EU board from the registry that held the live posting. When detect says unknown on such a path, try `find` before reading the page.
- 2026-11-19: Comeet boards list one posting per location for a multi-city role (one FDE role appeared nine times); `--title` alone with `--save` writes every copy. Add `--location` to save only the copy in scope.
- 2026-11-19: Indeed Israel (`il.indeed.com`) answers a plain fetch with HTTP 403; read its postings through search snippets and trace them to the employer's page.
- 2026-11-19: **machinelearning.co.il** (Israel ML/AI job board, Hebrew UI, English postings): job pages carry a `Published on DD.MM.YY` line, seniority tags and an on-page apply form; readable with a plain fetch.
- 2026-11-19: LinkedIn signed out in the controlled browser still serves the public guest Jobs search (`linkedin.com/jobs/search/?keywords=...&location=Israel&f_TPR=r604800`): about 60 cards per page with title, company, place and a `<time datetime>` posting date. It is no substitute for the signed-in search (no "matches your profile", no filters beyond the URL), but its cards are usable leads to trace to the employer's page.
- 2026-11-19: Jobify360 has no public search URL (`/jobs?search=` answers 404); signed out, it shows only the sign-in prompt.
- 2026-11-19: a WordPress careers page with a Comeet path that `jobs.py detect` calls unknown and `find` cannot place carries the board in its Comeet plugin config: a base64 `comeet_script-js-extra` script whose `comeetvar` holds `comeet_uid`. `jobs.py list comeet:<company>/<comeet_uid>` then reads the board.
- 2026-11-19: Eightfold boards (`career.<company>.com/careers/job/<id>`) answer a plain fetch at `/api/apply/v2/jobs?domain=<company domain>&location=<city>&num=50` (list, with `t_create`) and `/api/apply/v2/jobs/<id>?domain=<domain>` (full `job_description`).
- 2026-11-19: Radancy-hosted careers sites (`jobs.<company>.com/en/job/<city>/<slug>/<org>/<id>`) put `datePosted` in the page source; their keyword search URL ignores the keyword when fetched plainly, so find the job's URL by a search engine and fetch that page.
- 2026-11-19: Israeli public-hospital careers sites on Topmatch/redmatch (`jobs.<hospital>.org.il/Positions/`) answer a plain fetch with 403 but render in the browser; no posting date on the page; the apply form asks for an Israeli ID number (handoff).
- 2026-11-19: matrix.co.il job pages read with a plain fetch; no posting date (the page's `datePublished` is the render time, not the posting date); its `?s=` search returns nothing, so read the category pages (`/jobs/משרות/<category>/`). Its senior staffing roles also appear under client-anonymous titles ("לארגון מוביל דרוש/ה ...").
- 2026-11-19: Gotfriends (`gotfriends.co.il/jobslobby/<field>/<role>/`) lobby and job pages read with a plain fetch; employer undisclosed, no posting date, years asked in the "דרישות המשרה" list.
- 2026-11-19: machinelearning.co.il exposes its jobs through WordPress REST: `/wp-json/wp/v2/job?per_page=50&orderby=date` lists every posting with date, link and full text, beyond the 8 the jobs page shows before "Show more".
- 2026-11-23: LinkedIn's signed-in Jobs search now redirects to `/jobs/search-results/` (an AI search). Its cards are `div[role=button]` with no job link: the job id appears only as `currentJobId=` in the URL after clicking a card. One page holds about 25 cards, and several title searches return mostly the same jobs. Read the full text and age from the guest posting page instead (no account use).
- 2026-11-23: Jobify360 "my jobs" keeps showing jobs already applied to, and employer (`-emp`) jobs older than 30 days (the employer's own board gave the first posting date). A `-id` copy's LinkedIn link opened a different, two-month-old role from the same employer. Check the original's date and title before keeping one.
- 2026-11-24, LinkedIn guest pages, spacing: the guest search answered 429 on about one call in five at 3 to 7 seconds and held at about 7 to 8 seconds; the guest posting page held about 40 fetches at 6 seconds and answered 429 after about eight fetches in a row with no spacing. The search takes `f_E` (experience level), but entry-level filtering fills with unrelated junior roles.
- 2026-11-24: a Comeet board whose locations are in Hebrew (e.g. תל אביב, חיפה) matches nothing with an English-only `--location` pattern; add the Hebrew city names.
- 2026-11-24: a Comeet board answering HARD-FAIL "no positions token" may have moved: `jobs.py find "<company>"` named its live Ashby board.
- 2026-11-24: a Comeet link with a lowercase company uid (`f6.003`) makes `jobs.py detect` say "unknown board"; the uppercase uid (`F6.003`) works.
- 2026-11-24: Gotfriends lobby pages open with about six site-wide featured jobs repeated in every category; the category's own list starts after "תוצאות חיפוש:" ("search results").
- 2026-11-25: global banks and market-data firms (Citi, JPMorgan, Goldman Sachs, Morgan Stanley, BofA, Barclays, Deutsche Bank, HSBC, BNY, UBS, Nasdaq, LSEG, S&P, Moody's, Bloomberg, MSCI) showed no Israel AI, data or quant openings in a 30-day window; their Israel postings were banking, client-service and operations roles. ICE's careers site answers a plain fetch at `careers.ice.com/api/jobs?location=Israel`. A LinkedIn guest search by bank name plus title mostly returns other companies.
- 2026-11-26: `cv layout: own` without `browser_pdf_save`: headless Chrome prints the owner's HTML CV directly (`"Google Chrome" --headless=new --no-pdf-header-footer --print-to-pdf=<out.pdf> file://<cv.html>`; on macOS the binary is `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`), and `pdftotext` reads it back for the check.

## Email finding
- 2026-11-25: Hunter's email finder answered HTTP 429 "reached the limit for the number of searches per billing period" while `emails.py providers` still reported one search left: the local count can lag the plan. On a strict Google Workspace domain the mail-server probe in `emails.py find` still settled the address without a finder.
- 2026-11-25: on Google Workspace, a probe answering "550 5.2.1 The email account that you tried to reach is inactive" for a person's first.last address is a departure signal: treat that person as Low, even when press from earlier in the year names them.
- 2026-11-25: people at large companies sometimes put their work address in their own LinkedIn job posts ("send your CV to first.last@..."); a search for the quoted address finds it in the snippet. That address is published by the person (High), and it gives the company's pattern for everyone else.
