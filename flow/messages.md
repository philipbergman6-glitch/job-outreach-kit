# Messages

Four texts per application, plus an optional nudge later. Facts come from `profile/profile.json` and `profile/brief.md`; a worked, passing example is `examples/acme-robotics/messages.md`. The owner's "Voice" section in `brief.md` (their samples and every "Learned from edits" rule) overrides the defaults here wherever they differ, and `profile.json` → `messages` carries those overrides to the validator.

Placeholders: `{First}`, `{Company}`, `{Role}`, `{Apply_channel}` (the careers page, the ATS name, or the site the application went through), `{Hook}`, `{Other_contact}`.

Each template is a sequence of moves. Write a move only as far as it is true for this application; the notes in brackets say what to check.

## T1 Manager email (120 to 180 words)
Subject from `profile.json`. Greeting → "I applied for the {Role} role via {Apply_channel} today", plus why writing to them directly [person confidence High: "the role sits in your team"; Medium: "I understand the role sits in your team"] → one paragraph: the current role line, then `{Hook}` with its number or result [a career change: one bridge sentence from `brief.md` → "Career change", naming what carries over and nothing more] → one line on what the owner would bring to this team, tied to something the JD names → credentials line → "CV attached." and the links → ask them to flag the application to the hiring team, offer a short call → closing, full name, phone.

## T2 Recruiter email (120 to 180 words)
Same subject. Goes to the recruiter, or to the head of HR when they hold the recruiter slot (`people-discovery.md`); for a head of HR, the why-you line is "as the person who leads hiring at {Company}". "I submitted an application for the {Role} role via {Apply_channel} today", offer a short summary → current role line and two hooks by name, each mapped to the JD → degree, years, languages, location, work mode → "CV attached." [add "same version as submitted" only when this exact file was the one uploaded] "I also wrote to {Other_contact}." [only when T1 is going out] → links → "Happy to answer any questions." → closing, full name, phone.

## T3 Connection notes (200 characters at most, one per contact)
`Hi {First}, I applied for the {Role} role at {Company} today. {one-line identity with one proof}. I'd be glad to connect.`
The owner pastes these into LinkedIn invites themselves, or you send them in their session when `accounts.py check linkedin invites` says ALLOWED (`playbooks/ats.md`). A free LinkedIn account allows only a few noted invites a month: the manager's note goes first.

## T4 LinkedIn message to the manager (130 words at most)
For after the invite is accepted. "Thanks for connecting" → applied this week and emailed a summary [only if T1 went out], keeping it brief → one proof paragraph with the same hook → one line tying that hook to what the JD asks for [a stretch role: name what carries over, claim nothing more] → offer a call → first name only.

## N1 / N2 Nudge (15 to 90 words, optional, a week after the first email)
Greeting → "I wrote last week about the {Role} role" → still interested, plus one new fact when there is one (a result, a launch, a relevant change at their company) → offer a short call → closing, full name, phone. One nudge per person, ever.
When `profile.json` → `nudge_attaches_cv` is `true`, the nudge carries the snapshot CV too.

## C1 / C2 CV follow-up (15 to 90 words, only for a first email sent outside `mail.py` without the CV)
When the owner sent T1 or T2 by hand (or another tool sent it) and the CV was missing, record that email in the front matter: `hm_sent: YYYY-MM-DD <Message-ID>` (`rec_sent` for T2; the Message-ID header is in the sent email's original source). `mail.py` then treats that first email as sent, and nudges reply to it. The follow-up goes as a reply on that thread with the CV attached: greeting → following up on the earlier email about the {Role} role → "CV attached" and the links → closing, full name, phone. No apology longer than half a sentence, nothing new to claim. Once per person.

## K1 Check-in (15 to 90 words, optional, a reply on a thread the company started)
After an interview, or any email someone at the company wrote first (an invite, a question), when an answer is overdue. Front matter: `checkin_name`, `checkin_email`, `checkin_email_confidence` (High or Medium) and `checkin_reply_to: <Message-ID>` of their email (from its original source). The section starts `Subject: Re: <their subject>`, so it lands in their thread. Greeting → thanks for the step that happened (the interview, with whom, on which day) → still interested → asks for an update on next steps → closing, full name, phone. It goes to the person who runs the process (usually the recruiter who sent the invite), not around them to the interviewer. `mail.py preview <slug> --only checkin`; it carries the CV when `nudge_attaches_cv` is `true`. The next check-in to the same person waits a week; replace the text and `checkin_reply_to` when the thread moves on.

## R1 Referral ask (owner sends it personally, 80 words at most)
For someone the owner knows at the company (`brief.md` → "Network"). Their first name → the role and link → why the owner fits, one line with the hook → "Would you be open to referring me, or telling me who leads that team?" → no pressure line → first name. It goes from the owner's own phone or account, not through `mail.py`; the validator does not check it. Write it in `messages.md` under `## R1 referral ask` only when asked; the application then waits for the owner's word before T1 and T2 go out.

## Language
`messages.md` front matter `language: <name>` selects that language's rules from `profile.json` → `languages` (greeting, closing, subject, opener, attachment phrase, "today"). Write every text in that language. Hooks appear under their `hook_names` for that language (the front matter `hook:` keeps the name from `profile.json` → `hooks`); the current role line stays exactly as in `profile.json`. Absent, the main `messages` rules apply.

## No form existed (channel `email`)
T1 and T2 open with "I am applying for the {Role} role with this email"; everything else unchanged. When the address is one the company published for applications (a `jobs@` under the form) it takes the recruiter slot: `rec_name: Hiring Team`, greeting "Hi Hiring Team,", email confidence High, and the recruiter's T3 section is `none`.

## A contact with no usable address
Name known, email `none` (Low confidence, bounced twice, or on the do-not-contact list): their T1 or T2 section is the single word `none`; their LinkedIn texts are written as usual.

## A contact nobody could find
`hm_name: none` or `rec_name: none`, their email `none`, and the single word `none` as the body of each of their sections. The other contact's texts drop the "I also wrote to" line.

## Tone
1. **Apply-first.** Each text opens by saying the application is in and where.
2. The ask sits in the first sentence. Open plainly.
3. One proof paragraph, one hook. A second hook appears only in T2, by name.
4. The current employer is named once, by the current role line, with nothing the owner marked private.
5. A number or a visible result carries the proof paragraph; adjectives carry nothing.
6. The recruiter gets logistics (languages, location, the other contact's name); the manager gets the work.
7. Email signs off with the closing, full name and phone; LinkedIn with the first name.
8. Short declarative sentences ending in periods, in the owner's own vocabulary. `profile.json` lists the banned strings.
9. Dates stay true: `applied:` in the front matter is the day the application went in. When emails go out on a later day, "today" becomes the real day ("on Monday", "last week"); `mail.py` refuses a "today" that is no longer true.
