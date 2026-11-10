# Application-site playbooks

Field values come from `profile/profile.json`. Rules for every channel:

- Upload the snapshot CV from `outreach/<slug>/`.
- Show the owner the whole filled form (full-page screenshot, or one per screen, plus the list of fields and values) and get their OK before Submit.
- On an "unknown error" after Submit: remove the attachment, re-attach, resubmit once. A second failure → handoff.
- Optional diversity / self-identification blocks: answer as `form_answers` says, else leave blank or "Decline".
- A field `form_answers` does not answer (salary when it says `ask me`, visa, ID number, a free-text screening question) → show the owner the question and wait for their answer; save new standing answers to `form_answers`.
- A CAPTCHA, a "verifying your device" page, or a bot block → handoff. The owner finishes in the same headed window when there is one.

Observations below are dated; sites change. Append what you see.

| Channel | Detect | Action |
|---|---|---|
| `comeet` | `comeet.com/jobs/`, `comeet.co`, an iframe named `comeet-applyform-*` | submit (below) |
| `greenhouse` | `job-boards.greenhouse.io`, `boards.greenhouse.io`, `iframe#grnhse_iframe` on a careers page | submit (below) |
| `lever` | `jobs.lever.co`, `jobs.eu.lever.co` | attempt (below); verification error → handoff |
| `ashby` | `jobs.ashbyhq.com/<Company>/<uuid>` | submit (below) |
| `eightfold` | `<company>.eightfold.ai/careers`, or "Powered by eightfold.ai" in the footer | submit (below) |
| `workday` | `*.myworkdayjobs.com` | handoff for account creation, then continue (below) |
| `smartrecruiters` | `jobs.smartrecruiters.com` | handoff |
| `applied via linkedin easy apply` | "Easy Apply" button on a LinkedIn posting | submit when `brief.md` allows it, else handoff (below) |
| `other-form` | a login-free page showing name and email fields **and** a file input | fill, upload, screenshot, submit; anything unexpected → handoff |
| `handoff` | login wall, CAPTCHA, unknown site, unanswerable field | checklist: URL, each field with its value, CV path; wait for `applied` |
| `email` | no form on the posting or the careers page | the emails carry the application (`flow/messages.md` § No form existed) |

## Comeet (worked Oct to Nov 2026)
1. Open the company job list `https://www.comeet.com/jobs/<slug>/<company-uid>` and click the listing; opening a job URL directly can abort. When a company site hides the widget, read the company and position uids from the careers page source (`comeetvar`, the widget script, or the iframe `src`).
2. The form sits inside the `comeet-applyform-*` iframe; search inside it for the fields. Text waits on the outer page miss the iframe.
3. Fill first name, last name, email, phone, website. Phone: local digits when a country selector exists, full international number when there is one phone box.
4. "Attach Resume" → upload → confirm the file name shows.
5. Screenshot → OK → "Submit application" → wait about five seconds → look for "Thank you" or "Oops".
6. "Session verification failed due to a human check" → the form scored the browser as a bot. Use the "email your resume" address printed under the form: channel `email`, with that address in the recruiter slot as `Hiring Team` (`flow/messages.md` § No form existed).

## Greenhouse
1. Open `https://job-boards.greenhouse.io/<board>/jobs/<id>` (read the `iframe#grnhse_iframe` src when embedded). Skip "Autofill with Greenhouse" and MyGreenhouse login.
2. Top-level form: `#first_name`, `#last_name`, `#email`, `#phone` (country is a searchable combobox), custom `question_*` fields (searchable comboboxes).
3. "Attach" (`#resume`) → upload → wait for the file name chip.
4. Screenshot → OK → "Submit application". Success = a `/confirmation` page, "Thank you for applying". "Please complete the reCAPTCHA" → handoff in the same window. An emailed security code → the owner reads it out.

## Lever
1. Open `https://jobs.lever.co/<company>/<uuid>/apply` (EU: `jobs.eu.lever.co`). Form `#application-form`.
2. Upload the CV **first** (`#resume-upload-input`): Lever parses it and autofills. Wait for "Analyzing…" to clear, then check every field.
3. Fill name, email, phone, current company, link fields, custom cards. Location: type, wait a second, pick from the dropdown.
4. Screenshot → OK → submit. Success = `/thanks`, "Application submitted!". A visible hCaptcha or "error verifying your application" → handoff in the same window; re-check that the CV and fields survived.

## Ashby (worked Oct 2026; CAPTCHA seen Nov 2026 in a headless browser)
1. Open `.../<uuid>/application`. The form shows "Fetching application form" first; look again after two seconds.
2. CV first: "Upload File" under Resume → the chip shows the file name.
3. Fill name, email, phone, LinkedIn, screening boxes. Yes/No questions are toggle buttons.
4. "Missing entry for required field" on a box that visibly holds text → click into it and type the text again key by key, then resubmit.
5. Screening boxes are free text: answer from the CV and `brief.md` only, and show the answers at the screenshot gate.
6. Success = heading "Success", "Thanks for applying!", same URL. An image CAPTCHA after Submit → handoff.

## Eightfold (worked Oct 2026)
1. Titles on the board can differ from titles on LinkedIn: search the board (`/careers?query=<title>&location=<city>`) and match on the JD text.
2. Open the job → "Apply Now". CV first: "Upload resume" → confirm the privacy dialog → wait for "File upload completed successfully"; the form autofills. Check each field.
3. Screening comboboxes: click, look again (element references change), pick. Tick the privacy checkbox.
4. Screenshot → OK → submit. Success = `/careers/apply/success`.

## Workday
Every Workday site needs its own candidate account. Handoff: the owner creates the account in the headed window (email, their own password, the verification email). Then continue in that logged-in window: "Autofill with Resume", check each page, screenshot the review page → OK → submit. Phone fields want the local number. Salary and notice-period questions come from `form_answers` or the owner.

## LinkedIn Easy Apply
Allowed in `brief.md` → "LinkedIn": open the job in the owner's signed-in session, click Easy Apply, fill contact details, choose the CV (upload the snapshot CV once; LinkedIn keeps it, so on later applications confirm the selected file is the right one), stop at any screening question the profile leaves unanswered, show the owner the review page, then submit. Success text: "Your application was sent to <Company>". Log the channel as `applied via linkedin easy apply`. Not allowed → handoff: the owner clicks Easy Apply themselves.

Connection invites, when allowed: Connect often sits under the profile's "More" menu. A free account gets about five noted invites a month and the note box counts to 200 characters; when the notes run out, send without a note. Manager first.

## Webmail drafts through a browser (send option B)
- Attach by setting the compose window's hidden `input[type=file]` directly; clicking the paperclip opens a system file dialog that browser tools handle badly.
- After attaching, read the saved draft back: some webmail editors turn bare links into tracking redirects. Restore the clean link text before closing the draft.
- Work in batches of five drafts or fewer, and verify each has its attachment.
