#!/usr/bin/env python3
"""Preview, approve and send application emails. Stdlib only.

Usage:
  mail.py preview <slug>... [--only KEY] [--repeat-ok] [--no-open]
        print what would be sent, and write the owner's preview page (outreach/preview.html,
        opened in their browser). That page, and only that page, carries a one-time approval code.
  mail.py approve --code <code> --quote "..."
        record the owner's green light for exactly what the last preview showed.
        <code> is what the owner read on their page; --quote is their own words.
  mail.py send <slug>...
        send what was approved. Each approval works once and for 30 minutes.
  mail.py cancel [<slug>...] withdraw the waiting preview and any unused approval (all, or the named)
  mail.py test <slug>       send this application's first emails to the owner's own address, [TEST]
  mail.py status <slug>...  approval state and what was sent
  mail.py ledger            every email sent so far, across all applications
  mail.py check <slug>... [--only KEY] [--repeat-ok]
        the drafts route (flow/send.md § Setup B): every refusal preview applies, then print the
        emails to put in the owner's drafts. Writes nothing, approves nothing, needs no .env.
  mail.py draft <slug>... [--only KEY] [--repeat-ok]
        the drafts route with the CV attached automatically: every refusal check applies, then
        each email is saved, CV attached, in the Drafts folder of the owner's mailbox (IMAP) and
        read back to prove text and attachment arrived unchanged. Sends nothing: the owner opens
        each draft and presses Send. A draft with the same recipient and subject already there is
        left alone, so a rerun never makes doubles. Needs MAIL_ADDRESS and MAIL_APP_PASSWORD in .env.

<slug> = folder name under outreach/ (or a path to that folder; folders elsewhere are refused).
KEY = hm (T1 to the hiring manager), rec (T2 to the recruiter), hm-nudge (N1), rec-nudge (N2),
hm-cv (C1), rec-cv (C2): the CV follow-up, a reply carrying the CV on a first email that went out
by hand without it (messages.md hm_sent / rec_sent: its date and Message-ID).
Without --only, preview takes every email of the application that is due and unsent.
Nudges carry the CV when profile.json nudge_attaches_cv is true.

check, preview, approve and send all refuse when: messages.md fails validation; an address is on
outreach/do-not-contact.md; the application is not in yet (log.md Status is anything but
submitted or sent); an email says "today" but `applied` is another day; the same address was
already emailed for another application (--repeat-ok at preview lets the owner decide, with
the fact shown on their page); the daily cap (profile max_emails_per_day) would be passed.
First emails the owner sent themselves (messages.md hm_sent / rec_sent) count as sent for every
one of these rules, in every application.

Add --profile <profile.json> to use a profile other than profile/profile.json.
Reads MAIL_ADDRESS and MAIL_APP_PASSWORD from <repo>/.env (optional SMTP_HOST, SMTP_PORT;
default smtp.gmail.com:465; for draft, IMAP_HOST, IMAP_PORT, default imap.gmail.com:993).
Hard-fails on anything missing."""
import argparse
import hashlib
import html
import imaplib
import json
import mimetypes
import os
import re
import secrets
import smtplib
import ssl
import time
import webbrowser
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, getaddresses, make_msgid
from pathlib import Path

from _common import CLOUD_FIX, ROOT, die, env, in_cloud, run
from tracker import LOG_COLS, read_table
from validate import SENT_OUTSIDE, check, is_none, load_profile, messages_for, parse, sent_outside

APPROVAL_MINUTES = 30
NUDGE_AFTER_DAYS = 7  # the nudge says "I wrote last week"
CODE_TRIES = 3
STAMP = "%Y-%m-%dT%H:%M:%SZ"
OUT = ROOT / "outreach"
PENDING = OUT / "pending.json"
PAGE = OUT / "preview.html"
LOCK = OUT / "send.lock"
IN = ("submitted", "sent")
FIRST = (("hm", "T1", "N1", "C1"), ("rec", "T2", "N2", "C2"))
KEYS = ["hm", "rec", "hm-nudge", "rec-nudge", "hm-cv", "rec-cv"]


# ---------- state files ----------

def now():
    return datetime.now(timezone.utc)


OWNER_REPAIRS = ("Tell the owner, and stop: this is a state file you never open (AGENTS.md, Green light). "
                 "They open it in a text editor and fix it themselves, keeping every entry")


def stamp(text, where):
    try:
        return datetime.strptime(text, STAMP).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        die(f"{where}: bad timestamp {text!r}. {OWNER_REPAIRS}")


def minutes_since(text, where):
    age = (now() - stamp(text, where)).total_seconds() / 60
    if age < -2:
        die(f"{where}: its timestamp {text} is in the future (was the computer's clock changed?). "
            f"Run mail.py cancel, then preview again")
    return age


def read_json(path, default, kind):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"{path} is damaged ({e}). It is part of the record that prevents double sends. {OWNER_REPAIRS}")
    if not isinstance(data, kind):
        die(f"{path} is damaged (wrong shape). {OWNER_REPAIRS}")
    return data


