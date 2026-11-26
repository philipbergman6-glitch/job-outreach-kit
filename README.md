# Job outreach kit

A folder you hand to your AI assistant. It then works as your job-search partner, end to end:

1. **Gets to know you.** It reads your CV and interviews you the way a good career coach would: what you want, why now, what you can prove, what the market pays, where your CV falls short of the jobs you want, and who you already know.
2. **Finds jobs that fit.** It reads companies' job boards directly (posting date, salary and visa wording included) and searches the web. Each job gets a 1-5 score backed by a sentence copied from the posting, so you can see exactly why it was picked or dropped.
3. **Tailors your CV and applies** through the company's official form. For each job it proposes up to three changes that bring your most relevant true facts forward, using the job's own words; you approve each one, and the kit prints the tailored PDF (or, if you keep your CV in your own layout, you save it from your document). You see every filled form before it is submitted.
4. **Finds the people who matter.** The head of the team you would join, the recruiter, and the head of HR: from the posting, the company's own site, semantic web search, public records, and (only if you allow it) your own LinkedIn or job-board account.
5. **Finds their email addresses** without depending on any paid service: the company's published addresses, its email pattern, its public code, and its mail server, plus any free email-finder accounts you add. Each address gets a High / Medium / Low confidence with the evidence behind it.
6. **Writes to them** in your voice, in your language, with your CV attached. Someone you know at the company? It drafts a referral request for you to send first.
7. **Sends only after you say so.** The emails wait in your Drafts folder, your CV attached, and nothing leaves until you open each one, read it and press Send. (Prefer not to open your mail? Optional automatic sending shows the emails on a page in your browser with a code, and nothing leaves until you give your assistant that code.)
8. **Follows up and learns.** It checks for replies, drafts your answer to each, sends one polite nudge after a week, keeps a tracker, and reviews what is working every few replies so the next applications do better.
9. **Prepares you** for each interview: it researches who will interview you, then plays that person in a mock interview (technical with a hands-on expert, conceptual with a manager, plain-language with a recruiter), opening with "tell me about yourself", and debriefs you with a stronger version of each answer. You can practise for any job you applied to, before an invite arrives.

## What you need

- An AI assistant that can work with files on your computer and run commands. Recommended: **Claude Code** (in the Claude desktop app or the terminal; it needs a paid Claude plan). In the desktop app, pick your own computer under **Local** in the environment selector, not a cloud environment: the kit needs your files, your browser and the open internet. Codex, Cursor, Gemini CLI and Grok also work (see **Other assistants** below). A chat-only app can do the interview and the writing; you would then submit and send by hand.
- Your CV, ideally as a PDF. A Word or Google Docs file is fine: your assistant shows you how to save it as a PDF.
- A Gmail account to send from. Your assistant puts each email in your Drafts folder, your CV already attached, and you press Send. For that it needs a Gmail app password, created once in about three minutes (your assistant walks you through it); it stays in a file on your computer. Without one, connect Gmail to your assistant (in Claude: Settings → Connectors → Gmail): the drafts still appear, and you drag your CV into each before sending. Connecting Gmail also lets your assistant spot replies.
- Python 3.9 or newer. Your assistant checks this and walks you through installing it if needed.
- Optional: an email-finder account (Prospeo, Hunter, Apollo and Tomba have free tiers; Anymail Finder and Findymail are paid), a semantic search key (Exa or Brave, both with free monthly credit). The kit works without any of them.
- Optional: your LinkedIn or job-board login. You decide, use by use, what your assistant may do there.

## How long it takes

- **First session, 45 to 60 minutes:** your CV, five key questions, a market reality check, and your first shortlist of real jobs.
- **Second session, 1.5 to 2.5 hours, any later day (you can stop and pick up again):** the full coaching interview, your accounts and permissions, email setup, and your first application with your assistant explaining each step.
- **After that, about 15 to 25 minutes of your time per application:** you approve the CV changes, approve the form, read the emails in your Drafts folder and press Send.

People changing careers, or applying in two languages, should expect the second session at the long end.

## Start

1. On this page click the green **Code** button, then **Download ZIP**. Unzip it and put the folder somewhere you will find it again, such as Documents.
2. Open that folder in your AI assistant (in most apps: "Open folder" or "Open project").
3. Type: **Read AGENTS.md and start my onboarding.**

### Other assistants

Every assistant below reads the same instructions (`AGENTS.md`); the kit behaves the same in each.

