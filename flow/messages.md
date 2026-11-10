# Messages

Four texts per application. Facts come from `profile/profile.json` and `profile/brief.md`; a worked, passing example is `examples/acme-robotics/messages.md`. The owner's "Voice" section in `brief.md` overrides the defaults here wherever they differ, and `profile.json` → `messages` carries those overrides to the validator.

Placeholders: `{First}`, `{Company}`, `{Role}`, `{Apply_channel}` (the careers page, the ATS name, or the site the owner applied on), `{Hook}`, `{Other_contact}`.

## T1 Manager email (120 to 180 words)
Subject from `profile.json`. Greeting → "I applied for the {Role} role via {Apply_channel} today", plus why writing to them directly → one paragraph: the current role line, then `{Hook}` with its number or result → one line on what the owner would bring to this team, tied to something the JD names → credentials line → "CV attached." and the links → ask them to flag the application to the hiring team, offer a short call → closing, full name, phone.

## T2 Recruiter email (120 to 180 words)
Same subject. "I submitted an application for the {Role} role via {Apply_channel} today", offer a short summary → current role line and two hooks by name, each mapped to the JD → degree, years, languages, location, work mode → "CV attached, same version as submitted. I also wrote to {Other_contact}." → links → "Happy to answer any questions." → closing, full name, phone.

## T3 Connection notes (200 characters at most, one per contact)
`Hi {First}, I applied for the {Role} role at {Company} today. {one-line identity with one proof}. I'd be glad to connect.`
The owner pastes these into LinkedIn invites themselves, or you send them in their session when `brief.md` → "LinkedIn" allows invites (`playbooks/ats.md`). A free LinkedIn account allows only a few noted invites a month: the manager's note goes first.

## T4 LinkedIn message to the manager (130 words at most)
For after the invite is accepted. "Thanks for connecting" → applied this week and emailed a summary, keeping it brief → one proof paragraph with the same hook → "the job description describes work I already do" → offer a call → first name only.

## No form existed (channel `email`)
T1 and T2 open with "I am applying for the {Role} role with this email"; everything else unchanged.

## Tone
1. **Apply-first.** Each text opens by saying the application is in and where.
2. The ask sits in the first sentence. Open plainly.
3. One proof paragraph, one hook. A second hook appears only in T2, by name.
4. The current employer is named once, by the current role line, with nothing the owner marked private.
5. A number or a visible result carries the proof paragraph; adjectives carry nothing.
6. The recruiter gets logistics (languages, location, the other contact's name); the manager gets the work.
7. Email signs off with the closing, full name and phone; LinkedIn with the first name.
8. Short declarative sentences ending in periods, in the owner's own vocabulary. `profile.json` lists the banned strings.
9. Dates stay true: when emails go out on a later day than the application, "today" becomes the real day ("on Monday", "last week") before validation.
