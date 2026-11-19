#!/usr/bin/env python3
"""Application tracker. Stdlib only.

Usage:
  tracker.py init     create outreach/log.md, replies.md, followups.md, do-not-contact.md
                      (never overwrites)
  tracker.py build    write outreach/applications.csv from log.md + replies.md (opens in Excel / Sheets)
  tracker.py due      what needs doing: each open follow-up as overdue / urgent / waiting (a Trigger
                      that is a YYYY-MM-DD date is due that day; urgent = up to 2 days late), a nudge
                      made moot by a reply as answered, and each emailed application with no reply
                      14 days after its one nudge (21 after sending, with no nudge row) as cold.
                      There is no second nudge: cold means move on; Status `closed` in log.md ends
                      an application, so it is never shown again.

Hard-fails on a malformed table, a replies.md or followups.md row whose Company + Role is not
in log.md, a date not written YYYY-MM-DD, and a Done cell that says not done ("No", "-")."""
import csv
import re
import sys
from datetime import date, timedelta

from _common import ROOT, die, run

OUT = ROOT / "outreach"
LOG_COLS = ["Date", "Company", "Role", "JD URL", "Apply channel", "CV",
            "Contacts", "Emails", "Status", "Folder"]
REPLY_COLS = ["Company", "Role", "Got back?", "Reply date", "Reply from", "Outcome", "Notes"]
FOLLOW_COLS = ["Added", "Company", "Role", "Trigger", "Action", "Text source", "Done"]
OLD_FOLLOW_COLS = ["Added", "Company", "Trigger", "Action", "Text source", "Done"]
CLOSED = "closed"
DNC = """# Do not contact

> One per line: an address (name@company.com) or a whole company (@company.com).
> A note may follow it. scripts/mail.py refuses to write to anything listed here.

"""


def header(cols):
    return "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"


