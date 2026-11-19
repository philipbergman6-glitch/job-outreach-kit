# Onboarding

Two sessions. **Session 1** (steps 1 to 5, about 45 to 60 minutes) ends with the owner looking at real jobs picked for them. **Session 2** (steps 6 to 10, about 1.5 to 2.5 hours, any later day, and it can stop and resume between steps) makes them ready to apply: the coaching interview, their accounts, email, and one supervised application. A career change, two languages, or a first-time Python install push both toward the long end. Tell the owner this at the start, and that nothing is sent to anyone without their say: session 1 sends nothing, and the one application in session 2 goes in only after they see the filled form, its emails only after they give the code from their preview page.

Each step ends on its **Done when** line; move on only when it holds, then append `Step N done` (with the date) to `profile/onboarding.md`. A later session resumes at the first step lacking that line.

## Interview style

Every question to the owner is asked in **rounds**, in this file and in every flow. A round is one topic: at most five questions, numbered, each with your recommended answer drawn from the CV, earlier answers or your own research, and worded so "yes" accepts it:

```
Round 1 of 5: Targets

1. Titles you want: Instructional Designer, Learning Experience Designer. Right?
2. Close enough: Training Specialist, L&D Coordinator. Right?
3. Skip: anything with "Sales Trainer". Right?
4. Level: mid-level, 3 to 5 years. Right?

Reply "yes" for all, or e.g. "yes, but 3: also skip Teacher".
```

The owner answers the whole round in one reply. A question whose answer depends on another in the same round waits for the next round. A vague answer gets one follow-up that offers two or three concrete options. Facts are your job: never ask what the CV settles or what a search can find. Say where you are ("Round 1 of 5: Targets") so the owner sees the end coming.

# Session 1: first shortlist

## 1. Check what you can do

Follow [`flow/tools.md`](flow/tools.md): test each capability, then tell the owner in two or three sentences which parts will be automatic and which they will do by hand.

**Done when** every capability row except "Send mail" has a tested yes or no written in `profile/onboarding.md`, and the owner has heard the result.

## 2. Get the CV

Ask for the CV as a PDF in `profile/`. They have a Word or Google Docs file → walk them through it: Word: File > Save As > PDF. Google Docs: File > Download > PDF document. Pages: File > Export To > PDF. Keep the original next to it; they will edit that one later. Only a photo or scan of a paper CV → it must be retyped; offer to type it from the image for them to check.

Read the PDF fully and save its text beside it as `<same name>.txt` (`profile/cv.pdf` → `profile/cv.txt`), line by line: `validate.py` checks every figure and claim in the messages against it. Text that comes out jumbled, or no text at all, means application sites will read it the same way: ask for a fresh export from the original document. Read back a ten-line summary: name, contact details, current role, past roles with dates, education, languages, links. Ask what is wrong or out of date.

More than one CV version (by language, market or role type) → collect them all and ask when each is used.

**Done when** the owner has confirmed the summary, every CV is a readable PDF in `profile/` with its `.txt` beside it, and `profile/onboarding.md` notes which file is the original they edit.

## 3. Quick interview (the five things a search needs)

Output: the first version of `profile/brief.md`, shaped like [`profile/brief.example.md`](profile/brief.example.md), with these sections filled; the rest come in step 6.

1. **Target roles.** Exact titles they would accept, titles close enough, titles to skip, seniority band. Also the same titles in the local language of each target market (an Israeli search needs the Hebrew titles too).
2. **Where.** Countries and cities, remote / hybrid / on-site, commute limit, relocation, and work authorisation per country, including whether they need visa sponsorship.
3. **Deal-breakers.** Salary floor (currency, gross, per month or year), contract type, hours, travel, anything that ends the conversation.
4. **Hooks, first pass.** Propose three pieces of work from the CV that carry a number or a visible result. They confirm, swap, or add. The full proof comes in step 6.
5. **Companies.** The size, stage and industries they want; a wish list of companies they would love to work for; and companies or industries they rule out (current and past employers they want kept in the dark go here too). For each wish-list company, run `python3 scripts/jobs.py find "<name>"` (or `jobs.py detect <its careers link>`) and note the board in `brief.md` → "Wish list", so searches read it directly. A board marked `verify` counts once the company's careers page links to it.

