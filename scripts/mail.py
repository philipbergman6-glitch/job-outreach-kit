#!/usr/bin/env python3
"""Preview, approve and send the two emails of one application. Stdlib only.

Usage:
  mail.py preview <slug> [--only hm|rec]
        print exactly what would be sent, to whom, and an approval code for that exact text
  mail.py approve <slug> --code <code> --quote "..." [--only hm|rec]
        record the owner's green light: the code from the preview they read, and their own words
  mail.py send <slug> [--only hm|rec]
        send what was approved; refuses when the text or CV changed since the preview,
        when the approval is older than 30 minutes, or when that address was already sent to
  mail.py test <slug>
        send both emails to the owner's own address, subject prefixed [TEST]
  mail.py status <slug>

<slug> = folder name under outreach/ (or a path to an application folder).
hm = hiring manager email (T1), rec = recruiter email (T2).
Add --profile <profile.json> to use a profile other than profile/profile.json.
Reads MAIL_ADDRESS and MAIL_APP_PASSWORD from <repo>/.env (optional SMTP_HOST, SMTP_PORT;
default smtp.gmail.com:465). Hard-fails on anything missing."""
import argparse
import hashlib
import json
import mimetypes
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from _common import ROOT, die, env
from validate import check, load_profile, parse

APPROVAL_MINUTES = 30
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def folder_of(slug):
    p = Path(slug)
    if not p.is_dir():
        p = ROOT / "outreach" / slug
    if not p.is_dir():
        die(f"application folder not found: {slug}")
    if not (p / "messages.md").exists():
        die(f"{p}/messages.md not found")
    return p.resolve()


def load(folder, profile, only=None):
    """Validate, then return (meta, [(key, to, subject, body)]) for contacts that have an address."""
    path = folder / "messages.md"
    violations, _ = check(path, profile)
    if violations:
        die("messages.md fails validation:\n - " + "\n - ".join(violations))
    meta, secs = parse(path)
    mails = []
    for key, sec in (("hm", "T1"), ("rec", "T2")):
        to = meta[f"{key}_email"]
        if to.lower() != "none" and only in (None, key):
            subj, body = secs[sec]
            mails.append((key, to, subj, body))
    if not mails:
        die("no email to handle: the contact has no address (LinkedIn texts only)")
    return meta, mails


def digest(folder, meta):
    h = hashlib.sha256()
    h.update((folder / "messages.md").read_bytes())
    h.update((folder / meta["cv"]).read_bytes())
    return h.hexdigest()


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def now():
    return datetime.now(timezone.utc)