def write_json(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def folder_of(slug):
    p = Path(slug)
    if not p.is_dir():
        p = OUT / slug
    if not p.is_dir():
        die(f"application folder not found: {slug}")
    if not (p / "messages.md").is_file():
        die(f"{p}/messages.md not found")
    if p.resolve().parent != OUT.resolve():  # elsewhere it would escape the log check, ledger and cap
        die(f"{p}: an application folder must sit directly in outreach/ (outreach/<slug>/)")
    return p.resolve()


def sent_of(folder):
    path = folder / "sent.json"
    rows = read_json(path, [], list)
    for r in rows:
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) for k in ("key", "to", "at")):
            die(f"{path}: malformed entry {r!r}. {OWNER_REPAIRS}")
        stamp(r["at"], path)
    return rows


def sent_by_hand(folder):
    """First emails the owner sent themselves (from drafts, or their own mail app), recorded in
    messages.md as hm_sent / rec_sent. Read from the front matter alone, so one application's
    unfinished draft text never blocks the others."""
    path = folder / "messages.md"
    if not path.is_file():
        return []
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"), re.S)
    if not m:
        return []
    meta = {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in m.group(1).splitlines())}
    out = []
    for side in ("hm", "rec"):
        v = meta.get(f"{side}_sent", "")
        if not v or is_none(v):
            continue
        hit = SENT_OUTSIDE.fullmatch(v)
        if not hit:
            die(f"{path}: {side}_sent is '{v}'; write the date it went, then its <Message-ID> when known "
                f"(flow/messages.md)")
        to = meta.get(f"{side}_email", "")
        if not to or is_none(to):
            die(f"{path}: {side}_sent is set but {side}_email names no address")
        out.append({"key": side, "to": to, "at": f"{hit.group(1)}T12:00:00Z", "outside": True,
                    "message_id": hit.group(2) or ""})
    return out


def ledger(extra=()):
    """[(folder, sent entry)] across every application folder: what mail.py sent, plus first
    emails the owner sent by hand (an entry with "outside": True)."""
    folders = sorted(p.resolve() for p in OUT.iterdir() if p.is_dir()) if OUT.is_dir() else []
    folders += [f for f in extra if f not in folders]
    rows = []
    for f in folders:
        mine = sent_of(f)
        rows += [(f, r) for r in mine]
        rows += [(f, r) for r in sent_by_hand(f)
                 if not any(x["key"] == r["key"] and x["to"].lower() == r["to"].lower() for x in mine)]
    return rows


def blocked():
    p = OUT / "do-not-contact.md"
    out = set()
    if p.exists():
        for n, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), start=1):
            line = line.strip()
            if not line or line[0] in "#>":
                continue
            found = [x.strip("'.") for x in re.findall(r"[\w.+'-]*@[\w-]+(?:\.[\w-]+)+", line)]
            if not found:
                die(f"{p} line {n}: no address (name@company.com) or company (@company.com) found in "
                    f"{line!r}. Fix the line; notes go after the address, comments start with >")
            out.update(x.lower() for x in found)
    return out


# ---------- what could be sent ----------

def candidates(folder, profile):
    """Validate, then list every email this application defines, each with `skip` = why it
    cannot go now (None = it can)."""
    path = folder / "messages.md"
    violations, _ = check(path, profile)
    if violations:
        die(f"{path} fails validation:\n - " + "\n - ".join(violations))
    meta, secs = parse(path)
    sent = sent_of(folder)

    def last(keys, to):
        hits = [r for r in sent if r["key"] in keys and r["to"].lower() == to.lower()]
        return hits[-1] if hits else None

    def went(r):
        if r.get("outside"):
            return f"sent outside this script on {r['at'][:10]} (messages.md {r['key']}_sent)"
        if r.get("state") == "sending":
            return (f"a send to this address started {r['at']} and was never confirmed: the owner "
                    f"checks their Sent folder and decides")
        return f"already sent {r['at']}"

    items = []
    for key, sec, nsec, csec in FIRST:
        to = meta[f"{key}_email"]
        if is_none(to):
            continue
        subj, body = secs[sec]
        base = dict(to=to, name=meta[f"{key}_name"], conf=meta[f"{key}_email_confidence"])
        done = last(("hm", "rec"), to)
        outside = sent_outside(meta, key)
        if not done and outside:  # the owner sent it by hand: nudges and the CV follow-up reply to it
            done = {"key": key, "to": to, "at": f"{outside[0]}T00:00:00Z", "message_id": outside[1],
                    "outside": True}
        items.append(dict(base, key=key, subject=subj, body=body, attach=True, first=True, reply_to=None,
                          skip=went(done) if done else None))
        if csec in secs and not is_none(secs[csec][1]):
            cdone = last((key + "-cv",), to)
            if cdone:
                why = went(cdone)
            elif not done or not done.get("outside"):
                why = (f"a CV follow-up is for a first email sent outside this script ({key}_sent); "
                       f"this script's own first email already carries the CV")
            elif not done.get("message_id"):
                why = f"{key}_sent has no <Message-ID> to reply to: add it after the date"
            else:
                why = None
            items.append(dict(base, key=key + "-cv", subject="Re: " + subj, body=secs[csec][1], attach=True,
                              first=False, reply_to=done.get("message_id") if done else None, skip=why))
        if nsec in secs and not is_none(secs[nsec][1]):
            ndone = last(("hm-nudge", "rec-nudge"), to)
            if ndone:
                why = went(ndone)
            elif not done:
                why = "the first email to this address has not been sent"
            elif done.get("state") == "sending" and not done.get("outside"):
                why = went(done)
            elif now() - stamp(done["at"], folder / "sent.json") < timedelta(days=NUDGE_AFTER_DAYS):
                why = f"the first email went {done['at']}; a nudge waits {NUDGE_AFTER_DAYS} days"
            elif not done.get("message_id"):
                why = "the first email has no recorded message id to reply to"
            else:
                why = None
            items.append(dict(base, key=key + "-nudge", subject="Re: " + subj, body=secs[nsec][1],
                              attach=profile["nudge_attaches_cv"], first=False,
                              reply_to=done.get("message_id") if done else None, skip=why))
    return meta, items