def read_table(path, expected):
    if not path.exists():
        die(f"{path} missing: run tracker.py init")
    lines = [l for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        die(f"{path}: no table")
    head = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    if expected == FOLLOW_COLS and head == OLD_FOLLOW_COLS:
        die(f"{path}: add a Role column after Company (each row's role exactly as in log.md), so a "
            f"reply or nudge for one role at a company is not taken for another")
    if head != expected:
        die(f"{path}: header {head} != {expected}")
    if not re.fullmatch(r"[|\s:\-]+", lines[1]) or "-" not in lines[1]:
        die(f"{path}: the line under the header must be the |---|---| separator")
    rows = []
    for n, line in enumerate(lines[2:], start=3):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(expected):
            die(f"{path}: table row {n}: {len(cells)} cells, expected {len(expected)} "
                f"(a '|' inside a cell breaks the row)")
        if not any(cells):
            die(f"{path}: table row {n} is empty: delete it")
        rows.append(dict(zip(expected, cells)))
    return rows


def init():
    OUT.mkdir(exist_ok=True)
    files = (("log.md", header(LOG_COLS)), ("replies.md", header(REPLY_COLS)),
             ("followups.md", "# Follow-ups (read at the start of each session)\n\n" + header(FOLLOW_COLS)),
             ("do-not-contact.md", DNC))
    for name, text in files:
        p = OUT / name
        if p.exists():
            print(f"kept    {p}")
            continue
        p.write_text(text, encoding="utf-8")
        print(f"created {p}")


def safe(cell):
    """Spreadsheets run a cell starting with = + - @ as a formula; a leading quote stops that."""
    return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell


def build():
    apps = read_table(OUT / "log.md", LOG_COLS)
    # The n-th replies row for a Company + Role pairs with the n-th log row for it (a re-apply).
    replies = {}
    for r in read_table(OUT / "replies.md", REPLY_COLS):
        replies.setdefault((r["Company"], r["Role"]), []).append(r)
    for key, rs in replies.items():
        n = sum((a["Company"], a["Role"]) == key for a in apps)
        if len(rs) > n:
            die(f"replies.md has {len(rs)} row(s) for {key[0]!r} / {key[1]!r}, log.md has {n}: "
                f"Company and Role must match a log.md row exactly")
    cols = ["Date applied", "Company", "Role", "Got back?", "Reply date", "Reply from", "Outcome",
            "Notes", "Apply channel", "Status", "Contacts", "Emails", "CV", "JD URL", "Folder"]
    out = OUT / "applications.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for a in apps:
            rs = replies.get((a["Company"], a["Role"]), [])
            r = rs.pop(0) if rs else {}
            w.writerow([safe(c) for c in (
                a["Date"], a["Company"], a["Role"], r.get("Got back?", "No"),
                r.get("Reply date", ""), r.get("Reply from", ""), r.get("Outcome", "Pending"),
                r.get("Notes", ""), a["Apply channel"], a["Status"], a["Contacts"],
                a["Emails"], a["CV"], a["JD URL"], a["Folder"])])
    print(f"wrote {out} ({len(apps)} rows)")


ORDER = ("overdue", "urgent", "answered", "waiting", "cold")
URGENT_DAYS, COLD_AFTER_NUDGE, COLD_WITHOUT_NUDGE = 2, 14, 21


# Not inside a clock time or time range ("14:08-14:10Z"): no ":" or digit on either side.
DATE_ISH = re.compile(r"(?<![\d:])\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{1,4})?(?![\d:])")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _dates(s, where):
    """Every date in a cell, each written YYYY-MM-DD; anything else that looks like a date fails."""
    out = []
    for d in DATE_ISH.findall(s):
        if not ISO.fullmatch(d):
            die(f"{where}: '{d}' must be written YYYY-MM-DD (in '{s}')")
        try:
            out.append(date.fromisoformat(d))
        except ValueError:
            die(f"{where}: '{d}' is not a real date (YYYY-MM-DD)")
    return out


def _day(s, where):
    """The cell as one date when it is exactly one, else None (an event, such as "invite accepted")."""
    got = _dates(s, where)
    return got[0] if ISO.fullmatch(s.strip()) else None


def _done(s, where):
    if s.strip().lower() in ("no", "n", "-", "not yet", "pending", "open", "todo", "false"):
        die(f"{where}: Done '{s}' reads as not done. Leave it empty until it is done, then write the "
            f"date (or why it was dropped)")
    return bool(s.strip())


def due(today=None):
    """[{State, Company, Due, Action, Next}], most pressing first."""
    today = today or date.today()
    follow = read_table(OUT / "followups.md", FOLLOW_COLS)
    apps = read_table(OUT / "log.md", LOG_COLS) if (OUT / "log.md").exists() else []
    replies = read_table(OUT / "replies.md", REPLY_COLS) if (OUT / "replies.md").exists() else []
    logged = {(a["Company"], a["Role"]) for a in apps}
    for name, rows in (("replies.md", replies), ("followups.md", follow)):
        for r in rows:
            if (r["Company"], r["Role"]) not in logged:
                die(f"{name}: no log.md row for {r['Company']!r} / {r['Role']!r}: Company and Role must "
                    f"match a log.md row exactly")
    closed = {(a["Company"], a["Role"]) for a in apps if a["Status"].strip().lower() == CLOSED}
    heard = {(r["Company"], r["Role"]) for r in replies
             if r["Got back?"].strip().lower() == "yes" or r["Outcome"] not in ("Pending", "")}
    out = []
    for r in follow:
        app = (r["Company"], r["Role"])
        if _done(r["Done"], "followups.md Done") or app in closed:
            continue
        when = _day(r["Trigger"], "followups.md Trigger")
        row = {"Company": r["Company"], "Action": r["Action"], "Due": r["Trigger"]}
        if "nudge" in r["Action"].lower() and app in heard:
            row.update(State="answered", Next="a reply came in: mark it done, no nudge")
        elif when is None:
            row.update(State="waiting", Next="when that happens")
        elif today < when:
            row.update(State="waiting", Next=f"in {(when - today).days} days")
        elif (today - when).days <= URGENT_DAYS:
            row.update(State="urgent", Next="do it today")
        else:
            row.update(State="overdue", Next=f"{(today - when).days} days late: do it now, or mark it done with why")
        out.append(row)
    for a in apps:
        app = (a["Company"], a["Role"])
        sent = min(_dates(a["Emails"], "log.md Emails"), default=None)
        if not sent or app in heard or app in closed:
            continue
        nudges = [r for r in follow if (r["Company"], r["Role"]) == app and "nudge" in r["Action"].lower()]
        if any(not r["Done"] for r in nudges):
            continue
        last = max([_day(r["Done"], "followups.md Done") or _day(r["Trigger"], "followups.md Trigger") or sent
                    for r in nudges], default=None)
        quiet_since = last + timedelta(days=COLD_AFTER_NUDGE) if last else sent + timedelta(days=COLD_WITHOUT_NUDGE)
        if today >= quiet_since:
            out.append({"State": "cold", "Company": a["Company"], "Action": a["Role"], "Due": a["Emails"],
                        "Next": "no reply after the one nudge: no second nudge; move on (Status closed in "
                                "log.md hides it), and let review.md count it"})
    return sorted(out, key=lambda r: ORDER.index(r["State"]))


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(sys.argv) != 2 or sys.argv[1] not in ("init", "build", "due"):
        die(__doc__)
    if sys.argv[1] == "due":
        rows = due()
        if not rows:
            print("nothing due")
            return
        cols = ["State", "Company", "Due", "Action", "Next"]
        print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
        for r in rows:
            print("| " + " | ".join(r[c] for c in cols) + " |")
        return
    init() if sys.argv[1] == "init" else build()


if __name__ == "__main__":
    run(main)
