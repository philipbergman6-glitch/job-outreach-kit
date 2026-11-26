#!/usr/bin/env python3
"""Application tracker. Stdlib only.

Usage:
  tracker.py init     create outreach/log.md, replies.md, followups.md, do-not-contact.md
                      (never overwrites)
  tracker.py build    write outreach/applications.csv (opens in Excel / Sheets): one row per
                      application with its id, next due action, reply, and per recipient (manager,
                      recruiter) who they are and what happened: emailed, nudged, replied
  tracker.py due      what needs doing: each open follow-up as overdue / urgent / waiting (a Trigger
                      that is a YYYY-MM-DD date is due that day, one that is only a span of time,
                      "3-5 days", "in 2 weeks", "1-2 business days", is due that long after the
                      row's Added date, at the later bound; urgent = up to 2 days late), a nudge
                      made moot by a reply as answered, and each emailed application with no reply
                      14 days after its one nudge (21 after sending, with no nudge row) as cold.
                      There is no second nudge: cold means move on.

Writing (every change to log.md, replies.md and followups.md goes through these, never a hand edit;
<app> is the slug in the row's Folder cell, outreach/<slug>/, or the id `build` shows for it;
--date YYYY-MM-DD sets the day written, default today):
  tracker.py start <slug> --company "<Company>" --role "<Role>" --url <JD link> [--reapply]
                      a new application: its log.md row (Status started, Folder outreach/<slug>/) and its
                      replies.md row (Pending). A Company + Role already in log.md needs --reapply
  tracker.py status <app> <status> [--outcome "<Outcome>"] [--note "..."] [--set "Column=value" ...]
                      [--force "<reason>"]
                      sets Status. It goes forward only (started, handoff-pending, submitted, sent,
                      closed); a step back needs --force with the reason, kept in replies.md Notes.
                      closed needs an Outcome (or one already there that closes it): it is written to
                      replies.md and every open follow-up of the application is marked done. --set fills
                      another log.md cell: JD URL, Apply channel, CV, Contacts, Emails
  tracker.py reply <app> --got yes|auto-ack --outcome "<Outcome>" [--from "<who>"] [--thread <id>]
                      [--note "..."] [--force "<reason>"]
                      records a reply in replies.md. A person's reply (yes) or a closing Outcome marks
                      the open nudges done; an auto-ack never overwrites a person's reply; replacing a
                      closing Outcome with an open one needs --force
  tracker.py followup <app> add --trigger "<date, span or event>" --action "<N1 nudge manager ...>"
                      [--source <file>]
  tracker.py followup <app> done --action "<start of the Action>" [--note "<why>"]
                      marks that one open follow-up done with the date (and why)
  tracker.py normalize [--apply]
                      lists each log.md Status outside the list and what it becomes (dropped, expired,
                      rejected <date>, withdrawn -> closed with that Outcome; drafted -> started);
                      nothing is written without --apply. Anything with no rule is named for the owner.
  Each rerun of the same change prints "already" and writes nothing. Every other byte of the file stays
  as it was, and the file is replaced in one step.

Outcome (replies.md) starts with one of Pending, Interview, Offer, Rejected, Expired, Dropped, Withdrawn,
Closed; a reason may follow: "Rejected (role filled)".

Each replies.md and followups.md row belongs to one application (one log.md row, id = its folder
slug): the n-th replies row for a Company + Role pairs with the n-th log row for it; a follow-up goes
to the latest application for its Company + Role applied on or before its Added date. So a closed
earlier application to the same role hides nothing of a re-application.

Status (log.md) is one of: started, handoff-pending, submitted, sent, closed. `closed` ends the
application: nothing more is due. A reply whose Outcome starts with Rejected, Expired, Dropped,
Withdrawn or Closed ends its nudges and its cold verdict; other follow-ups stay until done. A Status
outside the list is named in a WARN line (stderr) and treated as open.

Hard-fails on a malformed table, a replies.md or followups.md row whose Company + Role is not
in log.md, a date not written YYYY-MM-DD, a span Trigger with no Added date, and a Done cell
that says not done ("No", "-"). The writing commands also hard-fail, writing nothing, on a value
outside these lists, an application id that names no row or two, a header that is not the kit's, and a
'|' or line break in a value."""
import argparse
import csv
import os
import re
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import ROOT, die, read_text, run

OUT = ROOT / "outreach"
LOG_COLS = ["Date", "Company", "Role", "JD URL", "Apply channel", "CV",
            "Contacts", "Emails", "Status", "Folder"]
REPLY_COLS = ["Company", "Role", "Got back?", "Reply date", "Reply from", "Outcome", "Notes"]
FOLLOW_COLS = ["Added", "Company", "Role", "Trigger", "Action", "Text source", "Done"]
OLD_FOLLOW_COLS = ["Added", "Company", "Trigger", "Action", "Text source", "Done"]
CLOSED = "closed"
# log.md Status, in the order an application moves through them. Anything else is reported, never guessed.
STATUSES = ("started", "handoff-pending", "submitted", "sent", CLOSED)
# A replies.md Outcome whose first word is one of these ends the application, as Status closed does.
CLOSING_OUTCOMES = ("rejected", "expired", "dropped", "withdrawn", "closed")
DNC = """# Do not contact

> One per line: an address (name@company.com) or a whole company (@company.com).
> A note may follow it. scripts/mail.py refuses to write to anything listed here.

"""


