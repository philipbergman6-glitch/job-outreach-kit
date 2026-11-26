# Green light and send

The **green light** is the owner's approval of the exact emails about to go out. It is the only thing that authorises a send, and its proof is a code only the owner can see.

## Steps

These steps are the script route (§ Setup A). On the drafts route (§ Setup B, the default), follow B's steps instead; the refusal table below applies to both.

1. Preview everything waiting to send in one command: `python3 scripts/mail.py preview <slug> [<slug> ...]`. It prints each email (recipient, confidence, subject, attachment, body) and opens the owner's **preview page** in their browser with the same emails and a one-time approval code. The page did not open → give the owner the file path the script printed and ask them to open it.
2. Paste the printed emails into chat too, with one summary table for a batch (company, recipient, confidence). Also show the T3 notes and T4 message: the owner pastes those into LinkedIn themselves, unless `accounts.py check linkedin invites` says ALLOWED (`playbooks/ats.md`).
3. Ask one question: send all, send some, edit, or hold. Tell them the page shows what to type to send.
4. Read the answer narrowly:
   - The owner gives the code from their page ("send 482913") → step 5.
   - Approval without the code ("yes, send them", "go") → ask for the code on the page; it is how the script knows they read it.
   - Approval of some applications, or of one email of a pair → preview again with only those (`--only hm` or `--only rec` for one email of one application; `--only checkin` for a K1 check-in, `flow/messages.md`); the rest stay held.
   - Any edit request, however small → change `messages.md`, rerun `validate.py`, return to step 1. A new preview replaces the earlier page, code and approval. When the edit is about wording or tone, not a fact, also save it as a rule so later drafts need no fix: one dated line in `brief.md` → "Voice" → "Learned from edits" (e.g. "2026-11-17: opens with the role, no warm-up sentence"); a word or phrase they never want → add it to `profile.json` → `messages` → `banned` as well, so `validate.py` enforces it. Read "Learned from edits" before drafting every message.
   - Hold, or a change of mind after giving the code → `python3 scripts/mail.py cancel`.
   - A question, a "looks good" about one paragraph, silence, or anything you have to interpret → ask again. Approval given in an earlier session, or for an earlier preview, covers nothing here.
5. Record it: `python3 scripts/mail.py approve --code <the code they gave> --quote "<what they wrote>"`. It covers exactly what that preview showed.
6. `python3 scripts/mail.py send <slug> [<slug> ...]`, straight away. An approval works once and for 30 minutes. A refusal is final until its cause is fixed and steps 1 to 5 are repeated; an SMTP failure is reported to the owner and retried only through this script: `mail.py status <slug>` shows what went, and the retry names only the applications with something left.
7. Tell the owner what went out, to whom, at what time. Record it: `python3 scripts/tracker.py status <slug> sent --set "Emails=<the date the first emails went>"` (a nudge changes neither); emails held → `tracker.py status <slug> submitted --set "Emails=held"`.
8. Five minutes later, when you can read the mailbox (`accounts.py record <mail site> mailbox "bounce check"` first): search for bounces (`from:mailer-daemon`). A bounce → mark that address wrong in `contacts.md`, tell the owner, and propose the next-best pattern: put the new address in `messages.md`, then steps 1 to 6 again with `--only` for that contact (a changed address counts as unsent). Two bounces for one person → stop writing to them.

**Done when** each shown application has `Emails` = the send date or `held` in `log.md`, and the owner has the list.

## What the script refuses, and the branch for each

