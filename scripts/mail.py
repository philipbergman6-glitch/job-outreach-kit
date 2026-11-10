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
  mail.py test <slug>       send this application's first emails to the owner's own address, [TEST]
  mail.py status <slug>...  approval state and what was sent
  mail.py ledger            every email sent so far, across all applications

<slug> = folder name under outreach/ (or a path to an application folder).
KEY = hm (T1 to the hiring manager), rec (T2 to the recruiter), hm-nudge (N1), rec-nudge (N2).
Without --only, preview takes every email of the application that is due and unsent.

preview, approve and send all refuse when: messages.md fails validation; an address is on
outreach/do-not-contact.md; the application is not in yet (log.md status started or
handoff-pending); an email says "today" but `applied` is another day; the same address was
already emailed for another application (--repeat-ok at preview lets the owner decide, with
the fact shown on their page); the daily cap (profile max_emails_per_day) would be passed.

Add --profile <profile.json> to use a profile other than profile/profile.json.
Reads MAIL_ADDRESS and MAIL_APP_PASSWORD from <repo>/.env (optional SMTP_HOST, SMTP_PORT;
default smtp.gmail.com:465). Hard-fails on anything missing."""
import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import smtplib
import ssl
import webbrowser
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from _common import ROOT, die, env, run
from tracker import LOG_COLS, read_table
from validate import check, is_none, load_profile, parse

APPROVAL_MINUTES = 30
NUDGE_AFTER_DAYS = 5
CODE_TRIES = 3
STAMP = "%Y-%m-%dT%H:%M:%SZ"
OUT = ROOT / "outreach"
PENDING = OUT / "pending.json"
PAGE = OUT / "preview.html"
FIRST = (("hm", "T1", "N1"), ("rec", "T2", "N2"))
KEYS = ["hm", "rec", "hm-nudge", "rec-nudge"]


# ---------- state files ----------

def now():
    return datetime.now(timezone.utc)


def stamp(text, where):
    try:
        return datetime.strptime(text, STAMP).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        die(f"{where}: bad timestamp {text!r}. Repair the file by hand with the owner; keep it")


def minutes_since(text, where):
    return (now() - stamp(text, where)).total_seconds() / 60


def read_json(path, default, kind):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"{path} is damaged ({e}). It is part of the record that prevents double sends: "
            f"repair it by hand with the owner; keep the file")
    if not isinstance(data, kind):
        die(f"{path} is damaged (wrong shape). Repair it by hand with the owner; keep the file")
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
    return p.resolve()


def sent_of(folder):
    path = folder / "sent.json"
    rows = read_json(path, [], list)
    for r in rows:
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) for k in ("key", "to", "at")):
            die(f"{path}: malformed entry {r!r}. Repair it by hand with the owner; keep the file")
        stamp(r["at"], path)
    return rows


def ledger(extra=()):
    """[(folder, sent entry)] across every application folder."""
    folders = sorted(p.resolve() for p in OUT.iterdir() if p.is_dir()) if OUT.is_dir() else []
    folders += [f for f in extra if f not in folders]
    return [(f, r) for f in folders for r in sent_of(f)]


def blocked():
    p = OUT / "do-not-contact.md"
    out = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            tok = line.strip().lstrip("-* ").strip("`").split()
            if tok and "@" in tok[0] and not line.strip().startswith("#"):
                out.add(tok[0].strip("`").lower())
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

    def last(key, to):
        hits = [r for r in sent if r["key"] == key and r["to"].lower() == to.lower()]
        return hits[-1] if hits else None

    items = []
    for key, sec, nsec in FIRST:
        to = meta[f"{key}_email"]
        if is_none(to):
            continue
        subj, body = secs[sec]
        base = dict(to=to, name=meta[f"{key}_name"], conf=meta[f"{key}_email_confidence"])
        done = last(key, to)
        items.append(dict(base, key=key, subject=subj, body=body, attach=True, reply_to=None,
                          skip=f"already sent {done['at']}" if done else None))
        if nsec in secs and not is_none(secs[nsec][1]):
            ndone = last(key + "-nudge", to)
            if ndone:
                why = f"already sent {ndone['at']}"
            elif not done:
                why = "the first email to this address has not been sent"
            elif now() - stamp(done["at"], folder / "sent.json") < timedelta(days=NUDGE_AFTER_DAYS):
                why = f"the first email went {done['at']}; a nudge waits {NUDGE_AFTER_DAYS} days"
            elif not done.get("message_id"):
                why = "the first email has no recorded message id to reply to"
            else:
                why = None
            items.append(dict(base, key=key + "-nudge", subject="Re: " + subj, body=secs[nsec][1],
                              attach=False, reply_to=done.get("message_id") if done else None, skip=why))
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
    firsts = [i for i in items if i["attach"]]
    if not firsts:
        return
    if folder.parent == OUT and meta["channel"] != "email":
        rows = [r for r in read_table(OUT / "log.md", LOG_COLS)
                if r["Folder"].strip("`/ ").split("/")[-1] == folder.name]
        if not rows:
            die(f"{folder.name}: no row with this Folder in outreach/log.md (flow/apply.md step 0)")
        if rows[-1]["Status"] in ("started", "handoff-pending"):
            die(f"{folder.name}: log.md says the application is '{rows[-1]['Status']}'. "
                f"Emails go out only once the application is in")
    if meta["channel"] != "email" and date.fromisoformat(meta["applied"]) != date.today():
        for i in firsts:
            for w in profile["messages"]["today_words"]:
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
        meta, items = candidates(f, profile)
        items = pick(f, items)
        guard(f, meta, items, profile, repeat_ok(f), book, bl)
        for i in items:
            other = seen.setdefault(i["to"].lower(), f.name)
            if other != f.name:
                die(f"{i['to']} would get an email from both {other} and {f.name}: one person gets "
                    f"one email. Set that address to none in one of them")
        apps.append(dict(folder=f, meta=meta, items=items, sha=digest(f, meta)))
    return apps, book


def cap_check(profile, book, n):
    today = now().strftime("%Y-%m-%d")
    done = sum(r["at"].startswith(today) for _, r in book)
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
            for msg, after in msgs:
                server.send_message(msg)
                after()
    except smtplib.SMTPAuthenticationError as e:
        die(f"the mail server refused the login ({e.smtp_code}). Check MAIL_ADDRESS and the app "
            f"password in .env (flow/send.md § Setup)")
    except smtplib.SMTPException as e:
        die(f"SMTP error: {e}")
    except OSError as e:
        die(f"cannot reach {host}:{port}: {e}")


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
            print(f"Attachment: {cv.name + f' ({max(1, cv.stat().st_size // 1024)} KB)' if i['attach'] else 'none (reply on the first email)'}")
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
            att = e(cv.name) if i["attach"] else "none (sent as a reply on your first email)"
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
    want = {}
    for s in a.slugs:
        f = folder_of(s)
        ap = read_json(f / "approval.json", None, dict)
        if not ap:
            die(f"{f.name}: not approved. Run preview, the owner reads their page and gives you its "
                f"code, then approve")
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
        def after():
            path = x["folder"] / "sent.json"
            write_json(path, sent_of(x["folder"]) + [
                {"key": i["key"], "to": i["to"], "at": now().strftime(STAMP), "message_id": mid}])
            print(f"sent {x['folder'].name} {i['key']}: {i['to']}")
            if last:  # an approval works once
                (x["folder"] / "approval.json").unlink()
        return after

    msgs = []
    for x in apps:
        cv = x["folder"] / x["meta"]["cv"]
        for n, i in enumerate(x["items"]):
            msg = build(profile, cfg["MAIL_ADDRESS"], i, cv)
            msgs.append((msg, record(x, i, msg["Message-ID"], n == len(x["items"]) - 1)))
    smtp_send(cfg, msgs)
    print(f"done: {len(msgs)} email(s) sent")


def cmd_test(a, profile):
    if len(a.slugs) != 1:
        die("test takes one application")
    folder = folder_of(a.slugs[0])
    meta, items = candidates(folder, profile)
    items = [i for i in items if i["attach"]]
    if not items:
        die("no email to test: no contact has an address")
    cfg = sender_cfg(profile)
    me = cfg["MAIL_ADDRESS"]
    msgs = [(build(profile, me, i, folder / meta["cv"], to=me, subject=f"[TEST] {i['subject']}",
                   body=f"[TEST: the real recipient would be {i['to']}]\n\n{i['body']}"), lambda: None)
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


def cmd_ledger(a, profile):
    rows = ledger()
    for f, r in sorted(rows, key=lambda x: x[1]["at"]):
        print(f"{r['at']}  {f.name}  {r['key']}  {r['to']}  {r.get('message_id', '')}")
    print(f"{len(rows)} email(s) sent in total")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preview", "approve", "send", "test", "status", "ledger"])
    ap.add_argument("slugs", nargs="*", metavar="slug")
    ap.add_argument("--only", choices=KEYS, help="preview: just this email")
    ap.add_argument("--repeat-ok", action="store_true",
                    help="preview: allow an address already emailed for another application")
    ap.add_argument("--no-open", action="store_true", help="preview: do not open the browser")
    ap.add_argument("--code", help="approve: the code the owner read on their preview page")
    ap.add_argument("--quote", help="approve: the owner's approving words, verbatim")
    ap.add_argument("--profile")
    a = ap.parse_args()
    if a.cmd in ("preview", "send", "test", "status") and not a.slugs:
        die(f"{a.cmd} needs at least one application name")
    if a.cmd == "ledger" and a.slugs:
        die("ledger takes no application names")
    profile = load_profile(a.profile)
    {"preview": cmd_preview, "approve": cmd_approve, "send": cmd_send, "test": cmd_test,
     "status": cmd_status, "ledger": cmd_ledger}[a.cmd](a, profile)


if __name__ == "__main__":
    run(main)
