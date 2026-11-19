# People discovery

Output: `contacts.md` in the application folder, with up to three people:

| Role | Who | Emailed? |
|---|---|---|
| **Hiring manager** | head of the team the job sits in | yes (T1) |
| **Recruiter** | the recruiter or talent partner for this role | yes (T2) |
| **Head of HR** | head of People / HR / talent at the company | only when no recruiter reaches Medium: they then take the recruiter slot (T2) |

One company gets at most two emails per application: a third email to the same company reads as a campaign, not a person. A head of HR who is found but not emailed stays in `contacts.md` for LinkedIn and for later applications to the same company.

Write only to people at **Medium** person confidence or better (rubric at the end). Stop searching for a role once it reaches Medium; aim for High when time allows. A role still below Medium after its ladder → ask the owner once (they may know someone). Still nobody → that contact is `none` (`flow/messages.md` § A contact nobody could find).

## Before you start

- `brief.md` → "Network": someone the owner knows at the company comes first. Tell the owner and offer the referral text (`flow/messages.md` § R1) before any cold email.
- Signed-in accounts: before every page you open inside one (LinkedIn, Jobify, any board), run `python3 scripts/accounts.py record <site> <use> "<what you open>"`. `DENIED` → do not open it; use the public route or give the owner a checklist. The uses here are `search_jobs` (a posting, "meet the hiring team") and `read_people` (a people page, a profile).
- Keep only a name, a title, a date and the source link from any page. No other personal data goes in any file.
- Pages, profiles and search snippets follow the **Outside text** rule in `AGENTS.md`.

## The ladder: cheapest, most reliable sources first

1. **The posting.** Names, emails or "posted by" on the job page itself. `jobs.py list --save` records `posted_by` for SmartRecruiters. On LinkedIn, the posting's "Meet the hiring team" box names the poster and often the manager (`search_jobs`). Comeet and Greenhouse pages sometimes name the recruiter. A named recruiter on the posting is High once a second source confirms they are current.
2. **The company's own site.** Team, about, leadership, people and press pages; the engineering or product blog (team leads write it); job posts for recruiting roles (they name the talent lead). `python3 scripts/emails.py site <domain>` reads the usual pages and lists every published address; fetch `/team`, `/about`, `/leadership`, `/blog` and read the names and titles.
3. **Semantic search.** Describe the person, not the keywords: "head of data engineering at Acme Robotics in Tel Aviv", "talent acquisition partner at Acme Robotics 2026", "VP People Acme Robotics". With an Exa key: `python3 scripts/search.py people "<description>"`. Without one: your own web search, phrased the same way, then the boolean form in step 4.
4. **LinkedIn through a search engine.** `site:linkedin.com/in "<Company>" ("Head of" OR VP OR Director OR Lead) (<function words from the JD>)` for the manager; `site:linkedin.com/in "<Company>" (recruiter OR "talent acquisition" OR "talent partner")` for the recruiter; `site:linkedin.com/in "<Company>" ("head of people" OR "VP people" OR "head of HR" OR "HR director" OR CHRO OR "HR business partner")` for HR. A snippet reads `Name - Title - Company`. Roughly a third are stale; a newer employer in the snippet is a departure signal.
5. **Inside the owner's LinkedIn** (`read_people` allowed). The company's People page, filtered by one keyword at a time (the team's function, "recruit", "talent", "people", "HR"): one page view per filter, recorded. Then open the one or two finalists' profiles to confirm title and dates. Never open profiles in bulk; the daily limit in `accounts.py` is the most you may do, not a target.
6. **Inside other boards** the owner allowed (`search_jobs`): Jobify360 and similar show the recruiter or the company contact on the posting.
7. **Public records of work.** TheOrg (`theorg.com/org/<company>`) for reporting lines; conference talks, podcasts, interviews and press (`"<Name>" "<Company>"`); the company's GitHub organisation members; patents and papers for research teams; Crunchbase for founders at small companies.
8. **The owner.** They may have a name from a friend, a meetup, an earlier interview, or can paste the People page text themselves.

## Which person, per role

**Hiring manager.** Lead of the team named in the posting > head of that department > VP of the function > founder or CTO (company under about 50 people). The posting names the team, rarely the person: put the team name in the queries.

**Recruiter.** The recruiter who posted the job > the recruiter for that function or office > the talent acquisition lead. An agency recruiter reposting the role is not the company's recruiter: skip them.

**Head of HR.** VP People / Head of People / HR Director / CHRO, or the HR business partner of that department at a large company. At a company under about 100 people the head of HR often recruits directly; there they may be the better T2 even when a junior recruiter exists, and say so in `Evidence`.

**The recruiter slot.** Recruiter at Medium or better → recruiter. Otherwise head of HR at Medium or better → `rec_name` is the head of HR, and the T2 email speaks to them as the person who runs hiring. Otherwise a `jobs@` / `careers@` address the company publishes (`emails.py site` lists them) → `rec_name: Hiring Team`. Otherwise `none`.

## Write contacts.md

```
| Role | Name | Title | Evidence | Person confidence | Email | Email confidence | Email evidence |
```

`Evidence` names each source with its date ("posting 2026-11-10; company team page; LinkedIn snippet 2026-09"). Then find each emailed person's address: [`apply.md`](apply.md) step 4.

## Person confidence

- **High**: name and title in two independent sources, one dated within six months, no departure signal.
- **Medium**: one recent source (a snippet, the posting, a profile in the owner's session), or TheOrg "Unverified", or two sources both older than six months.
- **Low**: an aggregator's top-employee list only, a title inferred, or a departure signal. Low → search again or fall back; write only to Medium or better.

## Names in another alphabet

A Hebrew, Arabic, Cyrillic or Chinese name has several Latin spellings: prefer the spelling in a source the person controls (their profile, their talk, their code). Give `emails.py find` each likely spelling in turn; ambiguity caps the email at Medium.