def header(cols):
    return "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"


def _parse_table(path, expected, lines):
    """[(index into lines, cells)] for each row of the table in lines; hard-fails, naming the file
    and its line, on a header, separator or row that is not as expected."""
    at = [i for i, l in enumerate(lines) if l.strip().startswith("|")]
    if len(at) < 2:
        die(f"{path}: no table")
    head = [c.strip() for c in lines[at[0]].strip().strip("|").split("|")]
    if expected == FOLLOW_COLS and head == OLD_FOLLOW_COLS:
        die(f"{path}: add a Role column after Company (each row's role exactly as in log.md), so a "
            f"reply or nudge for one role at a company is not taken for another")
    if head != expected:
        die(f"{path} line {at[0] + 1}: header {head} != {expected}")
    if not re.fullmatch(r"[|\s:\-]+", lines[at[1]]) or "-" not in lines[at[1]]:
        die(f"{path}: the line under the header must be the |---|---| separator")
    rows = []
    for n, i in enumerate(at[2:], start=3):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cells) != len(expected):
            die(f"{path}: table row {n}: {len(cells)} cells, expected {len(expected)} "
                f"(a '|' inside a cell breaks the row)")
        if not any(cells):
            die(f"{path}: table row {n} is empty: delete it")
        rows.append((i, cells))
    return rows


def read_table(path, expected):
    if not path.exists():
        die(f"{path} missing: run tracker.py init")
    return [dict(zip(expected, cells)) for _, cells in _parse_table(path, expected, read_text(path).splitlines())]


class Table:
    """One of the tables, open for editing. Only the cells set and the rows appended change: every
    other byte (other rows, their spacing, notes around the table, line endings, a byte-order mark)
    is written back as it was read, and the file is replaced in one step (save)."""

    def __init__(self, path, cols):
        if not path.exists():
            die(f"{path} missing: run tracker.py init")
        data = path.read_bytes()
        self.path, self.cols, self.changed = path, cols, False
        self.encoding = ("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else
                         "utf-8-sig" if data[:3] == b"\xef\xbb\xbf" else "utf-8")
        self.lines = read_text(path).splitlines(keepends=True)
        self.nl = "\r\n" if self.lines and self.lines[0].endswith("\r\n") else "\n"
        self.rows = _parse_table(path, cols, [l.rstrip("\r\n") for l in self.lines])

    def get(self, k, col):
        return self.rows[k][1][self.cols.index(col)]

    def set(self, k, col, value):
        """Row k (0 = first row under the separator) gets value in col; True when that changed it."""
        value = cell(value, f"{self.path.name} {col}")
        i, cells = self.rows[k]
        c = self.cols.index(col)
        if cells[c] == value:
            return False
        line = self.lines[i]
        body = line.rstrip("\r\n")
        end, inner = line[len(body):], body.strip()
        if not (inner.startswith("|") and inner.endswith("|")) or inner.startswith("||") or inner.endswith("||"):
            die(f"{self.path} line {i + 1}: start and end the row with a single '|' so it can be edited")
        segs = inner[1:-1].split("|")
        lead = body[:len(body) - len(body.lstrip())]
        segs[c] = f" {value} " if value else " "
        self.lines[i] = lead + "|" + "|".join(segs) + "|" + body[len(body.rstrip()):] + end
        cells[c] = value
        self.changed = True
        return True

    def append(self, values):
        """A new row after the table's last row; its index."""
        values = [cell(v, f"{self.path.name} {c}") for c, v in zip(self.cols, values)]
        last = self.rows[-1][0] if self.rows else [i for i, l in enumerate(self.lines) if l.strip().startswith("|")][1]
        if not self.lines[last].endswith(("\n", "\r")):
            self.lines[last] += self.nl
        self.lines.insert(last + 1, "|" + "|".join(f" {v} " if v else " " for v in values) + "|" + self.nl)
        self.rows = [(i + (i > last), c) for i, c in self.rows] + [(last + 1, values)]
        self.changed = True
        return len(self.rows) - 1

    def save(self):
        if not self.changed:
            return
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_bytes("".join(self.lines).encode(self.encoding))
        os.replace(tmp, self.path)
        self.changed = False


def cell(value, where):
    """A value fit for one table cell: one line, no '|'."""
    value = str(value).strip()
    if "|" in value or "\n" in value or "\r" in value:
        die(f"{where}: '{value}' cannot go in a table cell (no '|', no line break)")
    return value


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


def front_matter(path):
    """The key: value lines between a messages.md file's opening --- lines; {} when it has none."""
    lines = read_text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta
        k, sep, v = line.partition(":")
        if sep:
            meta[k.strip()] = v.strip()
    return {}


SIDES = (("hm", "Manager", "HM", re.compile(r"\s*(?:N1\b|nudge\s+(?:the\s+)?manager\b)", re.I)),
         ("rec", "Recruiter", "Rec", re.compile(r"\s*(?:N2\b|nudge\s+(?:the\s+)?recruiter\b)", re.I)))