| `HARD-FAIL` says | Do |
|---|---|
| fails validation | fix `messages.md` (`flow/apply.md` step 6) |
| is on `do-not-contact.md` | set that address to `none`; tell the owner |
| log.md Status is … / no row in log.md | finish the application first (`flow/apply.md` step 2); the row's `Status` must be `submitted` or `sent` and its `Folder` cell `outreach/<slug>/` (channel `email` has no form, so no row is checked) |
| a send … was never confirmed | the connection broke or the computer stopped mid-send. The owner looks in their Sent folder for that recipient and tells you whether it is there. Record their answer: `python3 scripts/mail.py confirm <slug> <key> --went --quote "<their words>"` (it is there: it counts as sent) or `--not-sent` (it is not: preview and green light again to send it). Nobody edits `sent.json` by hand |
| a draft of this email … was saved in the owner's Drafts | the drafts route saved it (`mail.py draft`). The owner looks in Sent: sent → record it (§ Setup B step 5), nothing to send; not sent → they delete the draft, then preview with `--drafted-unsent --only <key>` |
| sent.json changed while this batch was going | another run or a repair recorded that email mid-batch; it was not sent again. `mail.py status <slug>`, tell the owner |
| another send is running | wait for it; never start a second one |
| says 'today' but the application went in on another day | write the real day ("on Monday", "last week") |
| was already emailed for another application | tell the owner who and when. They choose: set the address to `none`, or preview with `--repeat-ok` so their page shows the fact |
| would get an email from both … | same person in two applications of one batch: set the address to `none` in one |
| daily cap | send the rest tomorrow, or the owner raises `max_emails_per_day` in `profile.json` |
| wrong code | ask the owner to read the code from their page again; three misses cancel that preview |
| a state file is damaged | show the owner the message; the file stays as it is until they decide |

## Setup (once, during onboarding)

Use **B** (drafts; the owner presses Send) unless the owner wants emails to leave without opening their mail (**A**); with no way to save drafts, **C**. Note the choice in `profile/onboarding.md`, with how drafts are saved:
- **B1, by the script (recommended):** `mail.py draft` saves every draft with the CV attached, any size, and checks it byte for byte. It needs a Gmail app password once (the app password steps below: steps 1 and 2 of A).
- **B2, by a connected mail tool:** no password, but the tool attaches only a CV of 30 KB or less (most CVs are larger); otherwise the owner drags the CV into each draft.

Explain it to the owner in plain words and let them choose: "With a one-time app password (about three minutes), every draft has your CV attached automatically. Without it, I still write the drafts, and you drag your CV into each one before sending." On a hosted assistant's computer (Grok Bot and the like) use B2: an app password stays on the owner's own computer.

Connecting a mail tool, in plain words for the owner: in the Claude desktop or web app, Settings → Connectors → Gmail → Connect, and sign in with Google (Claude Code then sees it too). Other assistants have their own connector or plugin settings; when yours has none, B2 still works through their webmail in the browser you control (`playbooks/ats.md` § Webmail drafts). Test: list the newest message subject, then save one draft to the owner's own address and delete it. On B1 too, a connected mail tool is what reads replies and bounces.

**The app password (B1 and A).** Works with Gmail and Google Workspace out of the box.
1. The owner turns on 2-Step Verification on their Google account, then creates an app password at `myaccount.google.com/apppasswords` (name it "job outreach"). Tell them first: an app password works like a second password to their whole mailbox, it lives only in the `.env` file on their computer, and deleting it on that same page switches it off at once. A work or school Google account whose administrator has switched app passwords off shows no such page → use a personal Gmail, or B2.
2. Create `.env` from `.env.example` if it is missing and open it for them (macOS `open -e .env`, Windows `notepad .env`). They fill `MAIL_ADDRESS=` with their address and `MAIL_APP_PASSWORD=` with the 16 letters (with or without the spaces Google shows), and save. Another mail provider → also `SMTP_HOST` and `SMTP_PORT` (A), or `IMAP_HOST` and `IMAP_PORT` (B1), from that provider's help page.
3. Proof: B1 → `python3 scripts/mail.py draft <slug>` on the first real application (B step 3) puts the drafts in their Drafts folder; they open one and see the CV. A → `python3 scripts/mail.py test <slug>` delivers the emails, CV attached, to their own inbox.

