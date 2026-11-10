#!/usr/bin/env python3
"""Application tracker. Stdlib only.

Usage:
  tracker.py init     create outreach/log.md, replies.md, followups.md (never overwrites)
  tracker.py build    write outreach/applications.csv from log.md + replies.md (opens in Excel / Sheets)

Hard-fails on a malformed row or a replies.md company missing from log.md."""
import csv
import sys

from _common import ROOT, die

OUT = ROOT / "outreach"
LOG_COLS = ["Date", "Company", "Role", "JD URL", "Apply channel", "CV",
            "Contacts", "Emails", "Status", "Folder"]
REPLY_COLS = ["Company", "Got back?", "Reply date", "Reply from", "Outcome", "Notes"]
FOLLOW_COLS = ["Added", "Company", "Trigger", "Action", "Text source", "Done"]


def header(cols):
    return "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"


def read_table(path, expected):
    if not path.exists():
        die(f"{path} missing: run tracker.py init")
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        die(f"{path}: no table")
    head = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    if head != expected:
        die(f"{path}: header {head} != {expected}")
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
    for name, cols, title in (("log.md", LOG_COLS, None), ("replies.md", REPLY_COLS, None),
                              ("followups.md", FOLLOW_COLS, "# Follow-ups (read at the start of each session)\n\n")):
        p = OUT / name
        if p.exists():
            print(f"kept    {p}")
            continue
        p.write_text((title or "") + header(cols), encoding="utf-8")
        print(f"created {p}")


def build():
    apps = read_table(OUT / "log.md", LOG_COLS)
    # A company can appear more than once (two roles). replies.md has no Role column, so the
    # n-th replies row for a company pairs with the n-th log row for it, in file order.
    replies = {}
    for r in read_table(OUT / "replies.md", REPLY_COLS):
        replies.setdefault(r["Company"], []).append(r)
    unknown = set(replies) - {a["Company"] for a in apps}
    if unknown:
        die(f"replies.md companies not in log.md: {sorted(unknown)}")
    for co, rs in replies.items():
        n = sum(a["Company"] == co for a in apps)
        if len(rs) > n:
            die(f"replies.md has {len(rs)} rows for {co!r}, log.md has {n}")
    cols = ["Date applied", "Company", "Role", "Got back?", "Reply date", "Reply from", "Outcome",
            "Notes", "Apply channel", "Status", "Contacts", "Emails", "CV", "JD URL", "Folder"]
    out = OUT / "applications.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for a in apps:
            rs = replies.get(a["Company"], [])
            r = rs.pop(0) if rs else {}
            w.writerow([a["Date"], a["Company"], a["Role"], r.get("Got back?", "No"),
                        r.get("Reply date", ""), r.get("Reply from", ""), r.get("Outcome", "Pending"),
                        r.get("Notes", ""), a["Apply channel"], a["Status"], a["Contacts"],
                        a["Emails"], a["CV"], a["JD URL"], a["Folder"]])
    print(f"wrote {out} ({len(apps)} rows)")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if len(sys.argv) != 2 or sys.argv[1] not in ("init", "build"):
        die(__doc__)
    init() if sys.argv[1] == "init" else build()
