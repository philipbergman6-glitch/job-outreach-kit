# Find jobs

Output: one triage file the owner picks from. Nothing is submitted in this flow.

1. Read "Targets", "Deal-breakers" and "Job sources" in `profile/brief.md`.
2. Search every listed source, per [`playbooks/sources.md`](../playbooks/sources.md), for each target title in each target location. Include the current year in web searches and keep only postings from the last 30 days.
3. For each posting open the job description and read it. Drop it when it breaks a deal-breaker, when the company is on the ruled-out list, when the company already has a row in `outreach/log.md` for that role, or when an earlier `outreach/triage-*.md` listed it and the owner passed.
4. Write `outreach/triage-<YYYY-MM-DD>.md`:

```
# Triage <date>: <sources searched>, <N> postings read, <M> kept
Dropped: <count by reason>

## A: direct fit
| # | Company | Role | Location | Source | Apply path | Link | Why it fits |
## B: adjacent title or one gap
## C: stretch
```

`Apply path` = the ATS name if recognisable from the link, else `company site`, `easy apply`, or `?`. `Why it fits` names the hook from `brief.md` that would carry the application, in under 12 words.

5. Show the owner the A table in chat, with counts for B and C, and ask which numbers to apply to.

**Done when** every source in `brief.md` was searched for every target title, every kept row has a link that opened, and the owner has picked or passed. For each pick, run `flow/apply.md`; with several picks, run them one after another and reach the green-light gate once for the whole batch.
