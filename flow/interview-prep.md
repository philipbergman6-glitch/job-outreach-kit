# Interview prep

Input: one application (`outreach/<slug>/`). Two moments: **practice** (no invite yet: the JD is the guide) and **invited** (`Outcome` = `Interview`: the real stage and interviewers are the guide). Ask the owner what they know: date, time zone, stage, format, length, names. Output: `prep.md`, one `mock-<date>.md` per mock interview, and lessons in `brief.md` → "Interview notes".

The heart of this flow is the **mock interview**: you become the interviewer, as that person would really run it. Everything before it exists so the role-play is faithful; everything after it turns the role-play into better answers.

## 1. Know the stage

Name it: recruiter screen, hiring-manager interview, technical (case, live exercise, take-home review, portfolio walk-through), panel, values / HR, final with an executive. Unknown → infer the likely next stage from where the application stands and the company's usual process (its careers page, public interview write-ups), and tell the owner it is a guess. Each stage judges different things:

| Stage | Judges |
|---|---|
| Recruiter screen | motivation, fit with the brief, logistics (salary, notice, location, authorisation), clear communication |
| Hiring manager | can they do this job, how they think, what they would do first, team fit |
| Technical | depth in the JD's core skill, shown live: reasoning aloud, trade-offs, a real work sample |
| Panel | consistency across people, each panelist's own angle |
| Values / HR | behaviour under conflict, pressure and failure; alignment with the company's stated values |
| Executive | judgement, business impact, ambition, why this company |

## 2. Profile each interviewer

