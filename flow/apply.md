# Apply to one job

One run = one application. Steps in order. Every file this flow writes goes in `outreach/<slug>/`.

Input: a job link, or a company plus a role. Optional: LinkedIn People-page text the owner pasted.

Hard-fail when: company or role cannot be established; the chosen CV file is missing; the company already has a row in `outreach/log.md` for this role (re-running would double-submit; continue only if the owner says `re-apply`).

## 0. Preflight
1. Slug = company in lowercase, non-alphanumerics → `-`. A second role at the same company gets `<slug>-<role-word>`. Create `outreach/<slug>/`.
2. Fetch the job description (browser if a plain fetch is blocked). Write `jd.md`: URL, fetch date, full text. A closed or expired posting → tell the owner and stop.
3. Check the JD against "Deal-breakers" in `profile/brief.md`. A hit → tell the owner and stop unless they say continue.
4. Choose the CV by the `use_when` of each entry in `profile.json`; ambiguous → ask. Copy it into the folder: this **snapshot CV** is the file used for upload and sending.
5. Prior-contact check: search the owner's mailbox for the company name and its domain. Any hit → show subjects and dates, wait for the owner.

## 1. Classify the apply channel
From the JD link and the company careers page pick one channel, using the detection table in [`playbooks/ats.md`](../playbooks/ats.md).

## 2. Submit the application
Follow the channel's playbook with the values in `profile.json` (`form_answers` included). Fill, upload the snapshot CV, **screenshot the filled form and wait for the owner's OK**, submit, save a screenshot of the confirmation as `submitted.png`. A handoff ends when the owner replies `applied`; record the channel as `applied via <site>`. No form anywhere → the emails carry the application: channel `email`.

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
Find the real mail domain first (it can differ from the website: check the careers-page mailto links and the domain's MX record). Cross-check with the pattern sources in `people-discovery.md` § C.

- **High**: Hunter says `valid`, or a published address of that person at the company domain.
- **Medium**: a Hunter pattern not verified, or two independent pattern sources agreeing.
- **Low**: one source, a spelling ambiguity, or nothing. Low → `none` in `contacts.md`; that contact gets LinkedIn texts only.

Quota at zero → queue the contact in `outreach/followups.md` with the reset date as trigger, and continue with what is known.

## 5. Write the messages
Templates and tone: [`messages.md`](messages.md). Choose **one** hook from `brief.md` that matches the JD and state why. Write `messages.md` in the folder in exactly the format `python3 scripts/validate.py --format` prints.

## 6. Validate
```
python3 scripts/validate.py outreach/<slug>/messages.md
```
`PASS` → continue. `FAIL` → fix the text, rerun. Still failing after two rounds → hard-fail and show the owner the violations. Then read the messages yourself for what a script cannot judge: the hook truly matches the JD, every claim is in the CV or `brief.md`, nothing from "Off limits" appears.

## 7. Green light
Follow [`send.md`](send.md).

## 8. Log
Append one row to `outreach/log.md`:
```
| Date | Company | Role | JD URL | Apply channel | CV | Contacts | Emails | Status | Folder |
```
`Contacts` = `Name (HM, High); Name (Rec, Medium)`. `Emails` = send date, `held`, or `LinkedIn-only`. `Status` = `submitted` (form in, emails pending), `handoff-pending`, or `sent`. Keep `|` out of cells.

Append `| <Company> | No | | | Pending | |` to `outreach/replies.md`, run `python3 scripts/tracker.py build`, and add to `outreach/followups.md` a nudge row dated seven days out for each email sent.

When a reply arrives (the owner says so, or the mailbox shows it): edit that company's row in `replies.md` (`Got back?` = `Yes` or `Auto-ack only`; `Outcome` = `Pending`, `Interview`, `Rejected`, `Offer`), close its follow-up rows, rerun `tracker.py build`.

**Done when** the row is in `log.md`, `submitted.png` (or the owner's `applied`) exists, and the owner has been told: channel, both contacts with confidences, what was sent or is waiting, and the Hunter quota left.