Then the **reality check**, before writing anything down: for the main target title and place, look up what such roles pay (two independent salary sources, with the year in the search) and how many open postings a quick search finds. Tell the owner plainly when the target and the CV are far apart: a salary floor above the market, a title two levels up, a city with few such jobs, a career change with no evidence yet. Offer one or two adjustments and let them decide. Record the market numbers and their sources in `brief.md` → "Market check".

**Done when** sections Targets, Where, Deal-breakers, Hooks (names), Companies and Market check of `brief.md` have concrete answers and the owner has read them.

## 4. Write the first profile

Write `profile/profile.json` from [`profile/profile.example.json`](profile/profile.example.json). It holds only what forms and the validator need; reasons and nuance stay in `brief.md`. Leave `form_answers`, `accounts` and `languages` for session 2 (`accounts` empty means every signed-in use is refused, which is the safe default).

**Done when** `python3 scripts/validate.py --check-profile` prints `PROFILE OK`.

## 5. First shortlist

Run [`flow/find-jobs.md`](flow/find-jobs.md) in its **quick** form: the wish-list companies through `scripts/jobs.py` where their boards allow it, plus one search per target title, at most ten searches in all. Score against the hook names from step 3 and treat "Stretch" as none until session 2. Show the A table.

Then say what happens next: "Next time we do a deeper interview so the emails sound like you, connect your accounts, and send your first application. Say 'continue onboarding' whenever you're ready." They may pick jobs now; those wait in the triage file until step 10.

**Done when** a triage file passes `python3 scripts/triage.py check` and the owner has seen it.

# Session 2: ready to apply

## 6. Coaching interview

The step a good career coach would spend an hour on. Cover every topic; it fills the remaining sections of `brief.md`. Rounds: one per topic for 1 to 6 (one per hook for 3), then 7 and 8 together, 9 to 11 together, and 12 to 14 one each. Prefill each round from the CV, the session-1 brief and the shortlist so most answers are "yes".

