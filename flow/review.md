# Review: what is working

Run when the owner asks "how is it going?", after every fifth reply or rejection, and at least once a week while applications are going out. Output: a short report in chat and the changes the owner agrees to, written into `brief.md` / `profile.json`.

## 1. Count
`python3 scripts/tracker.py build`, then from `outreach/log.md` and `outreach/replies.md`:

| Measure | How |
|---|---|
| Applications | rows in log.md with Status submitted, sent or closed |
| Answered by a person | replies.md `Got back?` = Yes, by anyone other than an auto-acknowledgement |
| Interviews / offers | replies.md `Outcome` |
| Rejections | `Outcome` = Rejected |
| Silent after 14 days | applied 14 or more days ago, nothing back |

Split each count by tier (A/B/C from the triage files), by hook (`messages.md` front matter), by apply channel, and by whether an email reached a person (Emails = a date) or only the form went in. Small numbers: say "too few to tell" below five in a group rather than drawing a conclusion.

## 2. Fit: does the shortlist hold what the owner wants?
`python3 scripts/fit.py report`. It reads the verdicts the owner gave while reviewing lists ([`find-jobs.md`](find-jobs.md) step 6) against where the kit put each job. "no labels yet" → skip this section and ask for verdicts on the next list. Under 10 labels it says too few to tell: read its rows, draw nothing from its shares.

- **Top 10 share**: of each list's first ten jobs the owner labelled, how many they would apply to. Under half → the score is off for this owner: read their skip reasons below before anything else.
- **Deal-breaker leak** (skip, for a reason that alone rules the job out, yet tiered A or B): the brief lacks the rule. Propose the line in the section the report names: words a posting would carry ("commission only", "fixed-term") under "Deal-breakers" → "Phrases that end it", each in double quotes; a title under "Targets" → "Titles to skip"; a company or industry under "Companies" → "Ruled out"; a place under "Where". `triage.py check` enforces the first two on every later list; the others guide the score.
- **Miss** (apply, yet tiered C, dropped or never found). Tier C → the score called something a gap that is not one to this owner: add the title to "Titles close enough", or the hook that would carry it. Dropped → read its reason: a title or phrase gate that fired on a job they want → narrow that brief line. Never found → the search lacks a title, a place or a source: add it to "Targets", "Where" or "Job sources".
- **Reasons**: a reason given three or more times points at the first change to propose, in the section the report names beside it.

Each change quotes the owner's own reason from the report. The kit's tests (`tests/fixtures/fit`) check the gates on a fictional persona; only these labels check the score.

## 3. Diagnose
Name the most likely bottleneck, from the earliest stage that fails:

- **Silence on most applications** (fewer than one in ten answered after 15 or more): targeting or the CV. Check the share of B and C tier, whether the CV survives a reading against three of the silent postings (onboarding step 6, item 4), and whether emails reached people (Low-confidence contacts mean the form alone went in).
- **Answers but no interviews**: the first screen. Reread the rejections for stated reasons; compare the CV's top third with what those postings put first.
- **Interviews but no offers**: interview prep. Offer `flow/interview-prep.md` mock rounds on the stages that failed.
- **Leaks or misses in the fit report**: targeting. The § 2 changes come first: every later list is built on them.
- **One hook or one tier doing all the work**: lean on it; stop the one that never gets answers.
- **Bounces**: the email step. Count bounces per method (pattern only vs a finder vs the mail-server check) from `contacts.md` and prefer what held.

State it as a hypothesis with its evidence, and name one alternative explanation.

## 4. Agree the changes
Propose at most three changes, each small and testable over the next ten applications (raise the A share, swap a hook, edit the CV's opening, change the subject line, widen a location, a deal-breaker phrase or title to skip from the fit report). The owner decides. Write each accepted change, dated, into `brief.md` → the section it changes, and note it under a "Changes" heading in `profile/onboarding.md` so the next review can compare before and after (for a fit change: the next `fit.py report` once ten more jobs are labelled).

**Done when** the owner has the numbers, the diagnosis and the agreed changes, and the changes are written down.
