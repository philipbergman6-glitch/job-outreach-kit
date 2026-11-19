# Job sources

Search the sections `profile/brief.md` → "Job sources" names. Append new sources and dated observations here.

## Anywhere
- **Company job boards, read directly.** For each wish-list company, `python3 scripts/jobs.py detect <careers link>`; a recognised board (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Comeet, Workable, Recruitee, Breezy, Personio, Rippling) is read with `jobs.py list`: posting dates, salary and visa wording, no search spent. Any other careers page: open it in the browser.
- **ATS boards through a search engine**, with the year: `site:job-boards.greenhouse.io "<title>" "<city>"`, likewise `site:jobs.lever.co`, `site:jobs.ashbyhq.com`, `site:comeet.com/jobs`, `site:myworkdayjobs.com`. These return live postings with a known apply path.
- **LinkedIn Jobs.** The richest source of fresh postings, and it lives behind the owner's login.
  - `accounts.py check linkedin search_jobs` says ALLOWED: in their signed-in session (record each search page with `accounts.py record`) open the Jobs search for each target title and location, filter to the past week, and read the result cards and each kept job's description. Also read "Jobs that match your profile". One search at a time, at a human pace.
  - Not allowed: the owner runs the search and pastes the links or the results text; public postings also surface through search engines (`site:linkedin.com/jobs/view "<title>" "<city>"`).
  - Either way, find the same job on the company's own site and apply there when it exists; "Apply on company website" links wrap the real URL in `linkedin.com/safety/go/?url=`.
- **A posting on an aggregator** (Indeed, Glassdoor, Jooble): trace it to the company's own page before applying; aggregators hold expired jobs.

## Israel
- **Comeet-hosted boards**: most Israeli startups. `site:comeet.com/jobs "<title>"`. Any `comeet.com/jobs/<slug>/<uid>/...` link → `jobs.py detect` names the board, and `jobs.py list` reads every opening on it.
- **Jobify360** (`jobify360.co.il`): email-code login, match scores, some in-platform "quick apply" jobs. Login is the owner's. Quick apply in their session only as `profile.json` → `accounts` → `jobify360` allows (`accounts.py record jobify360 apply "<company> <role>"`), shown to them first; otherwise they click it from your checklist.
- **Drushim**, **AllJobs**, **JobMaster**: broad boards; Drushim shows a CAPTCHA on apply → handoff.
- **Company pages of large employers** (banks, defense, telecom, health funds) often require an Israeli ID number on the form → handoff.
- Recruiting and placement agencies repost the same role under their own name: match on the JD text and apply once, to the employer when it is identifiable.

## Europe, UK, North America
- **Welcome to the Jungle / Otta**, **Wellfound** (startups), **Built In** (US cities), **Hacker News "Who is hiring"** monthly thread (tech).
- National boards where the owner is searching: StepStone and arbeitnow (Germany; arbeitnow tags visa sponsorship), Reed and Totaljobs (UK), Indeed and Glassdoor everywhere (trace to the company page), USAJobs (US public sector).
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