1. **The story.** Why they are looking now, and what they want more and less of in the next job. Then write their one-line pitch with them: who they are, the proof, what they want next. It opens every email; they must be able to say it aloud.
2. **Career change?** When the target differs from their past roles: name the transferable skills, the evidence for each (a project, a course, a result), and the gap a hiring manager will see first. Agree how the messages bridge it (one sentence, written now) and whether a work sample or portfolio would close the gap. Instructional design, design, writing, data and engineering roles are hired on samples: no sample → say so, and suggest the smallest one that proves the skill.
3. **Hooks, in full.** For each hook: what it was, their own part, the number or visible result, a public link if any, and which kinds of job it fits. Push for the number. A hook with no proof gets cut.
4. **CV fit.** Take the requirements that recur in three to five shortlisted postings. Map each to a CV line; list the requirements with no line, and the CV lines that sell nothing for this target. Propose concrete edits (reorder, reword, add a missing fact the owner confirms, remove noise); never invent. Offer once: the kit can make every CV itself in a plain layout application sites read well (`playbooks/cv-template.html`), so tailored CVs need nothing from them later. Show it: their CV text in that layout as `profile/<cv name>.html`, printed as [`flow/apply.md`](flow/apply.md) step 0.8 does. Recommend it unless their field judges CVs on looks (design, illustration, architecture). Yes → `cv layout: kit` in `profile/onboarding.md`, and the edits below go into that page. No, or no `browser_pdf_save` tool → `cv layout: own`, never offered again, and the owner makes the edits in their original document and exports a new PDF. Either way, add it to `cvs` with its `use_when`, and save its text beside it as in step 2. Shortlisted postings that fall into two or three kinds of role (say, corporate training and e-learning development) → one version per kind, at most three, each its own `cvs` entry. These versions are the base; each application tailors its own copy on top ([`flow/apply.md`](flow/apply.md) step 0.8). Tell the owner that, and confirm the original document stays where `profile/onboarding.md` says, because every tailored CV starts from it.
5. **Their LinkedIn profile.** Every email links to it. Read it (their public URL, or they paste the text): headline, current role and dates matching the CV, a photo. List what to fix before the first email goes out.
6. **Who they know.** A referral is worth many cold emails. For each wish-list company: do they know anyone there, or anyone who could introduce them? Record names in `brief.md` → "Network". [`flow/apply.md`](flow/apply.md) step 0 checks this list before writing to strangers. Offer once, optional: LinkedIn can export their connections so you can see who they know at every company. Checklist: on LinkedIn, Me → Settings & Privacy → Data privacy → Get a copy of your data → tick only "Connections" → Request archive; LinkedIn emails a download link, usually within minutes; download it and say where it landed. Move its `Connections.csv` (unzipped) to `profile/connections.csv` yourself, run `python3 scripts/network.py match "<company>" ...` on the wish list, and ask about the matches in rounds of five: an exact or strong one → well enough to ask a favour? (recommended: yes when they connected in the last few years); a weak one → does that person work there? Yes → "Network". Declined → write `connections: declined` in `profile/onboarding.md` and never offer again.
7. **Timeline.** When they could start (notice period, a school year, a project end), how urgent the search is, and interview availability.
8. **Trade-offs.** Rank what matters when two offers compete: money, role, company, commute, growth, stability. Three ranked items are enough.
9. **Stretch.** How far above or below their level to reach, and what share of applications may be stretch.
10. **Current role line.** One sentence naming what they do now, and what about their employer stays private. Between jobs → empty, and agree how the story covers the gap.
11. **Off limits.** Facts that stay out of messages (gaps, reasons for leaving, side work, anything under NDA).
12. **Voice and languages.** Which language each market's messages use, formal or relaxed, phrases they would never write. Do not ask them to describe their style; ask for 2 to 3 messages they actually wrote recently (a work email, a LinkedIn message, a chat message to a colleague), one set per language, and paste them into `brief.md` → "Voice" → "Samples". From the samples note what they do: sentence length, how they open and sign off, words they repeat, words they never use. None to hand → write one short paragraph in two registers and let them pick; a paragraph written on request is the last resort, because people write stiffly when tested. The first real drafts in step 10 refine this. Messages in more than one language → set up `languages` in `profile.json` (step 8, item 5).
13. **Form answers, as one table.** Fill this table from the CV and earlier answers, show it, and let them correct it in one reply: phone format, address (only if they want it on forms), notice period, salary expectation (a figure, or `ask me`: every form asking for it then waits for them), work authorisation and sponsorship per country, how to answer optional diversity questions.
14. **Pace.** Applications per week, the most emails in one day (default 20), how they want progress reported. Check the pace against what the email finders allow (step 8): two people are emailed per application, and each costs up to one lookup per configured finder when the free methods do not settle it first (`emails.py find` stops at the first finder that verifies an address). Ten applications a week can need up to eighty lookups a month per finder. Say what is realistic.

**Done when** every section of `brief.example.md` except "Accounts" (step 7), "Job sources" (step 9) and "Interview notes" (filled by later mock interviews) has a concrete answer in `brief.md`, the CV edits are made or declined, and the owner has read the whole brief and said it is right. Update `profile.json`: `hooks`, `current_role_line`, `form_answers`, `max_emails_per_day`, `cvs`, and `messages` (only keys that differ from `python3 scripts/validate.py --defaults`).

## 7. Accounts and permissions

The kit can work inside the owner's own signed-in accounts: LinkedIn, Jobify360 or another job board they use, their mailbox. It does nothing there without a recorded yes.

Explain the trade first, in these terms: a signed-in LinkedIn is the best source of fresh jobs and of who works where, and job boards show more inside the login. LinkedIn's user agreement forbids automated activity on an account, and LinkedIn can restrict an account for it, sometimes for good; other sites have similar rules. Reading a few pages at a human pace is the low-risk end; submitting, inviting and messaging are the high-risk end. The kit keeps a daily limit for each use on each site (the defaults are in `python3 scripts/accounts.py --help`; `profile.json` → `account_caps` lowers or raises one, e.g. `{"linkedin": {"read_people": 10}}`) and logs every action in `outreach/accounts-log.md`, which they can read any time.

Then for each account they have, one round with the uses that fit it (the five below for a job site, `mailbox` for their email), and record each answer as `true` or `false` in `profile.json` → `accounts`:

| Use | What it lets you do | Recommend |
|---|---|---|
| `search_jobs` | read job searches and postings inside the login, including "who posted this job" | yes |
| `read_people` | open a company's people page or a person's profile, to find and confirm the hiring manager, recruiter and head of HR | yes |
| `apply` | submit Easy Apply / quick apply for them, always shown to them first | no: they click it from your checklist |
| `invites` | send a connection invite with the T3 note, shown first | no: they click it |
| `messages` | send a message on the site, shown first | no |
| `mailbox` | in their email (its webmail page, or a mail tool connected to you): search for replies and bounces, save drafts. Never send: emails leave only through `mail.py send` | yes |