def recipients(a):
    """{"Manager": (who, state), "Recruiter": (who, state)} for the people the application names.

    Who and the email confidence come from outreach/<id>/messages.md (hm_* / rec_*), else from the
    Contacts cell ("Name (HM, High); Name (Rec, Medium)"). State is read from the tables, not from the
    send ledger: emailed <first date in Emails> (or <side>_sent), held, or no email; then the N1 (manager)
    / N2 (recruiter) nudge row, done or due; then replied <date> when Reply from names them."""
    path = OUT / a["id"] / "messages.md"
    meta = front_matter(path) if app_id(a["log"]["Folder"]) and path.exists() else {}
    contacts = {}
    for part in a["log"]["Contacts"].split(";"):
        m = re.match(r"\s*([^(]+?)\s*\((HM|Rec)\b[,\s]*([^)]*)\)", part)
        if m:
            contacts.setdefault(m.group(2), (m.group(1), m.group(3).strip()))
    emails = a["log"]["Emails"]
    first = min(_dates(emails, "log.md Emails"), default=None)
    r = a["reply"]
    out = {}
    for side, label, tag, nudge in SIDES:
        if meta.get(f"{side}_name"):
            name, address = meta[f"{side}_name"], meta.get(f"{side}_email", "")
            conf = meta.get(f"{side}_email_confidence", "")
            who = f"{name} (email {conf})" if conf else name
        elif tag in contacts:
            name, conf = contacts[tag]
            address, who = None, f"{name} ({conf})" if conf else name
        else:
            continue
        # <side>_sent is "<date> <Message-ID>" (mail.py): only its leading date counts.
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})\b", meta.get(f"{side}_sent", ""))
        sent = _day(m.group(1), f"{path} {side}_sent") if m else first
        if address == "":
            state = ["no email: LinkedIn only"]
        elif sent:
            state = [f"emailed {sent}"]
        elif emails.strip().lower() == "held":
            state = ["held"]
        else:
            state = ["not emailed"]
        for f in a["follow"]:
            if nudge.match(f["Action"]):
                state.append(f"nudged {f['Done']}" if f["Done"] else f"nudge {f['Trigger']}")
        frm = r.get("Reply from", "").lower()
        if a["heard"] and frm and (name.lower() in frm or (address and address.lower() in frm)):
            state.append(f"replied {r['Reply date']}".strip())
        out[label] = (who, ", ".join(state))
    return out


def next_due(apps, today=None):
    """{app id: (Next due, Next action)}: the most pressing due() row of each application."""
    out = {}
    for row in due(today, apps):
        if row["App"] not in out:
            when = row["When"].isoformat() if row["When"] else row["Due"]
            out[row["App"]] = (when, f"{row['State']}: {row['Action'] if row['State'] != 'cold' else 'move on'}")
    for a in apps:
        if a["closed"]:
            out.setdefault(a["id"], ("", "nothing: closed"))
    return out


CSV_COLS = ["Id", "Date applied", "Company", "Role", "Status", "Next due", "Next action", "Got back?",
            "Reply date", "Reply from", "Outcome", "Notes", "Manager", "Manager state", "Recruiter",
            "Recruiter state", "Apply channel", "Contacts", "Emails", "CV", "JD URL", "Folder"]


def build(today=None):
    apps = load(need=("log.md", "replies.md"))
    warn(apps)
    nxt = next_due(apps, today)
    out = OUT / "applications.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for a in apps:
            l, r, people = a["log"], a["reply"], recipients(a)
            hm, rec = people.get("Manager", ("", "")), people.get("Recruiter", ("", ""))
            when, action = nxt.get(a["id"], ("", ""))
            w.writerow([safe(c) for c in (
                a["id"], l["Date"], l["Company"], l["Role"], l["Status"], when, action,
                r.get("Got back?", "No"), r.get("Reply date", ""), r.get("Reply from", ""),
                r.get("Outcome", "Pending"), r.get("Notes", ""), hm[0], hm[1], rec[0], rec[1],
                l["Apply channel"], l["Contacts"], l["Emails"], l["CV"], l["JD URL"], l["Folder"])])
    print(f"wrote {out} ({len(apps)} rows)")


ORDER = ("overdue", "urgent", "answered", "waiting", "cold")
URGENT_DAYS, COLD_AFTER_NUDGE, COLD_WITHOUT_NUDGE = 2, 14, 21


# Not inside a clock time or time range ("14:08-14:10Z"): no ":" or digit on either side.
DATE_ISH = re.compile(r"(?<![\d:])\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{1,4})?(?![\d:])")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
# A nudge row's Action starts with it ("N1 nudge manager", "Nudge Maya: ..."); a row that only
# mentions one ("no nudge if silent") is not a nudge.
NUDGE = re.compile(r"\s*(?:N\d\s+)?nudge\b", re.I)


# A span of time, "5 days", "3-5 days", "2 weeks", "1-2 business days": not a date. A Trigger that is
# only a span ("3-5 days", "in 2 weeks") is due that long after the row's Added date, at the later bound.
SPAN = re.compile(r"(?<![\d:])(\d{1,3})(?:\s*[-\u2013]\s*(\d{1,3}))?\s+((?:business|working)\s+)?(day|week)s?\b",
                  re.I)
ONLY_SPAN = re.compile(r"\s*(?:in|after|within)?\s*" + SPAN.pattern + r"\s*", re.I)


def _dates(s, where):
    """Every date in a cell, each written YYYY-MM-DD; anything else that looks like a date fails."""
    out = []
    for d in DATE_ISH.findall(SPAN.sub(" ", s)):
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