**A. Script (automatic sending, approved with a code).** The app password above, then the Steps at the top of this file. Sent mail appears in the owner's Sent folder as usual, and replies arrive in their inbox.

**B. Drafts (default: the owner presses Send).** There is no preview page and no code; the owner reading each draft in their own mailbox and pressing Send is the green light.
1. `python3 scripts/mail.py check <slug> [<slug> ...]` (`--only <key>` for one email). It applies every refusal the script route has (table above) and prints the emails; it writes nothing and needs no `.env`. A `HARD-FAIL` → the table's branch.
2. Show the printed emails in chat (step 2 above) and ask: draft all, some, edit, or hold. An edit → `messages.md`, `validate.py`, back to 1.
3. **B1:** `python3 scripts/accounts.py record <mail site> mailbox "drafts for <slug>"`, then `python3 scripts/mail.py draft <slug> [<slug> ...]` with the same `--only` as step 1. It applies the same refusals again, saves each email in the Drafts folder with the CV attached (a nudge or CV follow-up as a reply on the first email's thread), reads each back, and prints `checked byte for byte` per draft. It records each saved draft in `outreach/<slug>/drafted.json`, a state file only the script writes (never open or edit it). Rerunning after a failure is safe: a recorded draft still in Drafts is checked again and left alone. A draft that reads back different is a `HARD-FAIL` naming it: the owner deletes that draft, then rerun. `is no longer in Drafts` → the owner has probably sent it: ask them to look in Sent; sent → step 5; deleted unsent → rerun with `--drafted-unsent`. `mail.py did not save it` → a draft with that recipient and subject is already there from another route (or from before the record existed): the owner opens it and sends or deletes it, then rerun. `is still in Drafts, unsent` → another reply on the same thread (a nudge and a CV follow-up share a subject) waits: the owner sends or deletes that one first. A refused login → the app password is wrong or was deleted: steps 1 and 2 of the app password again. **B2:** for each email `check` printed: `python3 scripts/accounts.py record <mail site> mailbox "draft to <name>"`, then save a draft with exactly the printed To, Subject and body, and the attachment it names (the file in `outreach/<slug>/`; `check` prints its size). Attach through the mail tool when the file is 30 KB or less, then confirm it: download the draft's attachment and compare its SHA-256 with the file's (`shasum -a 256`; `playbooks/ats.md` § Mail connectors: a raw read-back misreports attachments). A larger file, or an attachment that does not match → save the draft without it, show the owner the file (macOS `open -R <file>`, Windows `explorer /select,<file>`), and ask them to drag it into each draft you name. A nudge or CV follow-up goes as a reply on the thread of the first email (the mail tool's reply-to field with that email's id). Read each draft back: text unchanged, attachment present. A draft saved through a mail connector carries no links (the Gmail connector turns every link into a Google redirect): leave a link out, and tell the owner which link to type into which draft. A draft the tool cannot attach to → save it without, and tell the owner, for that draft by name, which file to drag into it before sending.
4. Tell the owner: how many drafts are in their Drafts folder, to whom, and that nothing has gone: they open each, read it, and press Send. Never send a draft yourself.
5. Record what went. When they say they sent (or at the next session's reply check): find each in their Sent folder, take the date and the Message-ID header (the raw message shows it), and write `hm_sent: <date> <Message-ID>` / `rec_sent: …` in that application's `messages.md`. From then on every rule counts it as sent: one email per person, one nudge per person, the daily cap, and nudges reply on its thread. Until then a draft the script saved already counts for one email per person and one nudge per person, and the script route (`preview`, `send`) refuses that email, since the owner may have sent it from Drafts: if they deleted it unsent, preview with `--drafted-unsent`. A nudge sent from Drafts needs no record: the script never offers it again. Then record it with `tracker.py status <slug> sent --set "Emails=<date>"` (step 7 above). A draft still unsent a day later → ask once whether to hold it.

**C. Neither.** Give the owner each email as copy-ready text plus the CV path.
