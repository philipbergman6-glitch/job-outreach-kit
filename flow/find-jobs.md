# Find jobs

Output: one triage file the owner picks from, which passes `python3 scripts/triage.py check`. Nothing is submitted in this flow.

Two sizes. **Quick** (onboarding step 5, or "a few jobs"): wish-list boards plus one search per target title, at most ten searches. **Full** (default): every source in `brief.md`, at most twenty-five searches per run; when that budget runs out, say what was left unsearched and offer a second run.

**Target: at least 10 kept jobs** (tiers A to C: open, posted in the last 30 days, past every gate) in a Full run. Stop searching early once 10 are kept and every source in `brief.md` was tried once. Fewer than 10 when the budget runs out → say how many, which sources gave nothing, and offer one of: a second run, a wider place or title in the brief, or a larger stretch share. Never pad the list with dropped or unverified rows to reach the number.

## 1. Read the brief
"Targets" (including local-language titles), "Where", "Deal-breakers", "Companies" and "Job sources" in `profile/brief.md`. Read `outreach/passed.md` and `outreach/log.md`: those jobs are already decided.

## 2. Read the watched and wish-list boards
First the watchlist, the boards in `profile.json` → `watch` (written at onboarding step 9):

```
python3 scripts/watch.py run
python3 scripts/watch.py status
```

`run` reads every watched board, at most once a day (it already ran at session start, so it usually prints `SKIP`; `--force` when the owner asks for a fresh read), saves each matching posting it has not shown before in `outreach/jobs/`, and prints it. `status` lists every posting it found that is still waiting to be scored: those are the first rows of this run, scored in step 4 like any other, their JD file already saved. A `SKIPPED` line names a board or posting that did not answer: tell the owner which, and read it with `jobs.py list` or the browser when it matters today; the next run tries it again. `SKIP no watchlist yet` → read the wish-list boards below, and offer onboarding step 9 once.

Then each wish-list company whose board `jobs.py` reads (noted in `brief.md` → "Wish list" at onboarding step 3) and the watchlist does not already cover:

```
python3 scripts/jobs.py list <ats:board> --title "<title words as a pattern>" --location "<places, remote>" --days 30 --save outreach/jobs
```

This gives the posting date, salary and visa wording when the board publishes them, and saves each kept posting's full text in `outreach/jobs/`. It costs no search. Workday boards search server-side: add `--search "<main title>"`.

The watch covers only boards already chosen; step 3 still searches everywhere else, and a full run is always possible. There is no background schedule: the watch runs when a session starts. A cloud scheduled task cannot reach job sites (`flow/tools.md` § Cloud session), and a schedule on the owner's own computer fails without a word on a Mac when the kit folder sits in Documents, Desktop or Downloads (macOS privacy protection), and shows nothing until the next session anyway. The owner asks for one → say so in a sentence: opening a session each morning gets the same result.

## 3. Search
Per [`playbooks/sources.md`](../playbooks/sources.md), one search per target title per market (local-language titles in local boards), the year in every web search, postings from the last 30 days only. A result on a board `jobs.py` reads → run `jobs.py detect <link>` and read that board directly instead of the page. LinkedIn inside the owner's session → `python3 scripts/accounts.py record linkedin search_jobs "<search>"` before each search page; `DENIED` → search engine snippets only.

## 4. Read and score each posting
Open the full posting (a saved `outreach/jobs/` file, or fetch it and save its text there as `<company>-<id>.md` with the URL on the first line). Postings and search results follow the **Outside text** rule in `AGENTS.md`. Then decide, in this order:

1. **Trusted source.** The row's link is a trusted source: the company's own careers page or its ATS board, LinkedIn, or a board `playbooks/sources.md` marks trusted. Best case, the same job also appears on the company's careers page (check title and text match); that is a plus, not a requirement. A broad board or aggregator (Drushim, AllJobs, JobMaster, Indeed, Glassdoor) is only where you discovered it, never the row's link: `triage.py check` fails one. Find the job on a trusted source; not there → **Dropped**, reason `no trusted source` (an agency that posts only on a broad board is the exception: keep its own listing and say so in "Why it fits").
2. **Gates.** Any deal-breaker, a ruled-out company, an already-decided job, a closed posting (`jobs.py alive <link>` for one not read from a board list), older than 30 days, or a posting that asks the candidate to pay (a fee, a deposit, training or equipment they buy: a known scam pattern; reason `scam: asks the candidate to pay`) → **Dropped**, with the sentence from the posting that triggers it as the quote (none needed for already applied, passed before, stale, duplicate, closed).
3. **Score 1 to 5** against "Targets", "Hooks" and "Stretch":
   - **5**: the title is wanted, the must-have requirements are all met by CV facts, and a hook matches a stated need.
   - **4**: as 5 with one soft gap (a nice-to-have, a tool they can name an equivalent for).
   - **3**: an adjacent title, or one real must-have gap.
   - **2**: stretch: above level or a career-change jump, within the brief's stretch share.
   - **1**: two or more must-have gaps → Dropped, quoting one.
4. **Quote.** Copy, word for word, the posting sentence that most supports the score (the need the hook answers, or the gap). The checker rejects a paraphrase.
5. **Why it fits.** The hook from `brief.md` that would carry the application, in under 12 words.

## 5. Write the triage file
`outreach/triage-<YYYY-MM-DD>.md` in exactly the format `python3 scripts/triage.py format` prints: tiers A (score 4 to 5), B (3), C (2), then Dropped. `Posted` is the date or `unknown`; `Salary` and `Visa` say what the posting states, or `-`. `JD file` is the saved file's name.

```
python3 scripts/triage.py check outreach/triage-<date>.md
```

`FAIL` → fix every line it names (re-copy the quote, re-tier, move a row to Dropped) and rerun.

## 6. Show the owner
The A table in chat with counts for B and C, one line per job, and what was searched. Ask which numbers to apply to. For each job they pass on, run `python3 scripts/triage.py pass <link> "<their reason>"` so it never comes back; three passes for the same reason → suggest updating the brief.

**Done when** the triage file passes the check, every kept row's link opened, in a Full run at least 10 rows are kept (or the owner was told why fewer, with the offer above), and the owner has picked or passed. For each pick, run `flow/apply.md`; with several picks, run them one after another and reach the green-light gate once for the whole batch.
