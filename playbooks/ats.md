# Application-site playbooks

Field values come from `profile/profile.json`. Rules for every channel:

- Upload the snapshot CV from `outreach/<slug>/`.
- Show the owner the whole filled form (full-page screenshot, or one per screen, plus the list of fields and values) and get their OK before Submit. Until that OK, the visible browser window never rests on a filled form with Submit in reach: an owner glancing at it can press Submit by mistake (2026-11-25, one form went in that way). Take the screenshots, then move the window off the form (open a blank tab and switch to it) and keep it there until they answer; on their OK, switch back and check the fields survived.
- On an "unknown error" after Submit: remove the attachment, re-attach, resubmit once. A second failure → handoff.
- Optional diversity / self-identification blocks: answer as `form_answers` says, else leave blank or "Decline".
- A field `form_answers` and `profile/answers.md` do not answer (salary when it says `ask me`, visa, ID number, a free-text screening question) → show the owner the question and wait for their answer (a free-text one: `flow/apply.md` § 2). A new standing answer to a short field (notice period, salary) goes into `form_answers`; an approved free-text answer goes into `profile/answers.md`.
- A CAPTCHA, a "verifying your device" page, or a bot block → handoff. The owner finishes in the same headed window when there is one.

Observations below are dated; sites change. Append what you see.