def _after(start, m):
    """start + the later bound of a SPAN match, business days skipping Saturday and Sunday."""
    n = int(m.group(2) or m.group(1))
    if m.group(4).lower() == "week":
        return start + timedelta(weeks=n)
    if not m.group(3):
        return start + timedelta(days=n)
    d = start
    while n:
        d += timedelta(days=1)
        n -= d.weekday() < 5
    return d


def _trigger(r, where):
    """(date or None, text shown): a YYYY-MM-DD Trigger is that day; a span counts from Added."""
    s = r["Trigger"]
    m = ONLY_SPAN.fullmatch(s)
    if not m:
        return _day(s, where), s
    added = _day(r["Added"], "followups.md Added")
    if not added:
        die(f"{where}: '{s}' counts from the row's Added date, which is '{r['Added']}': write Added as "
            f"YYYY-MM-DD, or the Trigger as a date")
    when = _after(added, m)
    return when, f"{s} (= {when})"


def _done(s, where):
    if s.strip().lower() in ("no", "n", "-", "not yet", "pending", "open", "todo", "false"):
        die(f"{where}: Done '{s}' reads as not done. Leave it empty until it is done, then write the "
            f"date (or why it was dropped)")
    return bool(s.strip())


def _app_day(a):
    got = _dates(a["log"]["Date"], f"log.md row {a['n']} Date")
    return got[0] if got else date.min


def _pair_follow(apps, r, n):
    """The application a followups.md row belongs to: the only one for its Company + Role, else the
    latest applied on or before the row's Added date (no Added: the latest)."""
    cands = [a for a in apps if (a["log"]["Company"], a["log"]["Role"]) == (r["Company"], r["Role"])]
    if not cands:
        die(f"followups.md: no log.md row for {r['Company']!r} / {r['Role']!r}: Company and Role must "
            f"match a log.md row exactly")
    if len(cands) == 1:
        return cands[0]
    added = _day(r["Added"], "followups.md Added")
    if added is None:
        return cands[-1]
    before = [a for a in cands if _app_day(a) <= added]
    if not before:
        die(f"followups.md row {n} ({r['Company']} / {r['Role']}, Added {r['Added']}) is older than every "
            f"application to that role ({', '.join(a['log']['Date'] for a in cands)}): fix its Added date, "
            f"which says which application it belongs to")
    return max(before, key=_app_day)


def load(need=("log.md", "replies.md", "followups.md")):
    """Every application in log.md, in order: {"id", "n", "log", "reply", "follow", "closed", "heard"}.

    id is the folder slug (outreach/<slug>/), else row-<n>. The n-th replies.md row for a Company + Role
    pairs with the n-th log.md row for it (a re-apply gets its own replies row); a followups.md row goes
    to the application it was added for (_pair_follow). So a follow-up, a reply or a close belongs to one
    application: an earlier, closed application to the same role hides nothing of a new one.
    closed: Status `closed` (closed_by "status": the owner has moved on, nothing more is due), or a reply
    whose Outcome starts with a closing word, CLOSING_OUTCOMES (closed_by "reply": no nudge, never cold;
    a follow-up the owner added for after it, such as a feedback request, still counts)."""
    def table(name, cols):
        path = OUT / name
        return read_table(path, cols) if name in need or path.exists() else []
    rows, replies, follow = (table("log.md", LOG_COLS), table("replies.md", REPLY_COLS),
                             table("followups.md", FOLLOW_COLS))
    apps, seen = [], set()
    for n, r in enumerate(rows, start=3):
        aid = app_id(r["Folder"]) or f"row-{n}"
        if aid in seen:
            aid = f"{aid}#{n}"
        seen.add(aid)
        apps.append({"id": aid, "n": n, "log": r, "reply": {}, "follow": []})
    by_key = {}
    for a in apps:
        by_key.setdefault((a["log"]["Company"], a["log"]["Role"]), []).append(a)
    used = {}
    for k_all, r in enumerate(replies):
        key = (r["Company"], r["Role"])
        k = used[key] = used.get(key, 0) + 1
        if k > len(by_key.get(key, [])):
            die(f"replies.md has {k} row(s) for {key[0]!r} / {key[1]!r}, log.md has {len(by_key.get(key, []))}: "
                f"Company and Role must match a log.md row exactly")
        by_key[key][k - 1]["reply"] = r
        by_key[key][k - 1]["reply_n"] = k_all
    for n, r in enumerate(follow, start=1):
        _pair_follow(apps, r, n)["follow"].append(dict(r, _n=n))
    for a in apps:
        r, status = a["reply"], a["log"]["Status"].strip().lower()
        outcome = re.split(r"[\s(:;,.]", r.get("Outcome", "").strip().lower(), maxsplit=1)[0]
        a["closed_by"] = "status" if status == CLOSED else "reply" if outcome in CLOSING_OUTCOMES else ""
        a["closed"] = bool(a["closed_by"])
        a["heard"] = bool(r) and (r["Got back?"].strip().lower() == "yes" or r["Outcome"] not in ("Pending", ""))
    return apps


def app_id(folder):
    """The slug in a Folder cell (outreach/<slug>/), or None when the cell names no folder."""
    m = re.fullmatch(r"(?:outreach/)?([A-Za-z0-9][A-Za-z0-9._-]*)/?", folder.strip())
    return m.group(1) if m and m.group(1).lower() not in ("none", "n/a", "na") else None