def build(profile, sender, to, subject, body, cv_path):
    msg = EmailMessage()
    msg["From"] = formataddr((profile["name"], sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[1])
    msg.set_content(body + "\n")
    ctype = mimetypes.guess_type(cv_path.name)[0] or "application/octet-stream"
    main_t, sub_t = ctype.split("/", 1)
    msg.add_attachment(cv_path.read_bytes(), maintype=main_t, subtype=sub_t, filename=cv_path.name)
    return msg


def smtp_send(cfg, msgs):
    host = cfg.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(cfg.get("SMTP_PORT") or 465)
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
    except smtplib.SMTPException as e:
        die(f"SMTP error: {e}")
    except OSError as e:
        die(f"cannot reach {host}:{port}: {e}")


def sender_cfg(profile):
    cfg = env("MAIL_ADDRESS", "MAIL_APP_PASSWORD")
    if cfg["MAIL_ADDRESS"].lower() != profile["email"].lower():
        die(f"MAIL_ADDRESS in .env ({cfg['MAIL_ADDRESS']}) differs from profile email ({profile['email']})")
    return cfg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preview", "approve", "send", "test", "status"])
    ap.add_argument("slug")
    ap.add_argument("--only", choices=["hm", "rec"])
    ap.add_argument("--code", help="approve: the approval code printed by the preview the owner read")
    ap.add_argument("--quote", help="approve: the owner's approving words, verbatim")
    ap.add_argument("--profile")
    a = ap.parse_args()

    profile = load_profile(a.profile)
    folder = folder_of(a.slug)
    approval_f, sent_f = folder / "approval.json", folder / "sent.json"
    approval, sent = read_json(approval_f, None), read_json(sent_f, {})
    meta, mails = load(folder, profile, a.only)
    cv = folder / meta["cv"]
    sha = digest(folder, meta)

    def was_sent(key, to):
        return key in sent and sent[key]["to"].lower() == to.lower()

    if a.cmd == "status":
        if not approval:
            state = "no"
        elif approval["sha256"] != sha:
            state = "stale (text or CV changed)"
        else:
            state = f"yes {approval['at']} for {approval['keys']}"
        print(f"approved: {state}")
        for key, to, _, _ in mails:
            print(f"{key}: {to}  {'sent ' + sent[key]['at'] if was_sent(key, to) else 'not sent'}")
        return

    if a.cmd == "preview":
        for key, to, subj, body in mails:
            print("=" * 72)
            print(f"To:         {to}   ({key}, confidence {meta[key + '_email_confidence']})"
                  f"{'   ALREADY SENT ' + sent[key]['at'] if was_sent(key, to) else ''}")
            print(f"From:       {profile['name']} <{profile['email']}>")
            print(f"Subject:    {subj}")
            print(f"Attachment: {cv.name} ({max(1, cv.stat().st_size // 1024)} KB)")
            print("-" * 72)
            print(body)
        print("=" * 72)
        print(f"{len(mails)} email(s). Nothing was sent. Approval code: {sha[:8]}")
        return

    if a.cmd == "approve":
        if not a.quote or not a.quote.strip():
            die("approve needs --quote with the owner's approving words, verbatim")
        if a.code != sha[:8]:
            die("approval code does not match the current text: the file changed since that preview "
                "(or no code was given). Run preview again and show the owner the new output")
        keys = [k for k, _, _, _ in mails]
        approval_f.write_text(json.dumps({
            "sha256": sha, "at": now().strftime(STAMP), "quote": a.quote.strip(), "keys": keys,
            "recipients": [to for _, to, _, _ in mails]}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"approved {keys} for {meta['company']}: {[to for _, to, _, _ in mails]} "
              f"(valid {APPROVAL_MINUTES} minutes)")
        return

    if a.cmd == "test":
        cfg = sender_cfg(profile)
        msgs = [(build(profile, cfg["MAIL_ADDRESS"], cfg["MAIL_ADDRESS"], f"[TEST] {subj}",
                       f"[TEST: real recipient would be {to}]\n\n{body}", cv), lambda: None)
                for _, to, subj, body in mails]
        smtp_send(cfg, msgs)
        print(f"sent {len(msgs)} test email(s) to {cfg['MAIL_ADDRESS']}")
        return

    # send
    if not approval:
        die("not approved: show the owner `mail.py preview`, then record their green light with `mail.py approve`")
    if approval["sha256"] != sha:
        die("messages.md or the CV changed after approval: preview again and get a new green light")
    age = (now() - datetime.strptime(approval["at"], STAMP).replace(tzinfo=timezone.utc)).total_seconds() / 60
    if age > APPROVAL_MINUTES:
        die(f"approval is {int(age)} minutes old (limit {APPROVAL_MINUTES}): preview again and get a new green light")
    todo = [x for x in mails if x[0] in approval["keys"] and not was_sent(x[0], x[1])]
    if not todo:
        die(f"nothing to send: not approved for this contact, or already sent. sent.json: "
            f"{json.dumps(sent, ensure_ascii=False)}")
    cfg = sender_cfg(profile)

    def record(key, to, mid):
        def after():
            sent[key] = {"to": to, "at": now().strftime(STAMP), "message_id": mid}
            sent_f.write_text(json.dumps(sent, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"sent {key}: {to}")
        return after

    msgs = []
    for key, to, subj, body in todo:
        msg = build(profile, cfg["MAIL_ADDRESS"], to, subj, body, cv)
        msgs.append((msg, record(key, to, msg["Message-ID"])))
    smtp_send(cfg, msgs)
    print(f"done: {len(msgs)} email(s) sent for {meta['company']}")


if __name__ == "__main__":
    main()
