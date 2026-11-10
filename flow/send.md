# Green light and send

The **green light** is the owner's approval of the exact emails about to go out. It is the only thing that authorises a send, and its proof is a code only the owner can see.

## Steps

1. Preview everything waiting to send in one command: `python3 scripts/mail.py preview <slug> [<slug> ...]`. It prints each email (recipient, confidence, subject, attachment, body) and opens the owner's **preview page** in their browser with the same emails and a one-time approval code. The page did not open → give the owner the file path the script printed and ask them to open it.
2. Paste the printed emails into chat too, with one summary table for a batch (company, recipient, confidence). Also show the T3 notes and T4 message: the owner pastes those into LinkedIn themselves, unless `brief.md` → "LinkedIn" allows invites (`playbooks/ats.md`).
3. Ask one question: send all, send some, edit, or hold. Tell them the page shows what to type to send.
4. Read the answer narrowly:
   - The owner gives the code from their page ("send 482913") → step 5.
   - Approval without the code ("yes, send them", "go") → ask for the code on the page; it is how the script knows they read it.
   - Approval of some applications, or of one email of a pair → preview again with only those (`--only hm` or `--only rec` for one email of one application); the rest stay held.
   - Any edit request, however small → change `messages.md`, rerun `validate.py`, return to step 1. A new preview replaces the earlier page, code and approval.
   - Hold, or a change of mind after giving the code → `python3 scripts/mail.py cancel`.
   - A question, a "looks good" about one paragraph, silence, or anything you have to interpret → ask again. Approval given in an earlier session, or for an earlier preview, covers nothing here.
5. Record it: `python3 scripts/mail.py approve --code <the code they gave> --quote "<what they wrote>"`. It covers exactly what that preview showed.
6. `python3 scripts/mail.py send <slug> [<slug> ...]`, straight away. An approval works once and for 30 minutes. A refusal is final until its cause is fixed and steps 1 to 5 are repeated; an SMTP failure is reported to the owner and retried only through this script: `mail.py status <slug>` shows what went, and the retry names only the applications with something left.
7. Tell the owner what went out, to whom, at what time. Set `Emails` and `Status` in `outreach/log.md`.
8. Five minutes later, when you can read the mailbox: search for bounces (`from:mailer-daemon`). A bounce → mark that address wrong in `contacts.md`, tell the owner, and propose the next-best pattern: put the new address in `messages.md`, then steps 1 to 6 again with `--only` for that contact (a changed address counts as unsent). Two bounces for one person → stop writing to them.

**Done when** each shown application has `Emails` = the send date or `held` in `log.md`, and the owner has the list.

## What the script refuses, and the branch for each

| `HARD-FAIL` says | Do |
|---|---|
| fails validation | fix `messages.md` (`flow/apply.md` step 6) |
| is on `do-not-contact.md` | set that address to `none`; tell the owner |
| log.md Status is … / no row in log.md | finish the application first (`flow/apply.md` step 2); the row's `Status` must be `submitted` and its `Folder` cell `outreach/<slug>/` |
| a send … was never confirmed | the computer stopped mid-send. The owner looks in their Sent folder for that recipient and tells you whether it went; they then correct `sent.json` with you watching |
| another send is running | wait for it; never start a second one |
| says 'today' but the application went in on another day | write the real day ("on Monday", "last week") |
| was already emailed for another application | tell the owner who and when. They choose: set the address to `none`, or preview with `--repeat-ok` so their page shows the fact |
| would get an email from both … | same person in two applications of one batch: set the address to `none` in one |
| daily cap | send the rest tomorrow, or the owner raises `max_emails_per_day` in `profile.json` |
| wrong code | ask the owner to read the code from their page again; three misses cancel that preview |
| a state file is damaged | show the owner the message; the file stays as it is until they decide |

## Setup (once, during onboarding)

Pick the first option that works and note it in `profile/onboarding.md`.

**A. Script (default, any agent that can run Python).** Works with Gmail and Google Workspace out of the box.
1. The owner turns on 2-Step Verification on their Google account, then creates an app password at `myaccount.google.com/apppasswords` (name it "job outreach"). Tell them first: an app password works like a second password to their whole mailbox, it lives only in the `.env` file on their computer, and deleting it on that same page switches it off at once. A work or school Google account whose administrator has switched app passwords off shows no such page → use a personal Gmail, or option B.
2. In `.env`: `MAIL_ADDRESS=` their address, `MAIL_APP_PASSWORD=` the 16 letters (with or without the spaces Google shows). Another mail provider → also set `SMTP_HOST` and `SMTP_PORT` from that provider's help page.
3. Proof: `python3 scripts/mail.py test <slug>` on the first real application delivers the emails, CV attached, to the owner's own inbox.
Sent mail appears in the owner's Sent folder as usual, and replies arrive in their inbox.

**B. Drafts (no script, or the owner prefers to press send).** Create one draft per contact in the owner's mailbox with a mail tool or in their webmail through the browser, attach the snapshot CV, confirm the attachment is on each draft, and stop. Steps 1 to 4 still happen first; the owner pressing Send is the green light. When a webmail editor rewrites pasted links, check the saved draft's text before stopping. After they send, ask which went out and record it in `log.md`.

**C. Neither.** Give the owner each email as copy-ready text plus the CV path.