The choice is theirs. Any yes → they sign in once in the browser window you control (they type the password; it stays out of chat and files). Check: `python3 scripts/accounts.py status` shows their answers.

**Done when** every account they named has an answer for each of its uses in `profile.json` → `accounts`, `--check-profile` passes, and any account with a yes is signed in in the controlled browser.

## 8. Email finding and sending

Copy `.env.example` to `.env` and open it for the owner in a plain text editor (macOS: `open -e .env`; Windows: `notepad .env`); the file is hidden in file browsers because its name starts with a dot. They paste each value and save; values stay out of this chat.

1. **Email finding needs no account.** `scripts/emails.py` finds addresses from the company's own pages, its public code, the mail server itself and the address pattern. Test it on a known address: `python3 scripts/emails.py mx <their own work or university domain>`. When `emails.py probe` reports port 25 blocked (common on home and cloud networks), the mail-server check is unavailable and API finders matter more.
2. **Optional finders, for more reach.** Prospeo (about 100 free a month), Hunter (about 25), Apollo (about 75, work email needed to sign up) and Tomba (about 25) have free tiers; Anymail Finder (trial) and Findymail (a few free credits) are paid. Recommend one or two free ones; they create the account and paste the key. `python3 scripts/emails.py providers` shows which are set and what is left. Tell them each lookup sends a contact's name and company domain to that provider.
3. **Optional semantic search.** An Exa key (about $10 of free searches a month) lets `scripts/search.py people` find "the head of data at Acme" by meaning. Your own web search covers the same ground more slowly; skip it unless they want speed.
4. **Sending.** Options and setup in [`flow/send.md`](flow/send.md) § Setup. The delivery test happens in step 10.
5. **Second language.** Messages in another language → add `languages` to `profile.json`, one entry per language with `subject`, `greeting`, `closing`, `opener_regex`, `fallback_opener_regex`, `attachment_phrases` and `today_words` in that language, `signature_name` when the name is spelled differently, and `hook_names` (each hook's name in that language). Each application's `messages.md` then says `language: <name>`; `--check-profile` checks the entry.
6. `python3 scripts/tracker.py init`. Ask whether anyone, or any company, must never be written to (a current manager, a former employer); add each to `outreach/do-not-contact.md`.

**Done when** `emails.py mx` answered, the send path (A, B or C) is written in `profile/onboarding.md`, the four tracker files exist, and `--check-profile` passes.

## 9. Pick the job sources

From "Where" and "Targets", mark in `brief.md` → "Job sources" which sections of [`playbooks/sources.md`](playbooks/sources.md) apply, and add any job board the owner already uses. Each wish-list company still without a board → `python3 scripts/jobs.py find "<name>"`, and note the board name, so every search reads it directly.

**Done when** `brief.md` lists the job sources and the wish-list boards.

## 10. First run, supervised

1. Run [`flow/find-jobs.md`](flow/find-jobs.md) in full (or reuse a shortlist from step 5 that is under a week old). The owner picks one job they would truly apply to.
2. Run [`flow/apply.md`](flow/apply.md) on it, explaining each step in a sentence as you go.
3. **Voice round.** Once the emails are written and before the green-light gate, show the manager email in chat and ask: "Does this sound like you? Mark anything you would never write." Rewrite and show it again, up to three rounds, until they say it sounds like them. Turn each correction into a rule as `flow/send.md` describes ("Learned from edits").
4. At the green-light gate, on the script path, run `python3 scripts/mail.py test <slug>` first so the owner sees the emails arrive in their own inbox with the CV attached. Then explain the preview page before it opens: it shows the real emails and a code, and giving you that code is how they say send.
5. Ask what felt wrong: tone, length, the hook chosen, the contacts found. Fix `brief.md` / `profile.json` accordingly.

**Done when** one real application is logged in `outreach/log.md` and the owner has either sent its emails or decided to hold them. Write `Step 10 done`, then tell them the sentences they will use from now on: "find me jobs", "apply to <link>", "send <code>", "any replies?", "how is it going?", "prepare me for the interview", "practise an interview for <company>".
