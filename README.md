# Job outreach kit

A folder you hand to your AI assistant. It then works as your job-search partner, end to end:

1. **Gets to know you.** It reads your CV and interviews you the way a good career coach would: what you want, why now, what you can prove, what the market pays, where your CV falls short of the jobs you want, and who you already know.
2. **Finds jobs that fit.** It reads companies' job boards directly (posting date, salary and visa wording included) and searches the web. Each job gets a 1-5 score backed by a sentence copied from the posting, so you can see exactly why it was picked or dropped.
3. **Applies** through the company's official form. You see every filled form before it is submitted.
4. **Finds the people who matter.** The head of the team you would join, the recruiter, and the head of HR: from the posting, the company's own site, semantic web search, public records, and (only if you allow it) your own LinkedIn or job-board account.
5. **Finds their email addresses** without depending on any paid service: the company's published addresses, its email pattern, its public code, and its mail server, plus any free email-finder accounts you add. Each address gets a High / Medium / Low confidence with the evidence behind it.
6. **Writes to them** in your voice, in your language, with your CV attached. Someone you know at the company? It drafts a referral request for you to send first.
7. **Sends only after you say so.** The real emails open in your browser with a code. Nothing leaves until you read them and give your assistant that code.
8. **Follows up and learns.** It checks for replies, drafts your answer to each, sends one polite nudge after a week, keeps a tracker, and reviews what is working every few replies so the next applications do better.
9. **Prepares you** when an interview comes, including a mock interview.

## What you need

- An AI assistant that can work with files on your computer and run commands. Recommended: **Claude Code** (in the Claude desktop app or the terminal; it needs a paid Claude plan). Codex, Cursor and Gemini CLI also work. A chat-only app can do the interview and the writing; you would then submit and send by hand.
- Your CV, ideally as a PDF. A Word or Google Docs file is fine: your assistant shows you how to save it as a PDF.
- A Gmail account to send from (another provider works if it offers app passwords; otherwise your assistant prepares drafts and you press Send).
- Python 3.9 or newer. Your assistant checks this and walks you through installing it if needed.
- Optional: an email-finder account (Prospeo, Hunter, Apollo and Tomba have free tiers; Anymail Finder and Findymail are paid), a semantic search key (Exa or Brave, both with free monthly credit). The kit works without any of them.
- Optional: your LinkedIn or job-board login. You decide, use by use, what your assistant may do there.

## How long it takes

- **First session, 45 to 60 minutes:** your CV, five key questions, a market reality check, and your first shortlist of real jobs.
- **Second session, 1.5 to 2.5 hours, any later day (you can stop and pick up again):** the full coaching interview, your accounts and permissions, email setup, and your first application with your assistant explaining each step.
- **After that, about 15 minutes of your time per application:** you approve the form, read the emails, give the code.

People changing careers, or applying in two languages, should expect the second session at the long end.

## Start

1. On this page click the green **Code** button, then **Download ZIP**. Unzip it and put the folder somewhere you will find it again, such as Documents.
2. Open that folder in your AI assistant (in most apps: "Open folder" or "Open project").
3. Type: **Read AGENTS.md and start my onboarding.**

After onboarding, a few sentences run everything: **"find me jobs"**, **"apply to <link>"**, **"send <code>"**, **"any replies?"**, **"how is it going?"**, **"prepare me for the interview"**.

## Your data

Your CV, your answers, the contacts found and the application history are **stored** only in this folder on your computer (`profile/` and `outreach/`). Both are excluded from git, so they are not uploaded if you push this folder to GitHub. Keys and your email app password live in a file called `.env`, also excluded.

What leaves your computer while it works: your AI assistant's provider sees whatever the assistant reads (your CV, your answers, the emails it drafts, any mailbox searches you let it run); an email-finder or search service you add receives the names and company domains it is asked about; a company's mail server is asked whether an address exists (no email is sent); job sites receive your application. Nothing is emailed to anyone until you approve it.

## Good to know

- **The emails are cold emails** to work addresses, about your own application: at most two people per application, and at most one short follow-up a week later. Anyone who asks not to be contacted goes on a do-not-contact list that the kit enforces. There is a daily limit (20 unless you change it).
- **Your accounts, your rules.** LinkedIn's user agreement forbids automated activity on an account and LinkedIn can restrict accounts for it; other sites have similar rules. The kit asks your permission use by use (search jobs, look up people, apply, invite, message), recommends that you click Apply, Connect and Send there yourself, keeps a daily limit per site, and logs every action it takes in `outreach/accounts-log.md`.
- **Checking an address with a mail server** uses port 25, which many home and office networks block. Then the kit relies on the other evidence and says so.
- **The approval code is a safeguard, and you are the other one.** The code lives on a page in your browser and your assistant is instructed never to open it, but an assistant that can read files could technically read that page. Read each email on the preview page before giving the code.

## For the curious

`AGENTS.md` is the entry point your assistant reads. `ONBOARDING.md` is the two-session setup. `flow/` holds the procedures, `playbooks/` what is known about each application site and job source, `scripts/` small Python tools (standard library only, no installs), `tests/` their tests (`python3 -m unittest discover tests`), `examples/` a fictional person's profile and messages.
