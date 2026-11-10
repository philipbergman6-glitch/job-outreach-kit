#!/usr/bin/env python3
"""Application tracker. Stdlib only.

Usage:
  tracker.py init     create outreach/log.md, replies.md, followups.md, do-not-contact.md
                      (never overwrites)
  tracker.py build    write outreach/applications.csv from log.md + replies.md (opens in Excel / Sheets)

Hard-fails on a malformed table or a replies.md row whose Company + Role is not in log.md."""
import csv
import re
import sys

from _common import ROOT, die, run

OUT = ROOT / "outreach"
LOG_COLS = ["Date", "Company", "Role", "JD URL", "Apply channel", "CV",
            "Contacts", "Emails", "Status", "Folder"]
REPLY_COLS = ["Company", "Role", "Got back?", "Reply date", "Reply from", "Outcome", "Notes"]
FOLLOW_COLS = ["Added", "Company", "Trigger", "Action", "Text source", "Done"]
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


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(sys.argv) != 2 or sys.argv[1] not in ("init", "build"):
        die(__doc__)
    init() if sys.argv[1] == "init" else build()


if __name__ == "__main__":
    run(main)
