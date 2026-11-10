# Capabilities

Test each row by doing it, then record the results in `profile/onboarding.md` (create it) under a "Capabilities" heading.

| Capability | Used for | Test | When absent |
|---|---|---|---|
| Run commands | every script | `python3 --version` prints 3.9 or newer | Validate messages by reading the rules in `flow/messages.md`; the owner sends from their own mail client |
| Read and write files here | everything | write then delete `profile/.probe` | Stop: this kit needs an agent with file access. Say so and suggest one (Claude Code, Codex, Cursor, Gemini CLI) |
| Web search | finding jobs, people discovery | search for today's date | The owner pastes job links and LinkedIn People-page text |
| Fetch a page | reading job descriptions | fetch `https://example.com` | The owner pastes the job description |
| Drive a browser | submitting application forms | open `https://example.com` in a controlled browser and read its heading | Every application is a handoff: give the owner the link, the field values and the CV path |
| Read the owner's mailbox | prior-contact check, bounce and reply tracking | list the newest message subject | Ask the owner to search their mail for the company name before each application |
| Send mail | the green-light send | set up in onboarding step 5, proven in step 7 (`flow/send.md` § Setup) | The owner presses send on drafts |

## Browser notes

- Run the browser **headed** (a visible window). Application sites score headless browsers as bots, and the owner needs a window to solve a CAPTCHA or sign in. If your browser tool was started headless, say so and fix its configuration before the first form.
- Use the owner's home connection; data-center and VPN addresses raise fraud scores on application sites.
- Upload files from inside this folder; some browser tools refuse paths outside the project.

## Claude Code fast path

Playwright MCP gives the browser (`claude mcp add playwright -- npx @playwright/mcp@latest`, no `--headless` flag). The Gmail connector gives mailbox reading and drafts; its send function stays unused. Sending goes through `scripts/mail.py`, which attaches the CV and enforces the green light.
