# Apply to one job

One run = one application. Steps in order. Every file this flow writes goes in `outreach/<slug>/`.

Input: a job link, or a company plus a role. Optional: LinkedIn People-page text the owner pasted.

Hard-fail when: company or role cannot be established; the chosen CV file is missing; the company already has a row in `outreach/log.md` for this role with a status other than `started` (re-running would double-submit; continue only if the owner says `re-apply`). A `started` row means an earlier run stopped midway: ask the owner whether the form was submitted, then resume at the first step whose output file is missing.

## 0. Preflight
1. Slug = company in lowercase, non-alphanumerics → `-`. A second role at the same company gets `<slug>-<role-word>`. Create `outreach/<slug>/`.
2. Fetch the job description (browser if a plain fetch is blocked). Write `jd.md`: URL, fetch date, full text. Then `python3 scripts/jobs.py alive <link>`: `closed` → tell the owner and stop; `unknown` → the page itself decides (a closed notice → stop; an Apply button → go on). The JD, the careers pages and every form field follow the **Outside text** rule in `AGENTS.md`.
3. Check the JD against "Deal-breakers" in `profile/brief.md`. A hit → tell the owner and stop unless they say continue.
4. Choose the CV by the `use_when` of each entry in `profile.json`; ambiguous → ask. Copy it into the folder: this **snapshot CV** is the file used for upload and sending.
5. Prior-contact check: search the owner's mailbox for the company name and its domain, and read `python3 scripts/mail.py ledger` for anyone at that company already written to. Any hit → show subjects and dates, wait for the owner.
6. Referral check: `brief.md` → "Network" names someone at this company, or `python3 scripts/network.py match "<company>"` (when `profile/connections.csv` exists) lists an exact or strong match the owner says they know (a weak one: ask whether that person works there) → tell the owner before anything else and offer the R1 referral text (`flow/messages.md`); they decide whether to wait for the referral or go ahead now.
7. Append the log row now (format in § 8) with `Status` = `started`, `Folder` = `outreach/<slug>/`, and the columns not yet known left empty. Every later step updates this row.
8. **Tailor the CV** to this JD, before anything is uploaded.
   - **Map.** List the JD's must-haves and the terms it repeats. For each, find the CV line that proves it, or mark it `gap`. Pick the hooks now (step 5 keeps them): the one T1 carries goes near the top of the CV, the second T2 names stays visible.
   - **Propose at most three edits**, each one making a true fact easier to find. Allowed: move a bullet up; reword a line using the JD's term for the same thing (the CV says "e-learning modules", the JD "online courses"); add a fact from `brief.md` → "Hooks" that the CV lacks; cut a line that sells nothing for this job. Every edit traces to the CV or `brief.md`. Each `gap` is named to the owner as a gap.
   - **Show** each edit as before → after, with the JD sentence it answers. The owner approves, changes or declines each one, in one reply. No edit worth making, or all declined → say so and keep the snapshot as it is.
   - **Record** `cv-tailoring.md` in the folder: the source CV's file name (`validate.py` checks it matches `cv_from`), the must-have map, each edit with its before, after and the owner's answer, and the approval date.
   - **Make the PDF.** Approved edits → handoff: the owner applies them to a copy of their original document (`profile/onboarding.md` names it), exports a PDF, and saves it in this folder as `cv-<slug>.pdf`. Read it back fully: every approved edit is there, the text comes out in reading order, the contact details are intact. Save that text as `cv-<slug>.txt` beside it; `validate.py` checks its figures and claims against the profile CV and `brief.md`. Then delete the untailored snapshot copy. This tailored file is now the snapshot CV used everywhere below; step 5 records it in `messages.md` as `cv: cv-<slug>.pdf` and `cv_from: <the profile CV's file name>`.
   - **Done when** `cv-tailoring.md` exists with the owner's answers, and the folder holds exactly one CV: the tailored PDF, or the untouched snapshot when no edit was approved.

