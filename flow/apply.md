# Apply to one job

One run = one application. Steps in order. Every file this flow writes goes in `outreach/<slug>/`.

Input: a job link, or a company plus a role. Optional: LinkedIn People-page text the owner pasted.

Hard-fail when: company or role cannot be established; the chosen CV file is missing; the company already has a row in `outreach/log.md` for this role with a status other than `started` (re-running would double-submit; continue only if the owner says `re-apply`). A `started` row means an earlier run stopped midway: ask the owner whether the form was submitted, then resume at the first step whose output file is missing.

## 0. Preflight
1. Slug = company in lowercase, non-alphanumerics → `-`. A second role at the same company gets `<slug>-<role-word>`. Create `outreach/<slug>/`.
2. Fetch the job description (browser if a plain fetch is blocked). Write `jd.md`: URL, fetch date, full text. A closed or expired posting → tell the owner and stop.
3. Check the JD against "Deal-breakers" in `profile/brief.md`. A hit → tell the owner and stop unless they say continue.
4. Choose the CV by the `use_when` of each entry in `profile.json`; ambiguous → ask. Copy it into the folder: this **snapshot CV** is the file used for upload and sending.
5. Prior-contact check: search the owner's mailbox for the company name and its domain, and read `python3 scripts/mail.py ledger` for anyone at that company already written to. Any hit → show subjects and dates, wait for the owner.
6. Append the log row now (format in step 8) with `Status` = `started` and the later columns empty. Every later step updates this row.

## 1. Classify the apply channel
From the JD link and the company careers page pick one channel, using the detection table in [`playbooks/ats.md`](../playbooks/ats.md).

## 2. Submit the application
Follow the channel's playbook with the values in `profile.json` (`form_answers` included). Fill, upload the snapshot CV, then show the owner the whole filled form: a full-page screenshot (or one per screen on a long form) plus a list of every field and the value you entered. **Wait for their OK**, submit, save a screenshot of the confirmation as `submitted.png`.

During a handoff set `Status` = `handoff-pending`; it ends when the owner replies `applied`, and the channel is recorded as `applied via <site>`. Ask which CV file they uploaded when they did it themselves. No form anywhere → the emails carry the application: channel `email`.

Once the application is in, set `Status` = `submitted`, fill `Apply channel` and `CV` in the log row, and note the date: it becomes `applied:` in `messages.md`.

## 3. Find the two contacts
Procedure and confidence rubric: [`people-discovery.md`](people-discovery.md). Write `contacts.md`:

```
| Role | Name | Title | Evidence | Person confidence | Email | Email confidence |
```

## 4. Find their emails
```
python3 scripts/hunter.py domain <domain>
python3 scripts/hunter.py find <domain> "<First>" "<Last>"
python3 scripts/hunter.py verify <email>
python3 scripts/hunter.py quota
```
Run `quota` first. Find the real mail domain first (it can differ from the website: check the careers-page mailto links and the domain's MX record). Cross-check with the pattern sources in `people-discovery.md` § C.

- **High**: Hunter says `valid`, or a published address of that person at the company domain.
- **Medium**: a Hunter pattern not verified, or two independent pattern sources agreeing.
- **Low**: one source, a spelling ambiguity, or nothing. Low → `none` in `contacts.md`; that contact gets LinkedIn texts only.

Quota at zero (or a Hunter `HARD-FAIL` naming the quota or HTTP 429) → skip Hunter for this run: use the pattern sources alone, capped at Medium, queue a Hunter verification in `outreach/followups.md` with the reset date as trigger, and continue.

Both contacts' addresses come out the same, or an address is in `outreach/do-not-contact.md` → that address is `none`.

## 5. Write the messages
Templates and tone: [`messages.md`](messages.md). Choose **one** hook from `brief.md` that matches the JD and state why. Write `messages.md` in the folder in exactly the format `python3 scripts/validate.py --format` prints.

## 6. Validate
```
python3 scripts/validate.py outreach/<slug>/messages.md
```
`PASS` → continue. `FAIL` → fix the text, rerun. Still failing after two rounds → hard-fail and show the owner the violations. Then read the messages yourself for what a script cannot judge: the hook truly matches the JD, every claim is in the CV or `brief.md`, every statement about the application is what happened, nothing from "Off limits" appears.

## 7. Green light
Follow [`send.md`](send.md).

## 8. Log
Complete the application's row in `outreach/log.md`:
```
| Date | Company | Role | JD URL | Apply channel | CV | Contacts | Emails | Status | Folder |
```
`Contacts` = `Name (HM, High); Name (Rec, Medium)`. `Emails` = send date, `held`, or `LinkedIn-only`. `Status` = `started`, `handoff-pending`, `submitted` (form in, emails pending or held), or `sent`. `Folder` = `outreach/<slug>/`. Keep `|` out of cells.

Append `| <Company> | <Role> | No | | | Pending | |` to `outreach/replies.md` (Company and Role exactly as in the log row), run `python3 scripts/tracker.py build`, and add to `outreach/followups.md`:
- a **nudge** row dated seven days out for each email sent;
- a **T4** row with the trigger "<manager> accepted the LinkedIn invite", when a T3 note went to the manager.

**Done when** the row is in `log.md`, `submitted.png` (or the owner's `applied`) exists, and the owner has been told: channel, both contacts with confidences, what was sent or is waiting, and the Hunter quota left.

## Replies

**Checking.** `python3 scripts/mail.py ledger` lists every address written to, with dates. When you can read the mailbox, search it for mail from each of those addresses and from each company's domain since the send date; otherwise ask the owner what arrived.

**Recording.** Edit that application's row in `replies.md` (`Got back?` = `Yes` or `Auto-ack only`; `Outcome` = `Pending`, `Interview`, `Rejected`, `Offer`), mark its follow-up rows done, rerun `tracker.py build`, and tell the owner. `Interview` → offer [`interview-prep.md`](interview-prep.md). A reply asking not to be contacted → add the address to `outreach/do-not-contact.md` and close every follow-up for that person.

**Nudge.** When a nudge row's date arrives with no reply: append `## N1 nudge manager` and / or `## N2 nudge recruiter` to that application's `messages.md` (template in `messages.md`), validate, then `send.md` from step 1. The script sends it as a reply on the first email's thread, without the CV, once per person, and only five days or more after the first email. On send path B or C the owner replies from their own Sent folder with the text you drafted.

**T4.** When the owner says the manager accepted the invite: give them the T4 text from `messages.md` to paste (or send it in their session when `brief.md` → "LinkedIn" allows it, shown first), with "today" and "this week" corrected to the real timing.
