# People discovery (public sources only)

Output: exactly one hiring manager and one recruiter, each at Medium person confidence or better. Stop searching when both reach it.

## Sources

| Source | Gives | Reach it by |
|---|---|---|
| Search-engine snippets of LinkedIn profiles | name, title, company | web search; the workhorse |
| TheOrg | org chart, reporting lines | `theorg.com/org/<company>` |
| Company site | team, about, careers pages | fetch |
| Press, podcasts, conference pages | proof the person is current | web search |
| RocketReach, LeadIQ, ContactOut | name lists, email format | logged-out pages |
| A company's People page, pasted by the owner | the full current staff list | the owner copies it from LinkedIn |
| A profile opened in the owner's signed-in session | current title, confirmed | only when `brief.md` → "LinkedIn" allows profile checks; open the one or two finalists, never a list |
| Hunter | names with positions, addresses | `scripts/hunter.py domain` |

Logged out, LinkedIn returns nothing, and bulk reading of profiles breaks its terms and endangers the owner's account. Keep only a name and a title from any source. Record in `Evidence` which sources confirmed each person.

## A. Hiring manager
Ranking: lead of the team named in the posting > head of that department > VP of the function > founder or C-level (small company only).

1. Pasted People-page text, if given: parse name and title lines, rank, confirm with step 3.
2. Web search, with the year: `site:linkedin.com/in "<Company>" ("Head of" OR VP OR Director OR Lead) (<function words from the JD>)`. A snippet title reads `Name - Title - Company`. Roughly a third of hits are stale; a newer employer in the snippet is a departure signal.
3. Confirm with one non-LinkedIn source: `theorg.com/org/<company>`; interviews, podcasts, conference pages (`"<Name>" "<Company>"`); the company's about or team page. Prefer the newest dated source.
4. The posting names the team, rarely the person: put the team name in the step 2 query.
5. Fallback: the function's VP, or at a small company a founder.

## B. Recruiter
1. Pasted text: titles containing Talent, Recruit, HR, People.
2. Web search: `site:linkedin.com/in "<Company>" (recruiter OR "talent acquisition")` and `"<Company>" "Talent Acquisition" OR "Recruiter" linkedin <year>`.
3. The company's own open recruiting roles sometimes name the talent lead.
4. TheOrg → head of People / HR as last resort.
5. A generic `jobs@` / `careers@` address only when the company site lists it. A company with no recruiter at all → the person who posted the job, or a second leader in the function; say so in `Evidence`.

## C. Email pattern sources
1. Pattern pages, logged out: RocketReach `<company>-email-format`, LeadIQ `email-format`, ContactOut. They disagree with each other; one alone is Low.
2. Public commit author emails on the company's GitHub organisation, where it has one: the best ground truth. Most are `noreply`; look at older commits.
3. `dig +short MX <domain>`: Google Workspace rejects unknown mailboxes, so a Hunter `valid` verdict means something there. An accept-all domain proves nothing until a real send does or does not bounce.
4. Names transliterated from another alphabet have several spellings: prefer the spelling in a source the person controls; ambiguity caps the email at Medium.

## Person confidence
- **High**: name and title in two independent sources, one dated within six months, no departure signal.
- **Medium**: one snippet, or TheOrg "Unverified", or two sources both older than six months.
- **Low**: an aggregator's top-employee list only, a title inferred, or a departure signal. Low → search again or fall back; write only to Medium or better.