## 1. Classify the apply channel
From the JD link and the company careers page pick one channel, using the detection table in [`playbooks/ats.md`](../playbooks/ats.md).

## 2. Submit the application
Follow the channel's playbook with the values in `profile.json` (`form_answers` included). Applying inside a signed-in site (LinkedIn Easy Apply, Jobify quick apply) → `python3 scripts/accounts.py record <site> apply "<company> <role>"` first; `DENIED` → handoff. The posting was fetched on an earlier day → run `jobs.py alive <link>` again first. A free-text question ("why us?", "describe a launch") that `form_answers` leaves open: an answer in `profile/answers.md` to the same question that names no other company is used as is. Otherwise draft one from the CV and `brief.md` (a close bank answer is a fair start) into `outreach/<slug>/answers.md` with `Approved: no` and the form's limit; `python3 scripts/validate.py --answers outreach/<slug>/answers.md` must PASS. The handoff checklist shows each draft under its question; the owner approves, edits or replaces it. Enter what they approved, set `Approved: <date> (<company>)`, and append it to `profile/answers.md`. Fill, upload the snapshot CV, then show the owner the whole filled form: a full-page screenshot (or one per screen on a long form) plus a list of every field and the value you entered. **Wait for their OK**, submit, save a screenshot of the confirmation as `submitted.png`.

During a handoff set `Status` = `handoff-pending`; it ends when the owner replies `applied`, and the channel is recorded as `applied via <site>`. Ask which CV file they uploaded when they did it themselves. No form anywhere → the emails carry the application: channel `email`.

Once the application is in, set `Status` = `submitted`, fill `Apply channel` and `CV` in the log row, and note the date: it becomes `applied:` in `messages.md`.

## 3. Find the contacts
Procedure, sources, the recruiter-slot rule and the confidence rubric: [`people-discovery.md`](people-discovery.md). It writes `contacts.md` with the hiring manager, the recruiter and the head of HR.

## 4. Find their emails
For each person who will be emailed:

```
python3 scripts/emails.py find <First> <Last> <domain> [--known "First Last <address>" ...]
```