- **Codex, Cursor, Gemini CLI:** open the folder and type the sentence in step 3.
- **Grok Build** (xAI's terminal agent, `grok`): open a terminal in the folder, run `grok`, type the sentence in step 3. It reads `AGENTS.md` by itself. Use a current version: builds from before 13 July 2026 uploaded whole project folders to xAI. Your personal files and `.env` (where the app password lives) are excluded from git, which keeps them out of such an upload.
- **Grok Bot** (xAI's bots with their own cloud computer): the kit runs on the bot's computer, not yours, and your files stay there between chats. Send your bot this once, then save it as a skill:
  > Clone https://github.com/philipbergman6-glitch/job-outreach-kit into a folder named job-outreach-kit on your computer. From now on, for anything about my job search, work inside that folder and follow its AGENTS.md exactly. Start my onboarding.

  Then upload your CV in the chat when it asks. Connect Gmail in the bot's plugins (Settings → Plugins → Gmail): it saves drafts, you drag your CV into each and press Send. Keep your Gmail app password off the bot's computer. Job sites distrust logins and form submissions from cloud computers, so with Grok Bot you sign in to LinkedIn and submit applications yourself; the bot gives you a checklist for each.

After onboarding, a few sentences run everything: **"find me jobs"**, **"apply to <link>"**, **"the drafts are sent"**, **"any replies?"**, **"how is it going?"**, **"prepare me for the interview"**, **"practise an interview for <company>"**.

## Updating

The kit is new and changes often. To move to a newer version without losing anything:

- **You downloaded the ZIP:** on this page click **Code**, then **Download ZIP** again, and unzip it next to your current folder. From your old folder, copy three things into the new one: the `profile` folder, the `outreach` folder, and the `.env` file. `.env` is hidden because its name starts with a dot: on a Mac, press Cmd + Shift + . (full stop) in Finder to show it; on Windows, in File Explorer choose View → Show → Hidden items. Then open the new folder in your assistant and type **continue**. Keep the old folder until the first session in the new one works, then delete it. Rather not copy by hand? Open the new folder and tell your assistant where the old one is: "copy my profile, outreach and .env from <old folder>".
- **You cloned it with git:** ask your assistant to run `git pull` in the folder. Your personal files are excluded from git, so they stay as they are.

**Something broke?** Because the kit is new, a step can fail on your computer or a job site can change its form. Tell your assistant what you saw, in your own words ("the form would not submit", "a command printed an error"). It is instructed to stop rather than guess, fixes what it can, and writes what it learned about a site into `playbooks/` so the next run goes better. When it cannot fix it, report it on this page's **Issues** tab.

## Your data

Your CV, your answers, the contacts found and the application history are **stored** only in this folder on your computer (`profile/` and `outreach/`). Both are excluded from git, so they are not uploaded if you push this folder to GitHub. Keys and your Gmail app password live in a file called `.env`, also excluded. The app password opens your whole mailbox, so it belongs only on your own computer: delete it at `myaccount.google.com/apppasswords` and it stops working at once.

What leaves your computer while it works: your AI assistant's provider sees whatever the assistant reads (your CV, your answers, the emails it drafts, any mailbox searches you let it run); an email-finder or search service you add receives the names and company domains it is asked about; a company's mail server is asked whether an address exists (no email is sent); job sites receive your application. Nothing is emailed to anyone until you approve it.

## Good to know

- **The emails are cold emails** to work addresses, about your own application: at most two people per application, and at most one short follow-up a week later. Anyone who asks not to be contacted goes on a do-not-contact list that the kit enforces. There is a daily limit (20 unless you change it).
- **Your accounts, your rules.** LinkedIn's user agreement forbids automated activity on an account and LinkedIn can restrict accounts for it; other sites have similar rules. The kit asks your permission use by use (search jobs, look up people, apply, invite, message), recommends that you click Apply, Connect and Send there yourself, keeps a daily limit per site, and logs every action it takes in `outreach/accounts-log.md`.
- **Checking an address with a mail server** uses port 25, which many home and office networks block. Then the kit relies on the other evidence and says so.
- **You press Send.** Your assistant only saves drafts in your mailbox; nothing leaves until you open a draft and send it. (With the optional automatic sending, a code on a page in your browser plays that role.)
- **The approval code is a safeguard, and you are the other one.** The code lives on a page in your browser and your assistant is instructed never to open it, but an assistant that can read files could technically read that page. Read each email on the preview page before giving the code.

## For the curious

`AGENTS.md` is the entry point your assistant reads. `ONBOARDING.md` is the two-session setup. `flow/` holds the procedures, `playbooks/` what is known about each application site and job source, `scripts/` small Python tools (standard library only, no installs), `tests/` their tests (`python3 -m unittest discover tests`), `examples/` a fictional person's profile and messages.

`scripts/data/employers.tsv`, the list that turns a company name into its job board, comes from the career-ops employer registry under CC BY 4.0; credits are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
