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
that says not done ("No", "-")."""
import csv
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


def read_table(path, expected):
    if not path.exists():
        die(f"{path} missing: run tracker.py init")
    lines = [l for l in read_text(path).splitlines() if l.strip().startswith("|")]
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
    for r in replies:
        key = (r["Company"], r["Role"])
        k = used[key] = used.get(key, 0) + 1
        if k > len(by_key.get(key, [])):
            die(f"replies.md has {k} row(s) for {key[0]!r} / {key[1]!r}, log.md has {len(by_key.get(key, []))}: "
                f"Company and Role must match a log.md row exactly")
        by_key[key][k - 1]["reply"] = r
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
            f"not one of {', '.join(STATUSES)}; treated as open. An application that has ended is `closed`"
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


if __name__ == "__main__":
    run(main)