def choose(items, only, name):
    if only:
        hit = [i for i in items if i["key"] == only]
        if not hit:
            die(f"{name}: no {only} email exists (no address, or no text for it in messages.md)")
        if hit[0]["skip"]:
            die(f"{name}: {only}: {hit[0]['skip']}")
        return hit
    todo = [i for i in items if not i["skip"]]
    if not todo:
        state = "; ".join(f"{i['key']}: {i['skip']}" for i in items) or "no contact has an address (LinkedIn texts only)"
        die(f"{name}: nothing to send. {state}")
    return todo


def guard(folder, meta, items, profile, repeat_ok, book, bl):
    """Refuse anything the owner should not be sending. Adds `note` to items shown with a warning."""
    for i in items:
        addr = i["to"].lower()
        if addr in bl or "@" + addr.split("@")[1] in bl:
            die(f"{folder.name}: {i['to']} is on outreach/do-not-contact.md")
    for i in items:
        if not i["key"].endswith("-nudge"):
            continue
        prior = [(f, r) for f, r in book if f != folder and r["key"].endswith("-nudge")
                 and r["to"].lower() == i["to"].lower()]
        if prior:
            die(f"{folder.name}: {i['to']} already had a nudge on {prior[-1][1]['at'][:10]} for "
                f"{prior[-1][0].name}: one nudge per person, ever (flow/messages.md)")
    firsts = [i for i in items if i["first"]]
    if not firsts:
        return
    if folder.parent == OUT and meta["channel"] != "email":
        rows = [r for r in read_table(OUT / "log.md", LOG_COLS)
                if re.split(r"[\\/]", r["Folder"].strip("`/\\ "))[-1] == folder.name]
        if not rows:
            die(f"{folder.name}: no row in outreach/log.md whose Folder cell is outreach/{folder.name}/")
        if rows[-1]["Status"] not in IN:
            die(f"{folder.name}: log.md Status is '{rows[-1]['Status']}'. Emails go out only once the "
                f"application is in: Status must be one of {IN}")
    if meta["channel"] != "email" and date.fromisoformat(meta["applied"]) != date.today():
        for i in firsts:
            for w in messages_for(profile, meta)["today_words"]:
                if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", i["body"], re.I):
                    die(f"{folder.name}: the {i['key']} email says '{w}' but the application went in on "
                        f"{meta['applied']}. Write the real day (flow/messages.md, Tone 9)")
    for i in firsts:
        prior = [(f, r) for f, r in book if f != folder and r["to"].lower() == i["to"].lower()]
        if prior:
            f, r = prior[-1]
            fact = f"{i['to']} was already emailed on {r['at'][:10]} for {f.name}"
            if not repeat_ok:
                die(f"{folder.name}: {fact}. Tell the owner. To write to them again anyway, rerun "
                    f"preview with --repeat-ok: their preview page will show this fact")
            i["note"] = fact


def digest(folder, meta):
    h = hashlib.sha256()
    h.update((folder / "messages.md").read_bytes())
    h.update((folder / meta["cv"]).read_bytes())
    return h.hexdigest()


def gather(slugs, profile, pick, repeat_ok):
    """[(app dict)] for the named applications. pick(folder, items) selects; repeat_ok(folder) -> bool."""
    folders = [folder_of(s) for s in slugs]
    if len(set(folders)) != len(folders):
        die("the same application is named twice")
    book, bl = ledger(folders), blocked()
    apps, seen = [], {}
    for f in folders:
        meta, every = candidates(f, profile)
        items = pick(f, every)
        hm = next((i for i in every if i["key"] == "hm"), None)
        if hm and not hm["skip"] and any(i["key"] == "rec" for i in items) and hm not in items:
            die(f"{f.name}: the recruiter email tells {meta['rec_name']} you also wrote to {meta['hm_name']}, "
                f"but the email to {meta['hm_name']} has not gone. Send both together (preview without "
                f"--only), or send the manager's first")
        guard(f, meta, items, profile, repeat_ok(f), book, bl)
        for i in items:
            other = seen.setdefault(i["to"].lower(), f.name)
            if other != f.name:
                die(f"{i['to']} would get an email from both {other} and {f.name}: one person gets "
                    f"one email. Set that address to none in one of them")
        apps.append(dict(folder=f, meta=meta, items=items, sha=digest(f, meta)))
    return apps, book


