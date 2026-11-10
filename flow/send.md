# Green light and send

The **green light** is the owner's approval, in this conversation, of the exact emails about to go out. It is the only thing that authorises a send.

## Steps

1. For each application waiting to send: `python3 scripts/mail.py preview <slug>`. Paste the full output to the owner: recipient, confidence, subject, attachment, body. For a batch, show every application's preview, then one summary table (company, recipient, confidence).
2. Also show the T3 notes and T4 message; the owner pastes those into LinkedIn themselves.
3. Ask one question: send all, send some, edit, or hold.
4. Read the answer narrowly:
   - Clear approval of everything shown ("send", "yes, send them", "go") → step 5 for all.
   - Approval of some → step 5 for those only; the rest stay held.
   - Any edit request, however small → change `messages.md`, rerun `validate.py`, return to step 1 for that application. The earlier approval is gone.
   - A question, a "looks good" about one paragraph, silence, or anything you have to interpret → ask again. Approval given in an earlier session, or for an earlier application, covers nothing here.
5. Record it, with the owner's own words: `python3 scripts/mail.py approve <slug> --quote "<what they wrote>"`.
6. `python3 scripts/mail.py send <slug>`. The script refuses when the text or CV changed after approval, and when the email was already sent. A refusal is final until its cause is fixed through steps 1 to 5.
7. Tell the owner what went out, to whom, at what time. Set `Emails` and `Status` in `outreach/log.md`.
8. Five minutes later, when you can read the mailbox: search for bounces (`from:mailer-daemon`). A bounce → mark that address wrong in `contacts.md`, tell the owner, and propose the next-best pattern as a new message needing its own green light. Two bounces for one person → stop writing to them.

**Done when** each shown application is `sent` or `held` in `log.md` and the owner has the list.

## Setup (once, during onboarding)

Pick the first option that works and note it under "Setup" in `brief.md`.

**A. Script (default, any agent that can run Python).** Works with Gmail and Google Workspace out of the box.
1. The owner turns on 2-Step Verification on their Google account, then creates an app password at `myaccount.google.com/apppasswords` (name it "job outreach").
2. In `.env`: `MAIL_ADDRESS=` their address, `MAIL_APP_PASSWORD=` the 16 characters. Another mail provider → also set `SMTP_HOST` and `SMTP_PORT` from that provider's help page.
3. Proof: `python3 scripts/mail.py test <slug>` on the first real application delivers both emails, CV attached, to the owner's own inbox.
Sent mail appears in the owner's Sent folder as usual, and replies arrive in their inbox.

**B. Drafts (no script, or the owner prefers to press send).** Create one draft per contact in the owner's mailbox with a mail tool or in their webmail through the browser, attach the snapshot CV, confirm the attachment is on each draft, and stop. Steps 1 to 4 still happen first; the owner pressing Send is the green light. When a webmail editor rewrites pasted links, check the saved draft's text before stopping.

**C. Neither.** Give the owner each email as copy-ready text plus the CV path.