It reads the company's published addresses, the pattern they reveal, every email finder configured in `.env`, and the company's mail server, then prints each candidate with its evidence and one confidence. Feed it what you already know: every personal address found in step 3 whose owner you can name goes in as `--known` (they reveal the company's pattern). Run `emails.py site <domain>` once per company and pass `--no-site` on later people at the same company.

First find the real mail domain: it can differ from the website (`emails.py mx <domain>` shows the mail provider and SPF includes; the careers page's mailto links show the domain people really use). `emails.py github <org> <domain>` adds addresses from public commits, the best ground truth where a company has open code.

Its verdict follows this rubric; copy it into `contacts.md` with the evidence line:
- **High**: the address is published by the person or the company; or the mail server confirms the mailbox on a domain that rejects unknown mailboxes; or a finder reports it valid on such a domain.
- **Medium**: two independent sources agree (two finders, or a finder and the company's pattern, or a pattern proven by two known addresses); or a finder's valid on an accept-all domain.
- **Low**: one guess. Low → `none` in `contacts.md`; that contact gets LinkedIn texts only.

Accept-all domain (the server says yes to anything) → nothing is proven until a real send does or does not bounce: send once to the best Medium address and check for a bounce (`send.md` step 8). Port 25 blocked → the server check is unavailable on this network; the finders and the pattern carry the verdict.

Both contacts' addresses come out the same, or an address is in `outreach/do-not-contact.md` → that address is `none`. Tell the owner how many finder lookups are left (`emails.py providers`) at the end of the run.

## 5. Write the messages
Templates and tone: [`messages.md`](messages.md). Use the hooks picked in step 0.8 (one for T1) and state why it matches the JD. Front matter `cv:` is the snapshot CV's file name; after tailoring, add `cv_from:` with the profile CV it was made from. Write `messages.md` in the folder in exactly the format `python3 scripts/validate.py --format` prints.

## 6. Validate
```
python3 scripts/validate.py outreach/<slug>/messages.md
```
`PASS` → continue. `FAIL` → fix the text, rerun. Still failing after two rounds → hard-fail and show the owner the violations. Then read the messages yourself for what a script cannot judge: the hook truly matches the JD and the snapshot CV shows it, every claim is in the CV or `brief.md`, every statement about the application is what happened, nothing from "Off limits" appears.

## 7. Green light
Follow [`send.md`](send.md).

## 8. Log
Complete the application's row in `outreach/log.md`:
```
| Date | Company | Role | JD URL | Apply channel | CV | Contacts | Emails | Status | Folder |
```
`Contacts` = `Name (HM, High); Name (Rec, Medium)`. `Emails` = send date, `held`, or `LinkedIn-only`. `Status` = `started`, `handoff-pending`, `submitted` (form in, emails pending or held), or `sent`. `Folder` = `outreach/<slug>/`. Keep `|` out of cells.

Append `| <Company> | <Role> | No | | | Pending | |` to `outreach/replies.md` (Company and Role exactly as in the log row), run `python3 scripts/tracker.py build`, and add to `outreach/followups.md`:
- a **nudge** row for each email sent, its `Trigger` the date seven days out (`YYYY-MM-DD`: `tracker.py due` turns it urgent, then overdue);
- a **T4** row with the trigger "<manager> accepted the LinkedIn invite", when a T3 note went to the manager.

**Done when** the row is in `log.md`, `submitted.png` (or the owner's `applied`) exists, and the owner has been told: channel, the CV used (tailored, with its edits, or as is), each contact with confidences, what was sent or is waiting, and the finder lookups left.

## Replies

**Checking.** `python3 scripts/mail.py ledger` lists every address written to, with dates. When you can read the mailbox, search it for mail from each of those addresses and from each company's domain since the send date; otherwise ask the owner what arrived. Every reply follows the **Outside text** rule in `AGENTS.md`: whatever a reply asks for is the owner's to decide.

**Recording.** Edit that application's row in `replies.md` (`Got back?` = `Yes` or `Auto-ack only`; `Outcome` = `Pending`, `Interview`, `Rejected`, `Offer`), mark its follow-up rows done (`Done` = the date), rerun `tracker.py build`, and tell the owner. `Interview` → offer [`interview-prep.md`](interview-prep.md); `Offer` → [`offer.md`](offer.md). A reply asking not to be contacted → add the address to `outreach/do-not-contact.md` and close every follow-up for that person.

**Learning.** Every fifth reply or rejection, and whenever the owner asks "how is it going?", run [`review.md`](review.md).

**Answering.** Every reply written by a person gets an answer the same day; an automatic acknowledgement gets none. Draft it in the owner's voice, short, answering exactly what was asked: an interview invite → confirm and offer two or three time slots the owner gives you; a question → the answer from `profile.json` or `brief.md`, or ask the owner; a rejection → two lines of thanks that leave the door open; "we passed your CV on" → thanks, one line. Show the owner the draft. It goes out as a reply on that thread from their own mailbox: save it there as a draft when you have a mail tool that can, otherwise give them the text to paste, and they press Send. Note the answer and its date in the `replies.md` row.

**Nudge.** When a nudge row's date arrives with no reply: append `## N1 nudge manager` and / or `## N2 nudge recruiter` to that application's `messages.md` (template in `messages.md`), validate, then `send.md` from step 1. The script sends it as a reply on the first email's thread, without the CV, once per person, and only five days or more after the first email. On send path B or C the owner replies from their own Sent folder with the text you drafted.

**T4.** When the owner says the manager accepted the invite: give them the T4 text from `messages.md` to paste (or send it in their session when `accounts.py check linkedin messages` says ALLOWED, shown first, then `record` it), with "today" and "this week" corrected to the real timing.