def cap_check(profile, book, n):
    done = sum(stamp(r["at"], "sent.json").astimezone().date() == date.today() for _, r in book)
    cap = profile["max_emails_per_day"]
    if done + n > cap:
        die(f"daily cap: {done} sent today + {n} now > {cap} (profile max_emails_per_day). "
            f"Send fewer, or tomorrow")


# ---------- SMTP ----------

def build(profile, sender, item, cv_path, to=None, subject=None, body=None):
    msg = EmailMessage()
    msg["From"] = formataddr((profile["name"], sender))
    msg["To"] = to or item["to"]
    msg["Subject"] = subject or item["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[1])
    if item["reply_to"]:
        msg["In-Reply-To"] = item["reply_to"]
        msg["References"] = item["reply_to"]
    msg.set_content((body or item["body"]) + "\n")
    if item["attach"]:
        ctype = mimetypes.guess_type(cv_path.name)[0] or "application/octet-stream"
        main_t, sub_t = ctype.split("/", 1)
        msg.add_attachment(cv_path.read_bytes(), maintype=main_t, subtype=sub_t, filename=cv_path.name)
    return msg


def sender_cfg(profile):
    cfg = env("MAIL_ADDRESS", "MAIL_APP_PASSWORD")
    if cfg["MAIL_ADDRESS"].lower() != profile["email"].lower():
        die(f"MAIL_ADDRESS in .env ({cfg['MAIL_ADDRESS']}) differs from profile email ({profile['email']})")
    cfg["host"] = cfg.get("SMTP_HOST") or "smtp.gmail.com"
    try:
        cfg["port"] = int(cfg.get("SMTP_PORT") or 465)
    except ValueError:
        die(f"SMTP_PORT in .env must be a number, got {cfg.get('SMTP_PORT')!r}")
    if cfg["host"] == "smtp.gmail.com":  # Google shows app passwords in four spaced groups
        cfg["MAIL_APP_PASSWORD"] = "".join(cfg["MAIL_APP_PASSWORD"].split())
    return cfg


def smtp_send(cfg, msgs):
    host, port = cfg["host"], cfg["port"]
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=60)
        else:
            server = smtplib.SMTP(host, port, timeout=60)
            server.starttls(context=ctx)
        with server:
            server.login(cfg["MAIL_ADDRESS"], cfg["MAIL_APP_PASSWORD"])
            for msg, hooks in msgs:
                hooks("before")
                try:
                    server.send_message(msg)
                except (smtplib.SMTPRecipientsRefused, smtplib.SMTPResponseException):
                    hooks("undo")  # the server answered with a refusal: nothing was taken
                    raise
                except BaseException as e:  # the line broke: the server may already have the email
                    hooks("unsure", e)
                    raise
                hooks("after")
    except smtplib.SMTPAuthenticationError as e:
        die(f"the mail server refused the login ({e.smtp_code}). Check MAIL_ADDRESS and the app "
            f"password in .env (flow/send.md § Setup)")
    except smtplib.SMTPException as e:
        die(f"SMTP error: {e}")
    except OSError as e:
        die(f"cannot reach {host}:{port}: {e}" + (f". {CLOUD_FIX}" if in_cloud() else ""))


# ---------- IMAP drafts ----------

LIST_ROW = re.compile(rb'\((?P<flags>[^)]*)\) (?:"(?:[^"\\]|\\.)*"|NIL) (?P<name>.+)$', re.I)


def imap_cfg(profile):
    cfg = sender_cfg(profile)
    host = cfg.get("IMAP_HOST") or ("imap.gmail.com" if cfg["host"] == "smtp.gmail.com" else "")
    if not host:
        die("IMAP_HOST missing in .env: with your own SMTP_HOST, also set IMAP_HOST (and IMAP_PORT when "
            "it is not 993) from your mail provider's help page")
    try:
        cfg["imap_port"] = int(cfg.get("IMAP_PORT") or 993)
    except ValueError:
        die(f"IMAP_PORT in .env must be a number, got {cfg.get('IMAP_PORT')!r}")
    cfg["imap_host"] = host
    if host == "imap.gmail.com":
        cfg["MAIL_APP_PASSWORD"] = "".join(cfg["MAIL_APP_PASSWORD"].split())
    return cfg


def quoted(name):
    if name.startswith('"') and name.endswith('"') and len(name) > 1:
        return name
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ok(reply, what):
    typ, data = reply
    if typ != "OK":
        die(f"the mail server refused to {what}: {data!r}")
    return data


