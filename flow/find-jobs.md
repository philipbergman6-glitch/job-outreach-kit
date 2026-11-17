# Find jobs

Output: one triage file the owner picks from, which passes `python3 scripts/triage.py check`. Nothing is submitted in this flow.

Two sizes. **Quick** (onboarding step 5, or "a few jobs"): wish-list boards plus one search per target title, at most ten searches. **Full** (default): every source in `brief.md`, at most twenty-five searches per run; when that budget runs out, say what was left unsearched and offer a second run.

## 1. Read the brief
"Targets" (including local-language titles), "Where", "Deal-breakers", "Companies" and "Job sources" in `profile/brief.md`. Read `outreach/passed.md` and `outreach/log.md`: those jobs are already decided.

## 2. Read the wish-list boards directly
For each wish-list company whose board `jobs.py` reads (noted in `brief.md` at onboarding):

```
python3 scripts/jobs.py list <ats:board> --title "<title words as a pattern>" --location "<places, remote>" --days 30 --save outreach/jobs
```

This gives the posting date, salary and visa wording when the board publishes them, and saves each kept posting's full text in `outreach/jobs/`. It costs no search. Workday boards search server-side: add `--search "<main title>"`.

## 3. Search
Per [`playbooks/sources.md`](../playbooks/sources.md), one search per target title per market (local-language titles in local boards), the year in every web search, postings from the last 30 days only. A result on a board `jobs.py` reads → run `jobs.py detect <link>` and read that board directly instead of the page. LinkedIn inside the owner's session → `python3 scripts/accounts.py record linkedin search_jobs "<search>"` before each search page; `DENIED` → search engine snippets only.

## 4. Read and score each posting
Open the full posting (a saved `outreach/jobs/` file, or fetch it and save its text there as `<company>-<id>.md` with the URL on the first line). Then decide, in this order:

1. **Gates.** Any deal-breaker, a ruled-out company, an already-decided job, a closed posting, older than 30 days → **Dropped**, with the sentence from the posting that triggers it as the quote (none needed for already applied, passed before, stale, duplicate, closed).
2. **Score 1 to 5** against "Targets", "Hooks" and "Stretch":
   - **5**: the title is wanted, the must-have requirements are all met by CV facts, and a hook matches a stated need.
   - **4**: as 5 with one soft gap (a nice-to-have, a tool they can name an equivalent for).
   - **3**: an adjacent title, or one real must-have gap.
   - **2**: stretch: above level or a career-change jump, within the brief's stretch share.
   - **1**: two or more must-have gaps → Dropped, quoting one.
3. **Quote.** Copy, word for word, the posting sentence that most supports the score (the need the hook answers, or the gap). The checker rejects a paraphrase.
4. **Why it fits.** The hook from `brief.md` that would carry the application, in under 12 words.

## 5. Write the triage file
`outreach/triage-<YYYY-MM-DD>.md` in exactly the format `python3 scripts/triage.py format` prints: tiers A (score 4 to 5), B (3), C (2), then Dropped. `Posted` is the date or `unknown`; `Salary` and `Visa` say what the posting states, or `-`. `JD file` is the saved file's name.

```
python3 scripts/triage.py check outreach/triage-<date>.md
```

`FAIL` → fix every line it names (re-copy the quote, re-tier, move a row to Dropped) and rerun.

## 6. Show the owner
The A table in chat with counts for B and C, one line per job, and what was searched. Ask which numbers to apply to. For each job they pass on, run `python3 scripts/triage.py pass <link> "<their reason>"` so it never comes back; three passes for the same reason → suggest updating the brief.

**Done when** the triage file passes the check, every kept row's link opened, and the owner has picked or passed. For each pick, run `flow/apply.md`; with several picks, run them one after another and reach the green-light gate once for the whole batch.