def warnings(apps):
    """One line per log.md row whose Status is outside STATUSES: it is treated as open."""
    return [f"log.md row {a['n']} ({a['log']['Company']} / {a['log']['Role']}): Status '{a['log']['Status']}' is "
            f"not one of {', '.join(STATUSES)}; treated as open. An application that has ended is `closed`: "
            f"tracker.py normalize shows the fix, --apply writes it"
            for a in apps if a["log"]["Status"].strip().lower() not in STATUSES]


def warn(apps):
    for w in warnings(apps):
        print(f"WARN: {w}", file=sys.stderr)


def due(today=None, apps=None):
    """[{State, App, Company, Due, Action, Next}], most pressing first."""
    today = today or date.today()
    apps = load(need=("followups.md",)) if apps is None else apps
    out = []
    for a, r in sorted(((a, r) for a in apps for r in a["follow"]), key=lambda ar: ar[1]["_n"]):
        if _done(r["Done"], "followups.md Done") or a["closed_by"] == "status":
            continue
        if a["closed_by"] == "reply" and NUDGE.match(r["Action"]):
            continue
        when, shown = _trigger(r, f"followups.md Trigger ({r['Company']} / {r['Role']})")
        row = {"App": a["id"], "Company": r["Company"], "Action": r["Action"], "Due": shown, "When": when}
        if NUDGE.match(r["Action"]) and a["heard"]:
            row.update(State="answered", Next=f"a reply came in: no nudge; mark it done (tracker.py followup "
                                              f"{a['id']} done --action \"{r['Action']}\")")
        elif when is None:
            row.update(State="waiting", Next="when that happens")
        elif today < when:
            row.update(State="waiting", Next=f"in {(when - today).days} days")
        elif (today - when).days <= URGENT_DAYS:
            row.update(State="urgent", Next="do it today")
        else:
            row.update(State="overdue", Next=f"{(today - when).days} days late: do it now, or mark it done with why "
                                             f"(tracker.py followup {a['id']} done --action ... --note \"<why>\")")
        out.append(row)
    for a in apps:
        sent = min(_dates(a["log"]["Emails"], "log.md Emails"), default=None)
        if not sent or a["heard"] or a["closed"]:
            continue
        nudges = [r for r in a["follow"] if NUDGE.match(r["Action"])]
        if any(not r["Done"] for r in nudges):
            continue
        last = max([_day(r["Done"], "followups.md Done") or _trigger(r, "followups.md Trigger")[0] or sent
                    for r in nudges], default=None)
        quiet_since = last + timedelta(days=COLD_AFTER_NUDGE) if last else sent + timedelta(days=COLD_WITHOUT_NUDGE)
        if today >= quiet_since:
            out.append({"State": "cold", "App": a["id"], "Company": a["log"]["Company"], "Action": a["log"]["Role"],
                        "Due": a["log"]["Emails"], "When": quiet_since,
                        "Next": f"no reply after the one nudge: no second nudge; move on (tracker.py status "
                                f"{a['id']} closed --outcome \"Closed (no reply)\" hides it), and let review.md count it"})
    return sorted(out, key=lambda r: ORDER.index(r["State"]))


# ---- Writing: every change to the three tables goes through these commands, never a hand edit.

# replies.md Outcome: its first word is one of these; a reason may follow ("Rejected (role filled)").
OUTCOMES = ("Pending", "Interview", "Offer", "Rejected", "Expired", "Dropped", "Withdrawn", "Closed")
GOT = {"yes": "Yes", "auto-ack": "Auto-ack only"}
# log.md Status values found in older installs, and what normalize makes of each: (Status, Outcome).
OLD_STATUS = {"drafted": ("started", None), "draft": ("started", None)}
EDITABLE = ("JD URL", "Apply channel", "CV", "Contacts", "Emails")


def _first(s):
    return re.split(r"[\s(:;,.]", s.strip().lower(), maxsplit=1)[0]


def outcome_of(text):
    """The Outcome as written to replies.md, its first word spelled as in OUTCOMES; hard-fails on any other."""
    text = cell(text, "--outcome")
    word = _first(text)
    canon = next((o for o in OUTCOMES if o.lower() == word), None)
    if not canon:
        die(f"Outcome '{text}' must start with one of {', '.join(OUTCOMES)} (a reason may follow: "
            f"'Rejected (role filled)')")
    return canon + text[len(word):]


def find(apps, ident):
    """The one application ident names: its folder slug (outreach/<slug>/), or the id tracker.py
    shows for it (row-<n>, <slug>#<n>). Hard-fails on none, or on a slug two rows share."""
    ident = ident.strip().strip("/")
    ident = ident[len("outreach/"):] if ident.startswith("outreach/") else ident
    exact = [a for a in apps if a["id"] == ident]
    by_slug = [a for a in apps if app_id(a["log"]["Folder"]) == ident]
    if len(by_slug) > 1:
        die(f"'{ident}' is the Folder of {len(by_slug)} log.md rows ("
            + ", ".join(f"row {a['n']}, id {a['id']}" for a in by_slug)
            + "): name one by its id, or give each application its own folder")
    got = exact or by_slug
    if not got:
        die(f"no application '{ident}' in log.md: use the slug in its Folder cell (outreach/<slug>/), "
            f"or the id tracker.py build shows (row-<n> when the Folder cell names no folder)")
    return got[0]


