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
| Send mail | the green-light send | set up in onboarding step 5, proven in step 7 (`flow/send.md` § Setup) | The owner presses send on drafts |

## Python setup

No interpreter passed the test → walk the owner through it, one step at a time:
- **Windows**: download the installer from `python.org/downloads`, tick "Add python.exe to PATH" on its first screen, finish, then close and reopen the assistant. Typing `python3` there may open the Microsoft Store instead; use `python` or `py -3`.
- **macOS**: running `python3` once opens a dialog offering the command line developer tools; the owner clicks Install and waits a few minutes. Or the installer from `python.org/downloads`.

Then run the test again, and `python3 -m unittest discover tests`: `OK` means the scripts work on this computer.

## Browser notes

- Run the browser **headed** (a visible window). Application sites score headless browsers as bots, and the owner needs a window to solve a CAPTCHA or sign in. If your browser tool was started headless, say so and fix its configuration before the first form.
- Use the owner's home connection; data-center and VPN addresses raise fraud scores on application sites.
- Upload files from inside this folder; some browser tools refuse paths outside the project.
- Sites the owner signs into (LinkedIn, job boards, webmail): they type their own password in the visible window, once; the browser profile keeps the session. Passwords stay out of chat and out of files.

## Claude Code fast path

Playwright MCP gives the browser (`claude mcp add playwright -- npx @playwright/mcp@latest`, no `--headless` flag). It needs Node.js: `node --version` failing → the owner installs the LTS version from `nodejs.org` first. The Gmail connector gives mailbox reading and drafts; its send function stays unused. Sending goes through `scripts/mail.py`, which attaches the CV and enforces the green light.
