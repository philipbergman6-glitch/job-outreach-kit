# Onboarding

Run once, in order. Each step ends on its **Done when** line; move on only when it holds, then append `Step N done` (with the date) to `profile/onboarding.md`. A later session resumes at the first step lacking that line. Tell the owner at the start: this takes about 30 to 45 minutes, most of it a conversation, and nothing is sent to anyone during it.

## 1. Check what you can do

Follow [`flow/tools.md`](flow/tools.md): test each capability, then tell the owner in two or three sentences which parts will be automatic and which they will do by hand.

**Done when** every capability row except "Send mail" has a tested yes or no written in `profile/onboarding.md`, and the owner has heard the result. "Send mail" is settled in steps 5 and 7.

## 2. Get the CV

Ask the owner to put their CV in `profile/` (PDF preferred; convert a Word file to PDF and keep both). Read it fully. Read back a ten-line summary: name, contact details, current role, past roles with dates, education, languages, links. Ask what is wrong or out of date.

More than one CV version (by language, market or role type) → collect them all and ask when each is used.

**Done when** the owner has confirmed the summary and every CV file is in `profile/`.

## 3. Grill

A **relentless** interview: one question at a time, each with your recommended answer drawn from the CV, each vague answer followed up until it is concrete. Take answers from the CV instead of asking when the CV already settles them. Cover every topic below; the output is `profile/brief.md`, shaped like [`profile/brief.example.md`](profile/brief.example.md).

1. **Target roles.** Exact titles they would accept, titles close enough to consider, titles to skip. Seniority band.
2. **Where.** Countries and cities, remote / hybrid / on-site, commute limit, relocation, work authorisation per country.
3. **Companies.** Size, stage, industries wanted, industries and named companies ruled out (include current and past employers they want kept in the dark).
4. **Deal-breakers.** Salary floor, contract type, hours, travel, anything that ends the conversation.
5. **Stretch.** How far above or below their level to reach, and what share of applications may be stretch.
6. **Hooks.** Three to five pieces of work they can prove: what it was, their own part, a number or a visible result, a link if public, and which kinds of job it fits. Push for the number. A hook with no proof gets cut.
7. **Current role line.** One sentence naming what they do now, and what about their employer stays private.
8. **Off limits.** Facts that stay out of messages (gaps, reasons for leaving, side work, anything under NDA).
9. **Voice.** Language of the messages, formal or relaxed, phrases they would never write. Ask for one real email they sent and liked; match it.
10. **Form answers.** Phone format, address, notice period, salary expectation (or "always hand off"), visa and sponsorship answers, how to answer optional diversity questions.
11. **LinkedIn.** Explain the trade first: their signed-in LinkedIn is the best source of fresh jobs and of who works where, and automated activity on an account carries some risk of LinkedIn restricting it. Then ask, use by use: search jobs in their session; open a profile to confirm a contact; submit Easy Apply; send connection invites with the T3 note. Record each as yes or no. Any yes → they sign in once in the browser you control.
12. **Pace.** Applications per week, and which tracker columns they care about.

**Done when** every heading of `brief.example.md` has a concrete answer in `brief.md` and the owner has read the whole file and said it is right.

## 4. Write the profile

Write `profile/profile.json` from [`profile/profile.example.json`](profile/profile.example.json). It holds only what forms and the validator need; reasons and nuance stay in `brief.md`. In `messages`, set only the keys that differ from the defaults printed by `python3 scripts/validate.py --defaults` (language, subject line, greeting, word limits). `banned` and `attachment_phrases` add to the defaults.

Messages in a language other than English → also set `greeting`, `closing`, `opener_regex`, `fallback_opener_regex` and `attachment_phrases` in that language.

**Done when** `python3 scripts/validate.py --check-profile` prints `PROFILE OK`.

## 5. Connect the accounts

Copy `.env.example` to `.env` and open it for the owner in a plain text editor (macOS: `open -e .env`; Windows: `notepad .env`); the file is hidden in file browsers because its name starts with a dot. Walk them through each item. They paste each value into the file and save; values stay out of this chat.

1. **Email finder.** Free account at hunter.io, API key from its dashboard → `HUNTER_API_KEY`. Check: `python3 scripts/hunter.py quota` prints searches and verifications as used/available. Tell the owner what is left this month; it caps how many contacts can be looked up. Tell them too that each lookup sends a contact's name and company domain to Hunter.
2. **Sending.** Options and setup in [`flow/send.md`](flow/send.md) § Setup. The delivery test happens in step 7, on the first real application.
3. `python3 scripts/tracker.py init`.

**Done when** the quota command prints numbers, the send path (A, B or C) is written in `profile/onboarding.md`, and the three tracker files exist. A missing Hunter key is allowed if the owner declines: record it, and email finding then runs on public pattern sources only, capped at Medium confidence.

## 6. Pick the market playbooks

From topic 2 of the grill, mark in `brief.md` which sections of [`playbooks/sources.md`](playbooks/sources.md) apply, and add any job board the owner already uses.

**Done when** `brief.md` lists the job sources to search.

## 7. First run, supervised

1. Run [`flow/find-jobs.md`](flow/find-jobs.md) once. The owner picks one job they would truly apply to.
2. Run [`flow/apply.md`](flow/apply.md) on it, explaining each step in a sentence as you go.
3. At the green-light gate, on the script path, run `python3 scripts/mail.py test <slug>` first so the owner sees both emails arrive in their own inbox with the CV attached.
4. Ask what felt wrong: tone, length, the hook chosen, the contacts found. Fix `brief.md` / `profile.json` accordingly.

**Done when** one real application is logged in `outreach/log.md` and the owner has either sent its emails or decided to hold them. Write `Step 7 done`, then tell them the three sentences they will use from now on: "find me jobs", "apply to <link>", "send".
