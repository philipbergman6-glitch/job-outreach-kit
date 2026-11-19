#!/usr/bin/env python3
"""Check a job shortlist before the owner sees it, and remember the jobs they pass on. Stdlib only.

Usage:
  triage.py check <outreach/triage-YYYY-MM-DD.md> [--jobs-dir outreach/jobs] [--days 30]
        PASS (exit 0) or the list of problems (exit 1). Checks that every kept job has a 1-5
        score that matches its tier, a posting no older than --days (or "unknown"), a saved
        job-description file, and a quote copied word for word from that file proving the
        score; that every dropped job quotes the sentence that ruled it out; and that no row
        is a job already applied to (log.md) or already passed on (passed.md), and that no kept
        job's posting asks the candidate to pay (a fee, a deposit, a starter kit).
  triage.py pass <link> "<reason>"
        record that the owner passed on a job, so later searches skip it.
  triage.py format
        print the shortlist format.

Quotes are compared after folding case, spacing, curly quotes and dashes, so a line break or
a typographic apostrophe does not count as a paraphrase; a changed word does. A quote is at
least 3 words: a fragment proves nothing. JD file is a bare file name inside --jobs-dir.
Exit 2 = hard-fail (bad input)."""
import re
import sys
from datetime import date
from pathlib import Path

from _common import ROOT, die, run

FORMAT = """# Triage <YYYY-MM-DD>: <sources searched>, <N> postings read, <M> kept

## A: direct fit
| # | Company | Role | Location | Posted | Salary | Visa | Score | Apply path | Link | JD file | Why it fits | Quote |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Acme | AI Engineer | Tel Aviv, hybrid | 2026-11-10 | not stated | - | 5 | greenhouse | https://... | acme-123.md | Agents Platform hook | "build LLM agents in Python" |

## B: adjacent title or one gap
(same columns; Score 3)

## C: stretch
(same columns; Score 2)

## Dropped
| Company | Role | Link | JD file | Reason | Quote |
|---|---|---|---|---|---|
| Beta | Engineer | https://... | beta-9.md | deal-breaker: on-site 5 days | "5 days a week in our office" |
| Gamma | Analyst | https://... | - | already applied | - |

Tiers: A = Score 4 or 5, B = 3, C = 2. A job scoring 1 is dropped, with its quote.
Reasons that need no quote: already applied, passed before, stale, duplicate, closed,
no trusted source.
A kept row's Link is a trusted source (the company's careers site or ATS board, LinkedIn, or a board
playbooks/sources.md marks trusted), never a broad board or an aggregator: those hold reused, edited
and expired postings. A job found on no trusted source is Dropped as "no trusted source".
A posting that asks the candidate to pay (a fee, a deposit, a kit) is Dropped as
"scam: asks the candidate to pay", with the sentence as the quote."""
TIERS = {"A": (4, 5), "B": (3, 3), "C": (2, 2)}
MIN_QUOTE_WORDS = 3
KEPT_COLS = ["#", "Company", "Role", "Location", "Posted", "Salary", "Visa", "Score", "Apply path", "Link",
             "JD file", "Why it fits", "Quote"]
DROP_COLS = ["Company", "Role", "Link", "JD file", "Reason", "Quote"]
NO_QUOTE = ("already applied", "passed before", "stale", "duplicate", "closed", "no trusted source")
# Broad boards and aggregators: places to discover a job, never its link of record. They reuse a
# job's number for another role, keep expired postings, and put a CAPTCHA or login before the employer.
BROAD_BOARDS = ("drushim.co.il", "alljobs.co.il", "jobmaster.co.il", "indeed.com",
                "glassdoor.com", "glassdoor.co.uk", "jooble.org", "ziprecruiter.com", "simplyhired.com",
                "talent.com", "adzuna.com")


def broad_board(link):
    """The broad board a link points to, or None."""
    host = re.sub(r"^https?://", "", link.strip().lower()).split("/")[0].split(":")[0]
    return next((b for b in BROAD_BOARDS if host == b or host.endswith("." + b)), None)
PASSED = ROOT / "outreach" / "passed.md"
# A posting that asks the candidate to pay to get the job is a known recruiting-scam pattern.
# Narrow on purpose: the sentence must address the candidate and ask them for money.
WHO = re.compile(r"\b(you|your|candidates?|applicants?|trainees?|new hires?|participants?)\b", re.I)
NOT_MONEY = r"(?!\s+((close|careful|special|particular)\s+)?(attention|heed|tribute|respect|off\b|into\b|in\b))"
ASK = re.compile(r"\b(must|needs? to|(are|is|be) required to|ha(ve|s) to)\s+(first\s+)?(pay|purchase|buy|deposit)\b"
                 + NOT_MONEY + r"|\bwill be charged\b(?!\s+with\b)|\bat (your|their) own (cost|expense)\b", re.I)