class Edit:
    """The three tables open for one change, and the lines saying what changed."""

    def __init__(self):
        self.apps = load()
        self.log, self.replies, self.follow = (Table(OUT / "log.md", LOG_COLS), Table(OUT / "replies.md", REPLY_COLS),
                                               Table(OUT / "followups.md", FOLLOW_COLS))
        self.changes = []

    def say(self, a, what):
        self.changes.append(f"{a['id']} ({a['log']['Company']} / {a['log']['Role']}): {what}")

    def set_log(self, a, col, value):
        old = self.log.get(a["n"] - 3, col)
        if self.log.set(a["n"] - 3, col, value):
            self.say(a, f"log.md {col} '{old}' -> '{value}'")

    def reply_row(self, a):
        """The application's replies.md row index, appending `| Company | Role | No | | | Pending | |`
        when it has none (refused when that row would pair with another application)."""
        if "reply_n" in a:
            return a["reply_n"]
        key = (a["log"]["Company"], a["log"]["Role"])
        same = [b for b in self.apps if (b["log"]["Company"], b["log"]["Role"]) == key]
        have = sum(1 for b in same if "reply_n" in b)
        if same[have] is not a:
            die(f"replies.md has {have} row(s) for {key[0]!r} / {key[1]!r}, and the next one added would "
                f"belong to log.md row {same[have]['n']}, not row {a['n']}: add that application's row first")
        a["reply_n"] = self.replies.append([key[0], key[1], "No", "", "", "Pending", ""])
        a["reply"] = dict(zip(REPLY_COLS, self.replies.rows[a["reply_n"]][1]))
        self.say(a, "replies.md row added")
        return a["reply_n"]

    def set_reply(self, a, col, value):
        k = self.reply_row(a)
        old = self.replies.get(k, col)
        if self.replies.set(k, col, value):
            self.say(a, f"replies.md {col} '{old}' -> '{value}'")

    def add_note(self, a, note):
        k = self.reply_row(a)
        old = self.replies.get(k, "Notes")
        if note and note not in old:
            self.set_reply(a, "Notes", f"{old}; {note}" if old else note)

    def close_follow(self, a, done, nudges_only=False):
        for f in a["follow"]:
            k = f["_n"] - 1
            if not self.follow.get(k, "Done") and (not nudges_only or NUDGE.match(f["Action"])):
                self.follow.set(k, "Done", done)
                self.say(a, f"followups.md '{f['Action']}' done: {done}")

    def finish(self, write=True):
        if not self.changes:
            return False
        for line in self.changes:
            print(("" if write else "would: ") + line)
        if write:
            for t in (self.replies, self.follow, self.log):
                t.save()
        return True


def _status(e, a, status, outcome=None, note=None, force=None, today=None, sets=()):
    """Plan a Status change for application a into e. Hard-fails on a value outside STATUSES, a step
    back without force, and a close that says neither now nor before why it ended."""
    status = status.strip().lower()
    if status not in STATUSES:
        die(f"Status '{status}' is not one of {', '.join(STATUSES)}")
    cur = a["log"]["Status"].strip().lower()
    if outcome is not None and status != CLOSED:
        die("--outcome goes with Status closed; a reply's outcome is recorded with tracker.py reply")
    if cur not in STATUSES and not force:
        die(f"{a['id']}: its Status '{a['log']['Status']}' is outside the list: run tracker.py normalize, "
            f"or say why with --force \"<reason>\"")
    if cur in STATUSES and STATUSES.index(status) < STATUSES.index(cur) and not force:
        die(f"{a['id']}: Status goes forward only ({' -> '.join(STATUSES)}): '{cur}' -> '{status}' is a step "
            f"back. Say why with --force \"<reason>\"")
    for col, value in sets:
        if col == "Emails":
            _dates(value, "--set Emails")
        e.set_log(a, col, value)
    if status != a["log"]["Status"]:
        e.set_log(a, "Status", status)
        if force:
            e.add_note(a, f"{today} Status {cur} -> {status}: {force}")
    if status == CLOSED:
        _close(e, a, outcome, today)
    if note:
        e.add_note(a, note)


def _close(e, a, outcome, today):
    """The replies.md side of closing a: the Outcome (kept when it already closes it), and every open
    follow-up done."""
    if outcome is not None:
        e.set_reply(a, "Outcome", outcome_of(outcome))
    elif _first(a["reply"].get("Outcome", "")) not in CLOSING_OUTCOMES:
        die(f"{a['id']}: say why it ended, --outcome followed by one of {', '.join(OUTCOMES[3:])} "
            f"(a reason may follow: \"Rejected (role filled)\")")
    e.close_follow(a, f"{today} (closed)")


def cmd_normalize(o):
    """Each log.md Status outside STATUSES, rewritten into the list where a rule says how: another case
    of a listed value; drafted -> started; a closing word (dropped, expired, rejected <date>, ...) ->
    closed, with that word as the Outcome unless the Outcome already closes it. Anything else is named
    and left for the owner. Dry run unless --apply."""
    e = Edit()
    unknown = []
    for a in e.apps:
        raw = a["log"]["Status"]
        low = raw.strip().lower()
        if raw in STATUSES:
            continue
        word, rest = _first(low), raw.strip()[len(_first(low)):].strip()
        if low in STATUSES:
            e.set_log(a, "Status", low)
        elif word in OLD_STATUS:
            e.set_log(a, "Status", OLD_STATUS[word][0])
        elif word in CLOSING_OUTCOMES:
            e.set_log(a, "Status", CLOSED)
            closes = _first(a["reply"].get("Outcome", "")) in CLOSING_OUTCOMES
            _close(e, a, None if closes else f"{word} {rest}".strip(), o.date)
        else:
            unknown.append(f"{a['id']} ({a['log']['Company']} / {a['log']['Role']}): Status '{raw}' has no rule: "
                           f"ask the owner where it stands, then tracker.py status {a['id']} <status> --force "
                           f"\"<why>\"")
    changed = e.finish(write=o.apply)
    for line in unknown:
        print(line)
    if not changed and not unknown:
        print("nothing to change: every Status is one of " + ", ".join(STATUSES))
    elif changed and not o.apply:
        print("dry run: nothing written. Rerun with --apply to write it")


SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")


def cmd_start(o):
    """A new application: its log.md row (Status started, Folder outreach/<slug>/) and its replies.md
    row (Pending). Refuses a slug another row uses, and a Company + Role already in log.md unless the
    owner said re-apply (--reapply)."""
    if not SLUG.fullmatch(o.slug) or o.slug in ("none", "na", "n/a"):
        die(f"slug '{o.slug}' must be lowercase letters, digits and '-' (the company, then a role word: acme-pmm)")
    company, role, url = cell(o.company, "--company"), cell(o.role, "--role"), cell(o.url, "--url")
    if not (company and role and url):
        die("--company, --role and --url are each required, as they will stand in every table")
    e = Edit()
    mine = [a for a in e.apps if app_id(a["log"]["Folder"]) == o.slug]
    if mine:
        a = mine[0]
        if (a["log"]["Company"], a["log"]["Role"]) == (company, role):
            print(f"already: {o.slug} is in log.md (row {a['n']}, Status {a['log']['Status']})")
            return
        die(f"'{o.slug}' is already the Folder of log.md row {a['n']} ({a['log']['Company']} / "
            f"{a['log']['Role']}): give this application its own slug")
    same = [a for a in e.apps if (a["log"]["Company"].lower(), a["log"]["Role"].lower()) == (company.lower(), role.lower())]
    if same and not o.reapply:
        a = same[-1]
        die(f"{company} / {role} is already in log.md as {a['id']} (row {a['n']}, Status {a['log']['Status']}). "
            f"An earlier run that stopped midway resumes there; a new application to the same role needs the "
            f"owner to say re-apply (--reapply)")
    k = e.log.append([o.date, company, role, url, "", "", "", "", "started", f"outreach/{o.slug}/"])
    a = {"id": o.slug, "n": k + 3, "log": dict(zip(LOG_COLS, e.log.rows[k][1])), "reply": {}, "follow": []}
    e.apps.append(a)
    e.say(a, "log.md row added, Status started")
    e.reply_row(a)
    e.finish()


def cmd_status(o):
    e = Edit()
    a = find(e.apps, o.app)
    sets = []
    for kv in o.set:
        col, sep, value = kv.partition("=")
        if not sep or col.strip() not in EDITABLE:
            die(f"--set '{kv}': write Column=value, the column one of {', '.join(EDITABLE)}")
        sets.append((col.strip(), value))
    _status(e, a, o.status, o.outcome, o.note, o.force, o.date, sets)
    if not e.finish():
        print(f"already: {a['id']} is {a['log']['Status']}")


def cmd_reply(o):
    if o.got is None and o.outcome is None and (o.note or o.thread):
        e = Edit()  # a note alone: the answer sent, a detail of the thread
        a = find(e.apps, o.app)
        if o.thread:
            e.add_note(a, f"thread {cell(o.thread, '--thread')}")
        e.add_note(a, o.note)
        if not e.finish():
            print(f"already: {a['id']} has that note")
        return
    if o.got is None:
        die("--got is required: yes (a person wrote) or auto-ack; or give only --note to add a note")
    got = GOT.get(o.got.strip().lower()) or die(f"--got '{o.got}' must be yes (a person wrote) or auto-ack")
    if o.outcome is None:
        die(f"say what the reply means: --outcome followed by one of {', '.join(OUTCOMES)}")
    outcome = outcome_of(o.outcome)
    e = Edit()
    a = find(e.apps, o.app)
    have = a["reply"]
    if got == GOT["auto-ack"] and have.get("Got back?", "").strip().lower().startswith("yes"):
        pass  # a person's reply stands: an automatic acknowledgement adds only its thread
    else:
        if _first(have.get("Outcome", "")) in CLOSING_OUTCOMES and _first(outcome) not in CLOSING_OUTCOMES \
                and not o.force:
            die(f"{a['id']}: its Outcome '{have['Outcome']}' has closed it; '{outcome}' would reopen it. "
                f"Say why with --force \"<reason>\"")
        e.set_reply(a, "Got back?", got)
        e.set_reply(a, "Reply date", o.date)
        if o.sender:
            e.set_reply(a, "Reply from", o.sender)
        e.set_reply(a, "Outcome", outcome)
        if o.force:
            e.add_note(a, f"{o.date} Outcome {have.get('Outcome', '')} -> {outcome}: {o.force}")
    if o.thread:
        e.add_note(a, f"thread {cell(o.thread, '--thread')}")
    if o.note:
        e.add_note(a, o.note)
    closing = _first(outcome) in CLOSING_OUTCOMES
    if got == GOT["yes"] or closing:
        e.close_follow(a, f"{o.date} (replied)", nudges_only=True)
    if not e.finish():
        print(f"already: {a['id']} has that reply")
    if closing and a["log"]["Status"].strip().lower() != CLOSED:
        print(f"next: once the owner has moved on, tracker.py status {a['id']} closed")