def drafts_box(imap):
    """The mailbox's Drafts folder, by its \\Drafts flag (its name differs by language: [Gmail]/Entwürfe)."""
    boxes = []
    for row in ok(imap.list(), "list its folders") or []:
        if isinstance(row, tuple):  # a name sent as a literal: (b'(\\Drafts) "/" {6}', b'Drafts')
            m = LIST_ROW.match(row[0])
            name = quoted(row[1].decode("utf-8", "replace")) if m else None
        else:
            m = LIST_ROW.match(row or b"")
            name = m.group("name").decode("utf-8", "replace").strip() if m else None
        if m:
            boxes.append((m.group("flags").decode("ascii", "replace").lower().split(), name))
    for flags, name in boxes:
        if "\\drafts" in flags:
            return name
    for flags, name in boxes:
        if name.strip('"').lower() == "drafts":
            return name
    die(f"no Drafts folder in this mailbox (folders: {[n for _, n in boxes]}). Save the drafts "
        f"through the mail tool instead (flow/send.md § Setup B)")


def mail_key(to, subject):
    return (frozenset(a.lower() for _, a in getaddresses([str(to or "")]) if a), str(subject or "").strip())


def drafts_there(imap, box):
    """{(recipients, subject)} of every draft already in the folder."""
    n = int((ok(imap.select(quoted(box)), f"open {box}") or [b"0"])[0] or 0)
    if not n:
        return set()
    out = set()
    for part in ok(imap.fetch("1:*", "(BODY.PEEK[HEADER.FIELDS (TO SUBJECT)])"), "read the drafts"):
        if isinstance(part, tuple):
            h = message_from_bytes(part[1], policy=policy.default)
            out.add(mail_key(h["To"], h["Subject"]))
    return out


def read_back(imap, box, mid):
    """The stored draft whose Message-ID is mid, parsed; None when the folder has no such draft."""
    ok(imap.select(quoted(box)), f"open {box}")
    uids = (ok(imap.uid("SEARCH", None, "HEADER", "Message-ID", quoted(mid)), "search the drafts")
            or [b""])[0].split()
    if not uids:
        return None
    for part in ok(imap.uid("FETCH", uids[-1], "(BODY.PEEK[])"), "read the draft back"):
        if isinstance(part, tuple):
            return message_from_bytes(part[1], policy=policy.default)
    return None


def proof(stored, item, cv):
    """Why the stored draft differs from what check showed, or None when it matches."""
    if stored is None:
        return "it is not in the Drafts folder after saving"
    if mail_key(stored["To"], stored["Subject"]) != mail_key(item["to"], item["subject"]):
        return "its recipient or subject changed"
    body = stored.get_body(("plain",))
    if body is None or body.get_content().strip() != item["body"].strip():
        return "its text changed"
    files = [p.get_payload(decode=True) for p in stored.iter_attachments()]
    if not item["attach"]:
        return "it carries an attachment it should not" if files else None
    want = hashlib.sha256(cv.read_bytes()).hexdigest()
    if [hashlib.sha256(f or b"").hexdigest() for f in files] != [want]:
        return f"its attachment is not {cv.name} byte for byte"
    return None


def imap_open(cfg):
    host, port = cfg["imap_host"], cfg["imap_port"]
    try:
        imap = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=60)
    except OSError as e:
        die(f"cannot reach {host}:{port}: {e}" + (f". {CLOUD_FIX}" if in_cloud() else ""))
    try:
        imap.login(cfg["MAIL_ADDRESS"], cfg["MAIL_APP_PASSWORD"])
    except imaplib.IMAP4.error as e:
        die(f"the mail server refused the login ({e}). Check MAIL_ADDRESS and the app password in .env "
            f"(flow/send.md § Setup B)")
    return imap


# ---------- commands ----------

def show(apps, profile):
    for x in apps:
        cv = x["folder"] / x["meta"]["cv"]
        for i in x["items"]:
            print("=" * 72)
            print(f"{x['meta']['company']}, {x['meta']['role']}   [{x['folder'].name} {i['key']}]")
            print(f"To:         {i['name']} <{i['to']}>   (address confidence {i['conf']})")
            if i.get("note"):
                print(f"WARNING:    {i['note']}")
            print(f"From:       {profile['name']} <{profile['email']}>")
            print(f"Subject:    {i['subject']}")
            att = cv.name + f" ({max(1, cv.stat().st_size // 1024)} KB)" if i["attach"] else "none"
            print(f"Attachment: {att}" + ("   (sent as a reply on the first email)" if i["reply_to"] else ""))
            print("-" * 72)
            print(i["body"])
    print("=" * 72)