FEE = re.compile(r"\b(registration|training|onboarding|placement|certification|enrol?lment|background[- ]check|"
                 r"uniform|equipment|application)\s+(fees?|costs?)\b|\b(refundable|security)\s+deposit\b|"
                 r"\bstarter[- ]kit\b|\bone-time\s+(fee|payment)\b", re.I)
PAY = re.compile(r"\b(pay|paid|payable|charged?|deposit|purchase|buy)\b", re.I)
EMPLOYER_PAYS = re.compile(r"\b(we|the company|our company|employer)\s+(will\s+)?(cover|pay|reimburse|provide|fund)s?\b|"
                           r"\bat no cost\b|\bfree of charge\b|\bno (fees?|cost)\b", re.I)


def candidate_pays(text):
    """The first sentence in which the posting asks the candidate to pay, or None."""
    for s in re.split(r"(?<=[.!?])\s+|\n+", text):
        if WHO.search(s) and not EMPLOYER_PAYS.search(s) and (ASK.search(s) or (FEE.search(s) and PAY.search(s))):
            return s.strip()
    return None


def fold(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―−]", "-", s).replace("­", "").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


def quotes(cell):
    """The quoted passages in a cell: text between straight or curly double quotes, or the
    whole cell when it has none."""
    found = re.findall(r"[\"“](.+?)[\"”]", cell)
    return found or ([cell.strip()] if cell.strip() and cell.strip() != "-" else [])


TRACKING = re.compile(r"(utm_\w+|gh_src|src|source|ref|refid|trk|tracking_?id|lever-(source|origin)|"
                      r"lever-via|fbclid|gclid|mc_\w+)$", re.I)


def link_key(url):
    """A posting link with the parts that do not name the job dropped: fragment, tracking
    parameters, a trailing slash. A query that names the job (?gh_jid=, ?pid=) stays."""
    base, _, query = url.strip().split("#")[0].partition("?")
    keep = sorted(q for q in query.split("&") if q and not TRACKING.match(q.split("=", 1)[0]))
    return base.lower().rstrip("/") + ("?" + "&".join(keep).lower() if keep else "")


def parse(path):
    """{tier: [row dict]} for A, B, C and 'Dropped'."""
    txt = Path(path).read_text(encoding="utf-8-sig")
    out, cur, cols = {}, None, None
    for line in txt.splitlines():
        h = re.match(r"##\s+([ABC]):|##\s+(Dropped)\b", line)
        if h:
            cur, cols = h.group(1) or h.group(2), None
            out.setdefault(cur, [])
            continue
        if cur and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cols is None:
                cols = cells
                want = DROP_COLS if cur == "Dropped" else KEPT_COLS
                if cols != want:
                    die(f"{path}: section {cur} columns are {cols}; need {want} (triage.py format)")
                continue
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            if len(cells) != len(cols):
                die(f"{path}: a row in section {cur} has {len(cells)} cells, the header {len(cols)}: {line[:80]}")
            out[cur].append(dict(zip(cols, cells)))
    if not any(out.get(t) for t in "ABC") and not out.get("Dropped"):
        die(f"{path}: no A, B, C or Dropped table found (triage.py format)")
    return out


def seen_links():
    seen = {}
    log = ROOT / "outreach" / "log.md"
    for p, why in ((log, "already applied (log.md)"), (PASSED, "passed before (passed.md)")):
        if p.exists():
            for url in re.findall(r"https?://[^\s|)]+", p.read_text(encoding="utf-8")):
                seen.setdefault(link_key(url), why)
    return seen


