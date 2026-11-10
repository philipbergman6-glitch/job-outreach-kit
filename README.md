# Job outreach kit

A folder you hand to your AI assistant. It then works as your job-search partner:

1. **Gets to know you.** You give it your CV and it interviews you about what you want.
2. **Finds jobs** that match, and shows you a shortlist.
3. **Applies** through the company's official form (you approve each form before it is submitted).
4. **Finds the two people who matter**: the hiring manager and the recruiter, and their email addresses.
5. **Writes to them** in your voice, with your CV attached.
6. **Sends only after you say so.** The real emails open in your browser with a code. Nothing leaves until you read them and give your assistant that code.
7. **Follows up**: checks for replies, drafts one polite nudge after a week, and keeps a tracker of every application.
8. **Prepares you** when an interview comes.

## What you need

- An AI assistant that can work with files on your computer and run commands: Claude Code, Codex, Cursor, Gemini CLI or similar (their desktop apps count). A chat-only app can do the interview and the writing, and you would submit and send by hand.
- Your CV, as a PDF if you have one.
- A Gmail account to send from (another provider works if it offers app passwords; otherwise the assistant prepares drafts and you press send).
- Python 3.9 or newer. Most Macs offer to install it the first time it is needed; on Windows it comes from python.org. Your assistant checks this and walks you through it.
- Optional: your LinkedIn. You decide during setup whether your assistant may search jobs and check people inside your signed-in LinkedIn, or works from public sources only.
- About 30 to 45 minutes for the first session.

## Start

1. On this page click the green **Code** button, then **Download ZIP**. Unzip it and put the folder somewhere you will find it again, such as Documents.
2. Open that folder in your AI assistant (in most apps: "Open folder" or "Open project").
3. Type: **Read AGENTS.md and start my onboarding.**

After onboarding, a few sentences run everything: **"find me jobs"**, **"apply to <link>"**, **"send <code>"**, **"any replies?"**, **"prepare me for the interview"**.

## Your data

Your CV, your answers, the contacts found and the application history are **stored** only in this folder on your computer (`profile/` and `outreach/`). Both are excluded from git, so they are not uploaded if you push this folder to GitHub. Your email app password and API key live in a file called `.env`, also excluded.

What leaves your computer while it works: your AI assistant's provider sees whatever the assistant reads (your CV, your answers, the emails it drafts, any mailbox searches you let it run); Hunter receives the names, company domains and email addresses it is asked to look up or check; job sites receive your application. Nothing is emailed to anyone until you approve it.

## Good to know

- **The emails are cold emails** to work addresses, about your own application: one to each person, and at most one short follow-up a week later. Anyone who asks not to be contacted goes on a do-not-contact list that the kit enforces. There is a daily limit (20 unless you change it).
- **LinkedIn does not allow automated activity** on an account and can restrict accounts for it. The kit asks your permission use by use, and its default advice is to let the assistant read and to click Apply and Connect yourself.
- **The approval code is a safeguard, and you are the other one.** Read each email on the preview page before giving the code.

## For the curious

`AGENTS.md` is the entry point your assistant reads. `flow/` holds the procedures, `playbooks/` what is known about each application site, `scripts/` small Python tools (standard library only), `tests/` their tests, `examples/` a fictional person's profile and messages.