def page(apps, profile, code):
    e = html.escape
    n = sum(len(x["items"]) for x in apps)
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           "<title>Emails waiting for your approval</title><style>",
           "body{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:2em auto;padding:0 1em;color:#111;background:#fff}",
           ".mail{border:1px solid #bbb;border-radius:8px;padding:1em;margin:1em 0}",
           "pre{white-space:pre-wrap;font:inherit;border-top:1px solid #ddd;padding-top:1em}",
           ".warn{color:#a00000;font-weight:600}.box{border:2px solid #111;border-radius:8px;padding:1em}",
           ".code{font-size:1.6em;font-weight:700;letter-spacing:.05em}",
           "</style></head><body>",
           f"<h1>{n} email{'s' if n != 1 else ''} waiting for your approval</h1>",
           f"<p>Nothing has been sent. Read each one. Made {e(now().strftime('%Y-%m-%d %H:%M'))} UTC; "
           f"the code below works for {APPROVAL_MINUTES} minutes.</p>"]
    for x in apps:
        cv = x["folder"] / x["meta"]["cv"]
        for i in x["items"]:
            att = (e(cv.name) if i["attach"] else "none") + (" (sent as a reply on your first email)"
                                                              if i["reply_to"] else "")
            warn = f'<p class="warn">Warning: {e(i["note"])}</p>' if i.get("note") else ""
            out.append(
                f'<div class="mail"><h2>{e(x["meta"]["company"])}: {e(x["meta"]["role"])}</h2>{warn}'
                f'<p><b>To:</b> {e(i["name"])} &lt;{e(i["to"])}&gt; (address confidence: {e(i["conf"])})<br>'
                f'<b>From:</b> {e(profile["name"])} &lt;{e(profile["email"])}&gt;<br>'
                f'<b>Subject:</b> {e(i["subject"])}<br><b>Attachment:</b> {att}</p>'
                f'<pre>{e(i["body"])}</pre></div>')
    out.append(f'<div class="box"><h2>To send all of the above</h2><p>Tell your assistant:</p>'
               f'<p class="code">send {code}</p>'
               f"<p>To change or hold anything, tell your assistant in your own words instead. "
               f"After any change you get a new page and a new code.</p></div></body></html>")
    return "\n".join(out)


def code_hash(salt, code):
    return hashlib.sha256((salt + code).encode()).hexdigest()


def cmd_preview(a, profile):
    if a.only and len(a.slugs) != 1:
        die("--only works with one application at a time")
    apps, book = gather(a.slugs, profile, lambda f, items: choose(items, a.only, f.name),
                        lambda f: a.repeat_ok)
    n = sum(len(x["items"]) for x in apps)
    cap_check(profile, book, n)
    for x in apps:  # a new preview replaces any earlier green light for these applications
        (x["folder"] / "approval.json").unlink(missing_ok=True)
    code, salt = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(8)
    OUT.mkdir(exist_ok=True)
    write_json(PENDING, {
        "created": now().strftime(STAMP), "salt": salt, "code_hash": code_hash(salt, code),
        "tries": 0, "repeat_ok": bool(a.repeat_ok),
        "apps": [{"folder": str(x["folder"]), "sha": x["sha"], "keys": [i["key"] for i in x["items"]]}
                 for x in apps]})
    PAGE.write_text(page(apps, profile, code), encoding="utf-8")
    show(apps, profile)
    opened = False if a.no_open else webbrowser.open(PAGE.as_uri())
    print(f"{n} email(s). Nothing was sent.")
    print(f"Owner's preview page: {PAGE}" + (" (opened in their browser)" if opened else
          " (NOT opened: ask the owner to open this file themselves)"))
    print("The approval code is on that page only. The owner reads it there and tells you; "
          "that page is theirs to open, not yours.")


def cmd_approve(a, profile):
    if a.slugs:
        die("approve takes no application names: it covers exactly what the last preview showed")
    if not a.quote or not a.quote.strip():
        die("approve needs --quote with the owner's approving words, verbatim")
    pend = read_json(PENDING, None, dict)
    if not pend:
        die("no preview is waiting. Run preview; the owner reads their page and gives you its code")
    age = minutes_since(pend.get("created"), PENDING)
    if age > APPROVAL_MINUTES:
        PENDING.unlink()
        die(f"that preview is {int(age)} minutes old (limit {APPROVAL_MINUTES}). Run preview again")
    code = re.sub(r"\D", "", a.code or "")
    if code_hash(pend["salt"], code) != pend["code_hash"]:
        pend["tries"] += 1
        if pend["tries"] >= CODE_TRIES:
            PENDING.unlink()
            die("wrong code, and that was the last try: this preview is cancelled. Run preview again")
        write_json(PENDING, pend)
        die(f"wrong code (try {pend['tries']} of {CODE_TRIES}). The code is on the owner's preview "
            f"page; ask them to read it to you")
    want = {Path(p["folder"]): p for p in pend["apps"]}
    apps, _ = gather([p["folder"] for p in pend["apps"]], profile,
                     lambda f, items: [i for i in items if i["key"] in want[f]["keys"] and not i["skip"]],
                     lambda f: pend["repeat_ok"])
    for x in apps:
        p = want[x["folder"]]
        if x["sha"] != p["sha"] or [i["key"] for i in x["items"]] != p["keys"]:
            PENDING.unlink()
            die(f"{x['folder'].name} changed after the preview the owner read. Run preview again")
    at = now().strftime(STAMP)
    for x in apps:
        write_json(x["folder"] / "approval.json", {
            "sha256": x["sha"], "at": at, "quote": a.quote.strip(), "repeat_ok": pend["repeat_ok"],
            "keys": [i["key"] for i in x["items"]], "recipients": [i["to"] for i in x["items"]]})
        print(f"approved {x['folder'].name}: {[i['to'] for i in x['items']]}")
    PENDING.unlink()
    print(f"valid {APPROVAL_MINUTES} minutes, for one send: "
          f"mail.py send {' '.join(x['folder'].name for x in apps)}")