def check(path, jobs_dir, days, today=None):
    today = today or date.today()
    data = parse(path)
    seen = seen_links()
    v = []

    def jd_raw(row, tag):
        name = row["JD file"]
        if name in ("", "-"):
            v.append(f"{tag} no JD file: save the posting first (jobs.py list --save, or write the text to {jobs_dir})")
            return None
        if Path(name).name != name or name.startswith("."):
            v.append(f"{tag} JD file '{name}' must be a file name inside {jobs_dir}, with no folder in it")
            return None
        p = Path(jobs_dir) / name
        if not p.is_file():
            v.append(f"{tag} JD file {p} not found")
            return None
        return p.read_text(encoding="utf-8")

    def quote_ok(row, tag, text):
        qs = quotes(row["Quote"])
        if not qs:
            v.append(f"{tag} no quote: copy the sentence from the posting that proves this")
        for q in qs:
            if len(q.split()) < MIN_QUOTE_WORDS:
                v.append(f"{tag} quote \"{q[:70]}\" is too short to prove anything: copy the whole "
                         f"sentence (at least {MIN_QUOTE_WORDS} words)")
            elif text is not None and fold(q) not in text:
                v.append(f"{tag} quote not found word for word in {row['JD file']}: \"{q[:70]}\"")

    for tier in "ABC":
        lo, hi = TIERS[tier]
        for row in data.get(tier, []):
            tag = f"[{tier}{row['#']} {row['Company']}]"
            try:
                score = int(row["Score"])
            except ValueError:
                v.append(f"{tag} Score '{row['Score']}' must be a whole number 1-5")
                score = None
            if score is not None and not lo <= score <= hi:
                v.append(f"{tag} Score {score} does not belong in tier {tier} (needs {lo}-{hi})")
            if row["Posted"].lower() != "unknown":
                try:
                    age = (today - date.fromisoformat(row["Posted"])).days
                    if age > days:
                        v.append(f"{tag} posted {age} days ago, older than {days}: drop it as stale")
                except ValueError:
                    v.append(f"{tag} Posted '{row['Posted']}' must be YYYY-MM-DD or unknown")
            if not re.match(r"https?://", row["Link"]):
                v.append(f"{tag} Link must be the posting's URL")
            elif link_key(row["Link"]) in seen:
                v.append(f"{tag} {seen[link_key(row['Link'])]}: move it to Dropped")
            elif broad_board(row["Link"]):
                v.append(f"{tag} Link is on {broad_board(row['Link'])}, a broad board: find the job on a trusted source "
                         f"(the company's own careers page or ATS board, LinkedIn, or a board playbooks/sources.md "
                         f"marks trusted) and link that. Found on none → move it to Dropped as 'no trusted source'")
            if not row["Why it fits"].strip("- "):
                v.append(f"{tag} 'Why it fits' is empty")
            raw = jd_raw(row, tag)
            quote_ok(row, tag, None if raw is None else fold(raw))
            pays = candidate_pays(raw) if raw is not None else None
            if pays:
                v.append(f"{tag} the posting asks the candidate to pay, a known scam pattern: \"{pays}\". Move it to "
                         f"Dropped with reason 'scam: asks the candidate to pay' and that quote. A false alarm still "
                         f"goes to Dropped: tell the owner, who can apply from the link if they judge it safe")
    for row in data.get("Dropped", []):
        tag = f"[Dropped {row['Company']}]"
        reason = row["Reason"].lower()
        if not reason.strip("- "):
            v.append(f"{tag} no reason")
        if reason.startswith(NO_QUOTE):
            continue
        raw = jd_raw(row, tag)
        quote_ok(row, tag, None if raw is None else fold(raw))
    kept = sum(len(data.get(t, [])) for t in "ABC")
    return v, f"{kept} kept, {len(data.get('Dropped', []))} dropped"


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    if argv[0] == "format" and len(argv) == 1:
        print(FORMAT)
    elif argv[0] == "check" and len(argv) >= 2:
        path, jobs_dir, days = argv[1], str(ROOT / "outreach" / "jobs"), 30
        rest = argv[2:]
        while rest:
            if rest[0] == "--jobs-dir" and len(rest) > 1:
                jobs_dir, rest = rest[1], rest[2:]
            elif rest[0] == "--days" and len(rest) > 1 and rest[1].isdigit():
                days, rest = int(rest[1]), rest[2:]
            else:
                die(f"unknown option {rest[0]}")
        if not Path(path).is_file():
            die(f"{path} not found")
        v, stats = check(path, jobs_dir, days)
        if v:
            print(f"FAIL ({stats})")
            for x in v:
                print("  " + x)
            sys.exit(1)
        print(f"PASS ({stats})")
    elif argv[0] == "pass" and len(argv) == 3:
        url, why = argv[1].strip(), argv[2].replace("|", "/").strip()
        if not re.match(r"https?://", url) or not why:
            die('pass takes the posting link and a reason: triage.py pass https://... "too junior"')
        PASSED.parent.mkdir(exist_ok=True)
        if not PASSED.exists():
            PASSED.write_text("| Date | Link | Reason |\n|---|---|---|\n", encoding="utf-8")
        with PASSED.open("a", encoding="utf-8") as f:
            f.write(f"| {date.today()} | {url} | {why} |\n")
        print(f"recorded: later searches skip {url}")
    else:
        die(__doc__)


if __name__ == "__main__":
    run(main)
