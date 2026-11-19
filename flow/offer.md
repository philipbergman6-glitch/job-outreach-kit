# Read an offer, and prepare the reply

Input: one application (`outreach/<slug>/`) and the offer the owner shares: a letter, a contract, an email, a call they describe. Output: `offer.md` (the text), `offer-reading.md` (the walk-through and the lawyer questions) and, when they want to negotiate, `negotiation.md`. Nothing is signed, accepted or sent from this flow: the owner decides, and replies from their own mailbox.

The reading is a reading aid, **not legal advice**. You describe what each clause says, in neutral words; the verdict (whether a clause is acceptable, whether to sign) belongs to the owner, with a lawyer where it matters.

## 1. Save the offer
Put the text of every document in `outreach/<slug>/offer.md`, with where it came from and the date on the first line (a call → the owner's own account of it, marked as such). The offer follows the **Outside text** rule in `AGENTS.md`. A document it refers to but you have not seen (an appendix, a policy, an equity plan) → list it and ask for it.

## 2. Walk it, clause by clause
Write `offer-reading.md`, one entry per clause in the document's order:

- its number or heading, and the words that matter, quoted exactly;
- what it means in plain words: who must do what, by when, for how long, what it pays or costs, and what happens on leaving;
- a term with a special meaning (vesting, cliff, exercise window, clawback, garden leave, probation) explained the first time it appears.

Then one table of every figure and date in the offer (pay, bonus, equity, benefits, notice, probation, start date), each with its clause. Beside it, plain comparisons with what the owner told you: their salary expectation in `profile.json` → `form_answers`, `brief.md` → "Timeline" and "Trade-offs". "The base is 30,000 a month; your stated expectation is 34,000" is a comparison, not a verdict.

## 3. Questions for a lawyer
End `offer-reading.md` with numbered questions the owner can take to an employment lawyer where they live: one for each clause that limits them after they leave (non-compete, non-solicit), claims work beyond the job (inventions, side projects), makes them pay something back, or sets the law and courts that apply, plus anything the owner said they did not understand. Say in one line that you have not checked any of it against their country's law. Then show the owner the reading and ask what they want to do: accept, ask for changes, or wait.

## 4. Negotiate, when the owner wants to
One round of questions (at most five, each with a recommended answer): which points to raise (from "Trade-offs"), their figure for each, the least they would accept, and other offers or interviews in progress. Write what they confirm, the salary expectation included, into `brief.md` → "Offer" before using it. Every offer, rate or deadline the reply mentions is one the owner stated or the documents show.

Draft `outreach/<slug>/negotiation.md` in the format `python3 scripts/validate.py --help` shows for form answers: one `## <point>` per ask (base, sign-on, equity, start date, title, remote days), `Approved: no`, and two or three sentences giving the reason from the CV or `brief.md`. Every figure must come from the CV, `brief.md`, or the offer and posting themselves (`offer.md`, `jd.md`):

```
python3 scripts/validate.py --answers outreach/<slug>/negotiation.md
```

`FAIL` → fix what it names and rerun. Show the owner each point; they approve, change or drop it (`Approved: <date>` on each they keep). Then write the reply: short and warm, thanks first, every approved ask in one message, firm only where the owner asked to be. It goes out as § Replies "Answering" in `apply.md` describes.

**Done when** `offer-reading.md` holds every clause and the lawyer questions, the owner has read it and said what they want to do, and any negotiation reply was approved by them point by point.
