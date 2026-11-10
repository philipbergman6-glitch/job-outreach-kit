# Job outreach kit

A folder you hand to your AI assistant. It then works as your job-search partner:

1. **Gets to know you.** You give it your CV and it interviews you about what you want.
2. **Finds jobs** that match, and shows you a shortlist.
3. **Applies** through the company's official form (you approve each form before it is submitted).
4. **Finds the two people who matter**: the hiring manager and the recruiter, and their email addresses.
5. **Writes to them** in your voice, with your CV attached.
6. **Sends only after you say so.** You read every email first. Nothing leaves without your green light.
7. **Keeps a tracker** of every application and reply.

## What you need

- An AI assistant that can work with files on your computer and run commands: Claude Code, Codex, Cursor, Gemini CLI or similar. A chat-only app can do the interview and the writing, and you would submit and send by hand.
- Your CV, as a PDF if you have one.
- A Gmail (or other) email account to send from.
- About 30 to 45 minutes for the first session.

## Start

1. Download this folder to your computer.
2. Open it in your AI assistant.
3. Type: **Read AGENTS.md and start my onboarding.**

After onboarding, three sentences run everything: **"find me jobs"**, **"apply to <link>"**, **"send"**.

## Your data

Your CV, your answers, the contacts found and the application history are **stored** only in this folder on your computer (`profile/` and `outreach/`). Both are excluded from git, so they are not uploaded if you push this folder to GitHub. Your email app password and API key live in a file called `.env`, also excluded.

What leaves your computer while it works: your AI assistant's provider sees whatever the assistant reads (your CV, your answers, the emails it drafts, any mailbox searches you let it run); Hunter receives the names and company domains of people it looks up; job sites receive your application. Nothing is emailed to anyone until you approve it.

## For the curious

`AGENTS.md` is the entry point your assistant reads. `flow/` holds the procedures, `playbooks/` what is known about each application site, `scripts/` small Python tools (standard library only, Python 3.9+), `examples/` a fictional person's profile and messages.