def cmd_followup(o):
    e = Edit()
    a = find(e.apps, o.app)
    if not o.action or not o.action.strip():
        die("--action is required: what to do, e.g. \"N1 nudge manager\" (add), or the start of it (done)")
    if o.what == "add":
        if not o.trigger:
            die("--trigger is required: a date (YYYY-MM-DD), a span counted from today (\"3-5 days\"), or an event")
        row = dict(zip(FOLLOW_COLS, [o.date, a["log"]["Company"], a["log"]["Role"], cell(o.trigger, "--trigger"),
                                     cell(o.action, "--action"), o.source or "", ""]))
        _trigger(row, "--trigger")
        owner = _pair_follow(e.apps, row, len(e.follow.rows) + 1)
        if owner is not a:
            die(f"a follow-up for {row['Company']!r} / {row['Role']!r} added {o.date} belongs to the latest "
                f"application to that role by then, {owner['id']}, not {a['id']}")
        if any(f["Action"].lower() == row["Action"].lower() and not f["Done"] for f in a["follow"]):
            print(f"already: {a['id']} has an open follow-up '{row['Action']}'")
            return
        e.follow.append([row[c] for c in FOLLOW_COLS])
        e.say(a, f"followups.md row added: {row['Trigger']}, {row['Action']}")
    else:
        want = o.action.strip().lower()
        hits = [f for f in a["follow"] if f["Action"].lower().startswith(want)]
        open_ = [f for f in hits if not f["Done"]]
        if len(open_) > 1:
            die(f"{a['id']}: {len(open_)} open follow-ups start with '{o.action}' ("
                + "; ".join(f["Action"] for f in open_) + "): give more of the Action")
        if not open_:
            if hits:
                print(f"already: {a['id']} '{hits[0]['Action']}' is done ({hits[0]['Done']})")
                return
            die(f"{a['id']}: no follow-up starts with '{o.action}'. Its open ones: "
                + ("; ".join(f["Action"] for f in a["follow"] if not f["Done"]) or "none"))
        done = f"{o.date} ({cell(o.note, '--note')})" if o.note else o.date
        e.follow.set(open_[0]["_n"] - 1, "Done", done)
        e.say(a, f"followups.md '{open_[0]['Action']}' done: {done}")
    e.finish()


class _Args(argparse.ArgumentParser):
    def error(self, message):
        die(f"{message}. Usage: tracker.py --help")


def _iso(s):
    if not ISO.fullmatch(s):
        die(f"--date '{s}' must be written YYYY-MM-DD")
    return _day(s, "--date").isoformat()


def parse(argv):
    ap = _Args(prog="tracker.py", add_help=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", add_help=False)
    s.add_argument("app")
    s.add_argument("status")
    s.add_argument("--outcome")
    s.add_argument("--note")
    s.add_argument("--force", metavar="REASON")
    s.add_argument("--set", action="append", default=[], metavar="COLUMN=VALUE")
    s.add_argument("--date", type=_iso, default=date.today().isoformat())
    r = sub.add_parser("reply", add_help=False)
    r.add_argument("app")
    r.add_argument("--got")
    r.add_argument("--outcome")
    r.add_argument("--from", dest="sender")
    r.add_argument("--thread")
    r.add_argument("--note")
    r.add_argument("--force", metavar="REASON")
    r.add_argument("--date", type=_iso, default=date.today().isoformat())
    f = sub.add_parser("followup", add_help=False)
    f.add_argument("app")
    f.add_argument("what", choices=("add", "done"))
    f.add_argument("--action")
    f.add_argument("--trigger")
    f.add_argument("--source")
    f.add_argument("--note")
    f.add_argument("--date", type=_iso, default=date.today().isoformat())
    n = sub.add_parser("normalize", add_help=False)
    n.add_argument("--apply", action="store_true")
    n.add_argument("--date", type=_iso, default=date.today().isoformat())
    st = sub.add_parser("start", add_help=False)
    st.add_argument("slug")
    st.add_argument("--company", required=True)
    st.add_argument("--role", required=True)
    st.add_argument("--url", required=True)
    st.add_argument("--reapply", action="store_true")
    st.add_argument("--date", type=_iso, default=date.today().isoformat())
    return ap.parse_args(argv)


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(sys.argv) > 1 and sys.argv[1] in WRITERS:
        o = parse(sys.argv[1:])
        WRITERS[o.cmd](o)
        return
    if len(sys.argv) != 2 or sys.argv[1] not in ("init", "build", "due"):
        die(__doc__)
    if sys.argv[1] == "due":
        apps = load(need=("followups.md",))
        warn(apps)
        rows = due(apps=apps)
        if not rows:
            print("nothing due")
            return
        cols = ["State", "Company", "Due", "Action", "Next"]
        print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
        for r in rows:
            print("| " + " | ".join(r[c] for c in cols) + " |")
        return
    init() if sys.argv[1] == "init" else build()


WRITERS = {"start": cmd_start, "status": cmd_status, "reply": cmd_reply, "followup": cmd_followup, "normalize": cmd_normalize}

if __name__ == "__main__":
    run(main)