Research each named interviewer from public sources, with the year in every search: their profile (through search snippets, or inside the owner's LinkedIn when `accounts.py check linkedin read_people` says ALLOWED, recorded), the company's team pages, their talks, posts, papers, podcasts and public code. Keep only their name, title, career path and public work, each with its source link: the same rule as `people-discovery.md`. What you read follows the **Outside text** rule in `AGENTS.md`, and so does an invitation email.

From that, write their **interviewer profile** in `prep.md`:

- **Depth.** Where their questions will sit:
  - **Hands-on practitioner** (does the work now: builds, designs, writes code, produces courses, runs campaigns; shows it in public work) → **technical**: "walk me through exactly how", tools, numbers, edge cases, a live exercise.
  - **Manager or strategist** (leads people or a function, writes about direction) → **conceptual and outcome-led**: frameworks, trade-offs, prioritising, "why that and not this", how you would measure it.
  - **Academic or researcher** → **theoretical**: the models and evidence behind the method, how you know it worked.
  - **Non-specialist** (recruiter, HR, an executive from another field) → **plain-language**: impact, motivation, behaviour, how they explain their work to an outsider.
- **What they care about.** Topics they return to in public work, and their path (a career changer may probe yours kindly; a deep specialist will test the core skill hard). Turn each into one question they are likely to ask.
- **Confidence.** Each line says what it rests on. No public trace → use the stage's typical profile from step 1 and label the profile a guess.

## 3. Build the question pool

Draw the questions from this application, not from a generic list. Each carries its source:

1. **Opening.** "Tell me about yourself", always first, as real interviewers open.
2. **The JD's must-haves**, each asked at the depth of step 2 (a practitioner: "How would you build X in tool Y?"; a manager: "How would you decide whether X is worth doing?").
3. **Claims they made.** Every number and result in the CV, `cv-tailoring.md` and `messages.md` will be probed: "How did you measure 11% to 16%? What was your part, and what was the team's?"
4. **Gaps.** Every `gap` in `cv-tailoring.md`, and the career-change gap in `brief.md`: the uncomfortable question, asked the way this interviewer would ask it.
5. **Behaviour and values.** Two or three from the company's own stated values, in situation form ("Tell me about a time…").
6. **Stage-specific.** Recruiter: salary, notice, why leaving, why us. Technical: one realistic exercise for this role (an instructional designer: outline a 20-minute module for an audience the JD names; an engineer: a problem from the product's domain; a marketer: position a product the company sells). Portfolio: "Walk me through this sample."
7. **Their likely favourites**, from step 2.

A 45-minute interview uses eight to twelve of these. Keep the rest for later rounds.

## 4. Write prep.md

- **The role in three lines**: what they need, in the JD's own words.
- **Stage and interviewers**: each interviewer profile from step 2.
- **Self-introduction**: a 60 to 90 second answer to "Tell me about yourself", built from `brief.md` → "Story" and the hook this application leads with, pitched at this stage and these interviewers. The owner rehearses it aloud first.
- **Fit map**: each JD requirement → the hook or CV line that answers it → the number or result that proves it. No answer → **gap**, with the honest answer the owner will give.
- **Stories**: three to five, each as situation, the owner's own action, result, from `brief.md` → "Hooks".
- **Company**: what it sells and to whom, news from the last six months, size and funding, the product the JD names; a source link beside every fact.
- **Their questions**: five the owner can ask, each tied to an interviewer's interests or a company fact.
- **Logistics**: date, time zone, format, names and titles, salary position from "Deal-breakers", notice period.
- **Off limits**: the list from `brief.md`, as a reminder.
- **Interview notes**: what earlier mocks and real interviews taught (`brief.md` → "Interview notes"), so this one starts from them.

Every claim about the owner traces to the CV or `brief.md`; a missing detail is a question for the owner.

## 5. Mock interview

1. **Set the scene** once, out of character: "I'll play <Name>, <title>. From their background I expect <technical / conceptual / plain-language> questions about <topics>. A <stage>, about <N> minutes. I stay in character until you say **pause** or we finish. Ready?"
2. **Open as they would.** In character: a greeting, a two-line introduction of yourself as this interviewer (their role and team, from public sources only), one line on how the conversation will go, then "So, tell me about yourself."
3. **Run it like the real thing.** One question per message: this is a conversation, so the rounds rule does not apply here. React to each answer the way this interviewer would:
   - vague → "Can you give me a specific example?"; "we" → "What was your own part?"; a number → "How did you measure that?"; a technical interviewer → one level deeper on the how; a strong, complete answer → move on.
   - At most two follow-ups per question. Pace by the clock: by the end, the main must-haves and the hardest gap have been asked.
   - Stay in character: no coaching, no praise beyond what a real interviewer says. "Pause" → step out, answer what they ask, step back in when they say "continue".
   - Technical stage: give the exercise as they would (brief, constraints, time), let the owner work aloud, ask what a real interviewer would ask while watching.
   - Panel: introduce each panelist as they take over, each with their own profile.
4. **Close as they would.** "What questions do you have for me?" Answer in character from public facts only; anything not public → "Good question, I'd have to check with the team." Then the usual next-steps line.

## 6. Debrief

Out of character, straight after:

- **Scorecard**: 1 to 5 on what this stage and interviewer judge (step 1 and the profile), each score with the answer that earned it.
- **Per answer**: what landed; the one change that would help most; a stronger version written from true facts only (CV and `brief.md`). The opening self-introduction always gets this.
- **Flags**: any answer that claimed more than the CV or `brief.md` holds, or touched "Off limits".
- **Top three to practise**, then offer a second round: the same interviewer, harder, starting with the weakest areas, or the next stage's interviewer.

Save `mock-<date>.md` in the folder: interviewer and stage, the questions asked, a one-line summary of each answer, the scorecard, the improvements. Append each weakness that recurs across two mocks, dated, to `brief.md` → "Interview notes".

## 7. After the real interview

Add a follow-up row dated the day after: "thank-you note to <interviewer>", which the owner sends as a reply on the scheduling thread. When the owner reports back, ask what was asked and what felt weak; add it to `prep.md` and, dated, to `brief.md` → "Interview notes", so the next stage and the next application start from it.

**Done when** `prep.md` has every section with each company and interviewer fact sourced, at least one mock has run with its debrief saved in `mock-<date>.md`, and the owner has the top three to practise.