Boards `jobs.py` reads, seen 2026-11-19: Workable (`apply.workable.com/<slug>`), Recruitee (`<slug>.recruitee.com`), Breezy (`<slug>.breezy.hr`), Personio (`<slug>.jobs.personio.de`, an XML feed with no job links; the kit builds `/job/<id>`), Rippling (`ats.rippling.com/<slug>`, no dates in the list). `jobs.py alive` (2026-11-19): Greenhouse, Workable and Workday answer per job (404 = gone; Workday 403 with `S22` = withdrawn); Lever's API also 404s some live confidential postings, so a Lever 404 stays unknown; SmartRecruiters is read by its `active` flag; the list-only boards (Ashby, Comeet, Recruitee, Breezy, Personio, Rippling) by whether the board still lists the job. Breezy and Rippling list without the job text: `--save` reads each kept job's page (Breezy: its second JSON-LD block, the first describes Breezy itself; Rippling: the page's embedded data).

| Channel | Detect | Action |
|---|---|---|
| `comeet` | `comeet.com/jobs/`, `comeet.co`, an iframe named `comeet-applyform-*` | submit (below) |
| `greenhouse` | `job-boards.greenhouse.io`, `boards.greenhouse.io`, `iframe#grnhse_iframe` on a careers page | submit (below) |
| `lever` | `jobs.lever.co`, `jobs.eu.lever.co` | attempt (below); verification error → handoff |
| `ashby` | `jobs.ashbyhq.com/<Company>/<uuid>` | submit (below) |
| `eightfold` | `<company>.eightfold.ai/careers`, or "Powered by eightfold.ai" in the footer | submit (below) |
| `workday` | `*.myworkdayjobs.com` | handoff for account creation, then continue (below) |
| `smartrecruiters` | `jobs.smartrecruiters.com` | attempt in a headed browser (below); bot wall → handoff |
| `workable`, `recruitee`, `breezy`, `personio`, `rippling` | the board links above | no playbook yet: the `other-form` rules; append what you see |
| `applied via linkedin easy apply` | "Easy Apply" button on a LinkedIn posting | submit when `accounts.py check linkedin apply` says ALLOWED, else handoff (below) |
| `other-form` | a login-free page showing name and email fields **and** a file input | fill, upload, screenshot, submit; anything unexpected → handoff |
| `handoff` | login wall, CAPTCHA, unknown site, unanswerable field | checklist: URL, each field with its value, CV path; wait for `applied` |
| `email` | no form on the posting or the careers page | the emails carry the application (`flow/messages.md` § No form existed) |

## Comeet (worked Oct to Nov 2026)
1. Open the company job list `https://www.comeet.com/jobs/<slug>/<company-uid>` and click the listing; opening a job URL directly can abort. When a company site hides the widget, read the company and position uids from the careers page source (`comeetvar`, the widget script, or the iframe `src`).
2. The form sits inside the `comeet-applyform-*` iframe; search inside it for the fields. Text waits on the outer page miss the iframe.
3. Fill first name, last name, email, phone, website. Phone: local digits when a country selector exists, full international number when there is one phone box.
4. "Attach Resume" → upload → confirm the file name shows.
5. Screenshot → OK → "Submit application" → wait about five seconds → look for "Thank you" or "Oops".
6. "Session verification failed due to a human check" → the form scored the browser as a bot. A headless browser → retry once headed (2026-11-25: two of three headless submits failed this check; the same forms went through at once in a headed browser on a copy of the signed-in browser profile). Still failing → use the "email your resume" address printed under the form (a saved posting's `apply_email`): channel `email`, with that address in the recruiter slot as `Hiring Team` (`flow/messages.md` § No form existed).

Seen 2026-11-22: the raw apply URL `https://www.comeet.co/jobs/<company-uid>/<position-uid>/apply?company-uid=<company-uid>&position-uid=<position-uid>&embedded=true` loads the bare form (no widget, no iframe); eight submits in a row worked that way. Fields: `firstName`, `lastName`, `email`, `phone`, `cv` (file), `websiteUrl`, `comment`; submit = `button.applyButton`. Custom questions (a privacy "I agree", "Do you live in …?", "How did you hear …?") are radio inputs with numeric ids: `.check()` fails as "outside of the viewport", a DOM `el.click()` sets them. The company uid: the careers page's iframe `src`, or (2026-11-26) the page source's `company-uid": "<uid>"` on a company page at `/career/position/<position-uid>/`.

Seen 2026-11-19, the widget on a company careers page: the `comeet.co/jobs/<company-uid>/<position-uid>/apply` iframe loads hidden. Its fields fill while hidden, but an element screenshot or a click on its submit button waits until the page's own "Apply for this position" button has been clicked. `frame.click('button[type=submit]')` timed out even then; `page.frameLocator('iframe[src*="comeet.co/jobs"]').getByRole('button', {name: /submit application/i})` worked. No human check in a headed browser.

Seen 2026-11-19: the public job list `comeet.com/jobs/<slug>/<uid>` prints the company's positions-API token next to its `company_uid`; `jobs.py list comeet:<slug>/<uid>` reads it, then the API. Comeet publishes no posting date, only the last update. `url_active_page` can be the company's generic careers page, so the kit links to the Comeet-hosted page. A company site embedding the widget still links to `comeet.com/jobs/<slug>/<uid>/...`, which `jobs.py detect` reads. Each position carries an `@applynow.io` address that takes a CV by email.

## Greenhouse
1. Open `https://job-boards.greenhouse.io/<board>/jobs/<id>` (read the `iframe#grnhse_iframe` src when embedded). Skip "Autofill with Greenhouse" and MyGreenhouse login.
2. Top-level form: `#first_name`, `#last_name`, `#email`, `#phone` (country is a searchable combobox), custom `question_*` fields (searchable comboboxes).
3. "Attach" (`#resume`) → upload → wait for the file name chip.
4. Screenshot → OK → "Submit application". Success = a `/confirmation` page, "Thank you for applying". "Please complete the reCAPTCHA" → handoff in the same window. An emailed security code → the owner reads it out.

Seen 2026-11-22: an education block (school, degree and discipline as searchable comboboxes, end year) can be required. The phone country picker's options are also `role=option`, so pick by the option text, never by index.

## SmartRecruiters (submitted 2026-11-22 in a headed browser)
1. The posting's "I'm interested" link (`/oneclick-ui/company/<Company>/publication/<uuid>`) opened without a bot wall in a headed browser. A bot wall or CAPTCHA → handoff.
2. Fields are web components (`spl-input`): target the inner `input` (`#first-name-input input`). City is an autocomplete: type, then click the `option`.
3. A second "screening" page carries salary, relocation, work authorisation, a certify checkbox, the privacy checkbox and an equal-opportunity combobox: `form_answers`, else handoff.
4. Screenshot → OK → submit. Success URL ends `/success`.

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

2026-11-19, `jobs.py alive` on NVIDIA's site: a withdrawn posting's API answers `403` with `"errorCode":"S22"` ("permission denied"), three old postings alike (one, `Payroll-Specialist_JR1986430`, is missing from the site's own search for its title, which lists a newer one: withdrawn, not just old); a job id that never existed answers `404` `S21`; a live one answers `200`. After about fifteen quick requests Cloudflare answers `429` with an HTML page for a few minutes: `alive` reports that as unknown, so wait and rerun once.

2026-11-19, `jobs.py list` on NVIDIA's site: the jobs API (`/wday/cxs/.../jobs`) gives the board's `total` (2000) on the first page only; offset 20 and 40 answer `"total": 0` with 20 jobs each. `jobs.py` now keeps the first page's count and reads up to 200, then prints a NOTE; narrow a big board with `--search`.

## LinkedIn Easy Apply
`python3 scripts/accounts.py record linkedin apply "<company> <role>"` says ALLOWED: open the job in the owner's signed-in session, click Easy Apply, fill contact details, choose the CV (LinkedIn preselects the last file used: upload this application's snapshot CV whenever it was tailored, and confirm the selected file name matches it), stop at any screening question the profile leaves unanswered, show the owner the review page, then submit. Success text: "Your application was sent to <Company>". Log the channel as `applied via linkedin easy apply`. Not allowed → handoff: the owner clicks Easy Apply themselves.

Seen 2026-11-25 and 2026-11-26:
- The resume step has no visible file input. Click "Upload resume" on its own, then call the browser tool's file-upload function; clicking it inside a run-code script leaves the tool's file-chooser open and the script never returns. Before Review, confirm the checked radio is this application's file.
- Yes/no screening questions sit in `fieldset`s that a dialog-scoped query can miss: `fieldset.nth(i).getByText('Yes', {exact: true}).click()`, or find the question text and click the first "Yes" after it (XPath `following::*[normalize-space(text())="Yes"][1]`).
- A salary box may reject text ("Invalid input") and take digits only.
- A "Resume uploaded successfully" toast carries `role=alert`: not an error.
- Some Easy Apply forms are Greenhouse-backed ("Application powered by Greenhouse") and add employer questions (office days, shift availability).

Connection invites, when `accounts.py record linkedin invites "<name>"` says ALLOWED (one record per invite): Connect often sits under the profile's "More" menu. A free account gets about five noted invites a month and the note box counts to 200 characters; when the notes run out, send without a note. Manager first.

## Other forms seen (`other-form`)
- 2026-11-25, monday.com forms embedded on a careers page (`forms.monday.com/forms/embed/<id>?position_id=<n>`): `#name-input`, `#files-file-input` (CV), `#phone_1-country-code-dropdown-input` + `#phone_1-phone-number-input`, `#email-input`, a "How did you hear about us?" downshift combobox (click it, then dispatch a click on the `[role=option]`; a pointer click times out), `#check-checkbox` (privacy). Success text "Form submitted successfully". The page may also carry a site contact form without a CV field; the monday.com one is the application.
- 2026-11-25, Dueto (`employer.dueto.io/position/<id>/<company>`): Apply → upload CV → Next → name, email, phone and LinkedIn autofill from the CV (a name in capitals: retype it) → optional salary and a "Flexible" checkbox (leave both) → privacy checkbox → "Submit Application" → "We got your application!".
- 2026-11-25, small-company WordPress careers forms posting to a `wp-json/<theme>/v1/apply` endpoint: success = that endpoint's 200 response with a reference id (`{"ref": "..."}`) and a short "received" line on the page. 2026-11-26, Elementor careers forms: a page can carry two forms (application and sales contact): use the one holding the file input; success = a redirect to a thank-you page. Both passed an invisible reCAPTCHA v3 headless. Leave honeypot fields ("Leave this field empty") and marketing-consent boxes untouched.
- 2026-11-25, an in-house careers form behind Cloudflare (`revolut.com/careers`): plain fetches get 403; a headed real Chrome loads the posting and the form (`/careers/apply/<job-uuid>/`). A cookie dialog intercepts clicks until "Reject non-essential cookies". Dropdowns are `input[type=button]` opening virtualised `[role=option]` lists (about nine shown); long lists (country, university, major) have an `input[type=search]` to filter. A multi-select of work locations reads "Consider me for all available locations" when all are selected. The CV upload pre-fills Experience entries (company, role, dates): check each. Education is an "Add" dialog whose month/year cells need a forced click; a school missing from the list → "Other – not listed". Role questions differ per posting. Success = `/careers-thanks/`, and a confirmation email within a minute. One form there went in from the visible window before the owner's OK: see the window rule at the top of this file.
- 2026-11-25, an agency's job pages (SQLink, `sqlink.com/career/...`): three CV forms per page. The one tied to the job is `#SideCvForm` (hidden `JobId` = the page id, `JobName` = the title): `FullName`, `Email`, file `fileSideCV`, and one `Agree` checkbox that bundles marketing email/SMS consent with the terms; it cannot be accepted separately, so tell the owner before ticking it. The job box's own "send CV" button (Hebrew "שלח קורות חיים") opens a generic form whose `jobId` is `1` ("general"): not tied to the job, never use it. The side panel sits off-screen: fill and click through `evaluate` / `setInputFiles` (pointer clicks time out). Cloudflare challenges the first load (wait a few seconds after `goto`); the invisible reCAPTCHA v3 passed headless. Success = a redirect to `/careerconfirm/`.
- 2026-11-26, Teamtailor (`careers.<company>/jobs/<id>-<slug>`): "Apply for this job" opens an in-page form: `#candidate_first_name`, `#candidate_last_name`, `#candidate_email`, `#candidate_phone`, CV via `#candidate_resume_remote_url` (`setInputFiles`, no file chooser), consent `#candidate_consent_given` (DOM click). `#full_email` is a honeypot: leave it empty. Success URL ends `/applications/<uuid>/thanks/...`, title "Applied to <role>".
- 2026-11-26, Manatal (`<company>.careers-page.com/jobs/<uuid>/apply`): custom required fields can ask for owner facts the profile lacks (a degree GPA, a psychometric score) → handoff question. Submit stays disabled until the consent box is ticked through its visible `[role=checkbox]` element; the hidden `input[type=checkbox]` ignores `check()`, and clicking the consent text opens the terms in a new tab. Success = a "Thank you for your application!" panel on the same URL.

## Mail connectors (send option B)
- 2026-11-23, the Claude Gmail connector (`create_draft`, `attachments` with base64 `content`): the stored attachment is correct. `download_gmail_attachment` on the draft's `messageId` returned the PDF byte for byte (same size, same SHA-256). Verify every attachment that way, by SHA-256: a size check misses a single miscopied character. Do not verify by `get_draft` / `get_message` with `RAW`: that read-back shows attachments base64-encoded twice even when the stored file is fine, and `FULL_CONTENT` lists no attachment on a draft.
- Same day: the whole file passes through your tool call as base64 text, about 4/3 of its size. A 2 KB PDF and a 30 KB PDF of random bytes (41,000 base64 characters, copied from a terminal print) both arrived identical by SHA-256. Larger files are untested; a typical CV PDF of 50 to 150 KB may not fit in one tool call. Attach through the tool at 30 KB or less; above that, the owner drags the CV in.
- Same day: every link in a draft saved through the connector reads back as `https://www.google.com/url?q=…&ust=<creation time + 24 h>`: plain text, HTML `href`s, and bare `github.com/…` or `www.…` text alike, and the same value on every later read. The API cannot show whether Gmail stores and sends it that way; assume it does (such redirects expire into a Google warning page). So drafts saved through a connector carry no links; a link the email needs, the owner types into the draft in Gmail.

## Webmail drafts through a browser (send option B)
- Attach by setting the compose window's hidden `input[type=file]` directly; clicking the paperclip opens a system file dialog that browser tools handle badly.
- After attaching, read the saved draft back: some webmail editors turn bare links into tracking redirects. Restore the clean link text before closing the draft.
- Work in batches of five drafts or fewer, and verify each has its attachment.