def cmd_send(a, profile):
    with send_lock():  # before the checks, so two runs cannot both pass them
        _send(a, profile)


def _send(a, profile):
    want = {}
    for s in a.slugs:
        f = folder_of(s)
        ap = read_json(f / "approval.json", None, dict)
        if not ap:
            die(f"{f.name}: not approved, or its approved emails have already gone (mail.py status "
                f"{f.name}). Otherwise: preview, the owner reads their page and gives you its code, approve")
        age = minutes_since(ap.get("at"), f / "approval.json")
        if age > APPROVAL_MINUTES:
            die(f"{f.name}: the approval is {int(age)} minutes old (limit {APPROVAL_MINUTES}). "
                f"Preview again and get a new green light")
        want[f] = ap
    apps, book = gather(a.slugs, profile,
                        lambda f, items: [i for i in items if i["key"] in want[f]["keys"] and not i["skip"]],
                        lambda f: bool(want[f].get("repeat_ok")))
    for x in apps:
        if want[x["folder"]]["sha256"] != x["sha"]:
            die(f"{x['folder'].name}: messages.md or the CV changed after approval. "
                f"Preview again and get a new green light")
        if not x["items"]:
            die(f"{x['folder'].name}: nothing left to send: everything approved has already gone")
    cap_check(profile, book, sum(len(x["items"]) for x in apps))
    cfg = sender_cfg(profile)

    def record(x, i, mid, last):
        path = x["folder"] / "sent.json"
        entry = {"key": i["key"], "to": i["to"], "at": now().strftime(STAMP), "message_id": mid}
        where = f"{x['folder'].name} {i['key']}: {i['to']}"

        def hooks(stage, error=None):
            if stage == "unsure":  # keep the 'sending' record: it blocks a resend
                die(f"{where}: the connection broke while sending ({error}). The email may have gone. "
                    f"The record says 'sending', which blocks any resend of it. Tell the owner: they "
                    f"check their Sent folder for it (flow/send.md, 'a send … was never confirmed')")
            rows = [r for r in sent_of(x["folder"]) if r.get("message_id") != mid]
            try:
                if stage == "before":  # written first, so a crash can never lead to a second send
                    write_json(path, rows + [dict(entry, state="sending")])
                elif stage == "undo":
                    write_json(path, rows)
                else:
                    write_json(path, rows + [entry])
                    print(f"sent {where}")
                    if last:  # an approval works once
                        (x["folder"] / "approval.json").unlink(missing_ok=True)
            except OSError as e:
                if stage == "before":
                    die(f"cannot write {path} ({e}). Nothing was sent to {i['to']}. Is the folder "
                        f"locked by a sync or antivirus program?")
                die(f"{where}: the email {'WAS SENT' if stage == 'after' else 'was NOT sent'} but {path} "
                    f"could not be updated ({e}). The record still says 'sending', which blocks any "
                    f"resend. Tell the owner")
        return hooks

    msgs = []
    for x in apps:
        cv = x["folder"] / x["meta"]["cv"]
        for n, i in enumerate(x["items"]):
            msg = build(profile, cfg["MAIL_ADDRESS"], i, cv)
            msgs.append((msg, record(x, i, msg["Message-ID"], n == len(x["items"]) - 1)))
    smtp_send(cfg, msgs)
    print(f"done: {len(msgs)} email(s) sent")


class send_lock:
    """One send at a time: a second run started while one is going would send everything twice."""

    def __enter__(self):
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime > 600:
            LOCK.unlink()
        try:
            os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            die("another send is running (outreach/send.lock exists). Wait for it to finish, "
                "then check mail.py status")

    def __exit__(self, *exc):
        LOCK.unlink(missing_ok=True)


def cmd_cancel(a, profile):
    folders = [folder_of(s) for s in a.slugs] or ([p for p in OUT.iterdir() if p.is_dir()] if OUT.is_dir() else [])
    gone = []
    for f in folders:
        if (f / "approval.json").exists():
            (f / "approval.json").unlink()
            gone.append(f.name)
    waiting = PENDING.exists()
    PENDING.unlink(missing_ok=True)
    print(f"cancelled: waiting preview {'withdrawn' if waiting else 'none'}; "
          f"approvals withdrawn for {gone or 'none'}. Nothing was sent")


def cmd_test(a, profile):
    if len(a.slugs) != 1:
        die("test takes one application")
    folder = folder_of(a.slugs[0])
    meta, items = candidates(folder, profile)
    items = [i for i in items if i["first"]]
    if not items:
        die("no email to test: no contact has an address")
    cfg = sender_cfg(profile)
    me = cfg["MAIL_ADDRESS"]
    msgs = [(build(profile, me, i, folder / meta["cv"], to=me, subject=f"[TEST] {i['subject']}",
                   body=f"[TEST: the real recipient would be {i['to']}]\n\n{i['body']}"), lambda stage: None)
            for i in items]
    smtp_send(cfg, msgs)
    print(f"sent {len(msgs)} test email(s) to {me}")


