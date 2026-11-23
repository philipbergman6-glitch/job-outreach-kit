# Capabilities

Test each row by doing it, then record the results in `profile/onboarding.md` (create it) under a "Capabilities" heading.

| Capability | Used for | Test | When absent |
|---|---|---|---|
| Run commands | every script | `python3 --version` prints 3.9 or newer; else try `python --version`, then `py -3 --version` (Windows). Use whichever passed wherever these docs say `python3`. None → Python setup below | Validate messages by reading the rules in `flow/messages.md`; the owner sends from their own mail client |
| Read and write files here | everything | write then delete `profile/.probe` | Stop: this kit needs an agent with file access. Say so and suggest one (Claude Code, Codex, Cursor, Gemini CLI) |
| Web search | finding jobs, people discovery | search for today's date | The owner pastes job links and LinkedIn People-page text |
| Fetch a page | reading job descriptions | fetch `https://example.com` | The owner pastes the job description |
| Drive a browser | submitting application forms | open `https://example.com` in a controlled browser and read its heading | Every application is a handoff: give the owner the link, the field values and the CV path |
| Read the owner's mailbox | prior-contact check, bounce and reply tracking | list the newest message subject | Ask the owner to search their mail for the company name before each application |
| Check a mail server | email confidence without any paid finder | `python3 scripts/emails.py mx gmail.com` prints a provider; `emails.py probe` on a known address says exists, or names port 25 as blocked | Port 25 blocked: the finders in `.env` and the company's pattern carry the verdict, capped lower; say so |
| Send mail | the green-light send | set up in onboarding step 8, proven in step 10 (`flow/send.md` § Setup) | The owner presses send on drafts |

## Python setup

No interpreter passed the test → walk the owner through it, one step at a time:
- **Windows**: download the installer from `python.org/downloads`, tick "Add python.exe to PATH" on its first screen, finish, then close and reopen the assistant. Typing `python3` there may open the Microsoft Store instead; use `python` or `py -3`.
- **macOS**: running `python3` once opens a dialog offering the command line developer tools; the owner clicks Install and waits a few minutes. Or the installer from `python.org/downloads`: that one ships without the certificates Python needs for secure websites, so straight after installing, open the new `/Applications/Python 3.x` folder and double-click `Install Certificates.command` (once per Python version installed this way).

Then prove the internet works from Python: `python3 scripts/jobs.py list greenhouse:anthropic --days 30` prints a line ending in "match", not a `HARD-FAIL` (any public board works; `jobs.py detect <careers link>` names one). A `CERTIFICATE_VERIFY_FAILED` → the certificates step above was skipped; on a work laptop it can also mean the company network inspects secure traffic, so try a home network before anything else. `the internet is blocked` → follow what the line says: a cloud session gets § Cloud session below; any other network, a home network or the VPN off.

## Cloud session

The kit runs on the owner's own computer. A Claude Code cloud session (`CLAUDE_CODE_REMOTE` is `true`, or a script says `the internet is blocked for this session`) has none of their files, no browser they can see, no mailbox, and blocks job sites; allowing sites one by one does not fix the later steps (the CV, the approval page, sending), and the next cloud session starts without anything saved. So never ask the owner to allow sites, change network access or press "Update environment". Tell them this, in their language:

> I'm running on a computer in the cloud instead of yours, so I can't reach job sites or your files. Please:
> 1. In the Claude app, open the **Code** tab and start a new session.
> 2. Under the message box, click the first button (it shows the environment, like "Default" or a name with a cloud icon) and choose your own computer under **Local**.
> 3. Click the folder button next to it and choose the **job-outreach-kit** folder.
> 4. Type **continue**.
>
> If a window asks to update the environment, press **Deny**.

Anything set up during a cloud session stayed there: on the owner's computer, onboarding resumes from what `profile/onboarding.md` on that computer says.

Then run the test again, and `python3 -m unittest discover tests`: `OK` means the scripts work on this computer.

## Browser notes

- Run the browser **headed** (a visible window). Application sites score headless browsers as bots, and the owner needs a window to solve a CAPTCHA or sign in. If your browser tool was started headless, say so and fix its configuration before the first form.
- Use the owner's home connection; data-center and VPN addresses raise fraud scores on application sites.
- Upload files from inside this folder; some browser tools refuse paths outside the project.
- Sites the owner signs into (LinkedIn, job boards, webmail): they type their own password in the visible window, once; the browser profile keeps the session. Passwords stay out of chat and out of files.

## Claude Code fast path

Playwright MCP gives the browser (`claude mcp add playwright -- npx @playwright/mcp@latest --caps=pdf`, no `--headless` flag; `--caps=pdf` adds `browser_pdf_save`, which prints the kit's CV layout, and without it CVs go through the owner as before). It needs Node.js: `node --version` failing → the owner installs the LTS version from `nodejs.org` first. After adding it, the owner quits and reopens Claude Code (type `/exit`, then `claude` again in this folder) so the browser tools load; `/mcp` lists them. The Gmail connector gives mailbox reading and drafts: in the Claude desktop or web app, Settings > Connectors > Gmail > Connect, then it appears in Claude Code too; its send function stays unused. Sending goes through `scripts/mail.py`, which attaches the CV and enforces the green light.