def cmd_status(a, profile):
    for s in a.slugs:
        folder = folder_of(s)
        meta, items = candidates(folder, profile)
        ap = read_json(folder / "approval.json", None, dict)
        if not ap:
            state = "no"
        elif ap.get("sha256") != digest(folder, meta):
            state = "stale (text or CV changed)"
        elif minutes_since(ap.get("at"), folder / "approval.json") > APPROVAL_MINUTES:
            state = f"expired (given {ap['at']})"
        else:
            state = f"yes {ap['at']} for {ap['keys']}"
        print(f"{folder.name}  approved: {state}")
        for i in items:
            print(f"  {i['key']}: {i['to']}  {i['skip'] or 'ready to preview'}")
        if not items:
            print("  no contact has an address (LinkedIn texts only)")


def cmd_check(a, profile):
    if a.only and len(a.slugs) != 1:
        die("--only works with one application at a time")
    apps, book = gather(a.slugs, profile, lambda f, items: choose(items, a.only, f.name),
                        lambda f: a.repeat_ok)
    cap_check(profile, book, sum(len(x["items"]) for x in apps))
    show(apps, profile)
    print("check passed. Nothing was sent, approved or saved. Draft exactly these emails, each with the "
          "attachment shown (a reply goes on the first email's thread); the owner pressing Send is the "
          "green light (flow/send.md § Setup B)")


def cmd_draft(a, profile):
    if a.only and len(a.slugs) != 1:
        die("--only works with one application at a time")
    apps, book = gather(a.slugs, profile, lambda f, items: choose(items, a.only, f.name),
                        lambda f: a.repeat_ok)
    cap_check(profile, book, sum(len(x["items"]) for x in apps))
    cfg = imap_cfg(profile)
    show(apps, profile)
    imap = imap_open(cfg)
    try:
        box = drafts_box(imap)
        there = drafts_there(imap, box)
        saved = kept = 0
        for x in apps:
            cv = x["folder"] / x["meta"]["cv"]
            for i in x["items"]:
                where = f"{x['folder'].name} {i['key']}: {i['to']}"
                if mail_key(i["to"], i["subject"]) in there:
                    print(f"already in Drafts, left alone: {where}")
                    kept += 1
                    continue
                msg = build(profile, cfg["MAIL_ADDRESS"], i, cv)
                ok(imap.append(quoted(box), r"(\Draft \Seen)", imaplib.Time2Internaldate(time.time()),
                               msg.as_bytes()), f"save the draft for {where}")
                wrong = proof(read_back(imap, box, msg["Message-ID"]), i, cv)
                if wrong:
                    die(f"{where}: the draft was saved but {wrong}. Tell the owner: they delete that draft "
                        f"(subject '{i['subject']}') from Drafts before sending anything; then rerun draft")
                att = f", {cv.name} attached and checked byte for byte" if i["attach"] else ""
                print(f"saved draft {where}{att}")
                saved += 1
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    print(f"done: {saved} draft(s) saved, {kept} already there, in {box.strip(chr(34))}. Nothing was sent: "
          f"the owner opens each draft, reads it, and presses Send (flow/send.md § Setup B)")


def cmd_ledger(a, profile):
    rows = ledger()
    for f, r in sorted(rows, key=lambda x: x[1]["at"]):
        how = "  (sent by the owner)" if r.get("outside") else ""
        print(f"{r['at']}  {f.name}  {r['key']}  {r['to']}  {r.get('message_id', '')}{how}")
    print(f"{len(rows)} email(s) sent in total")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "draft", "preview", "approve", "send", "cancel", "test", "status",
                                    "ledger"])
    ap.add_argument("slugs", nargs="*", metavar="slug")
    ap.add_argument("--only", choices=KEYS, help="preview, check, draft: just this email")
    ap.add_argument("--repeat-ok", action="store_true",
                    help="preview, check, draft: allow an address already emailed for another application")
    ap.add_argument("--no-open", action="store_true", help="preview: do not open the browser")
    ap.add_argument("--code", help="approve: the code the owner read on their preview page")
    ap.add_argument("--quote", help="approve: the owner's approving words, verbatim")
    ap.add_argument("--profile")
    a = ap.parse_args()
    if a.cmd in ("check", "draft", "preview", "send", "test", "status") and not a.slugs:
        die(f"{a.cmd} needs at least one application name")
    if a.cmd == "ledger" and a.slugs:
        die("ledger takes no application names")
    if a.cmd not in ("preview", "check", "draft") and (a.only or a.repeat_ok):
        die(f"--only and --repeat-ok belong to preview, check and draft, not {a.cmd}. To send only part of "
            f"what was approved: mail.py cancel, then preview just that part")
    if a.cmd != "preview" and a.no_open:
        die(f"--no-open belongs to preview, not {a.cmd}")
    if a.cmd != "approve" and (a.code or a.quote):
        die(f"--code and --quote belong to approve, not {a.cmd}")
    profile = load_profile(a.profile)
    {"check": cmd_check, "draft": cmd_draft, "preview": cmd_preview, "approve": cmd_approve, "send": cmd_send, "cancel": cmd_cancel, "test": cmd_test,
     "status": cmd_status, "ledger": cmd_ledger}[a.cmd](a, profile)


if __name__ == "__main__":
    run(main)
