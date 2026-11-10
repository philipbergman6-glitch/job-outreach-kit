#!/usr/bin/env python3
"""Validate outreach/<slug>/messages.md against the owner's profile and tone rules.

Usage:
  validate.py <messages.md> [--profile <profile.json>]   exit 0 = pass, 1 = violations
  validate.py --format                                   print the required file format
  validate.py --check-profile [--profile <profile.json>] check the profile alone
  validate.py --defaults                                 print the default message rules

profile.json "messages" overrides the defaults key by key, except that "banned" and
"attachment_phrases" are added to the defaults and "word_limits" is merged per text.

Default profile: profile/profile.json. Exit 2 = hard-fail (bad input)."""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from _common import ROOT, die, run

FORMAT = """---
company: <Company>
role: <Role>
channel: <comeet|greenhouse|lever|other-form|email|applied via ...>
applied: <YYYY-MM-DD, the day the application went in>
cv: <file name of the snapshot CV in this folder>
hm_name: <First Last, or none>
hm_email: <email or none>
hm_email_confidence: <High|Medium|Low>
rec_name: <First Last, or Hiring Team for a published jobs@ address, or none>
rec_email: <email or none>
rec_email_confidence: <High|Medium|Low>
hook: <one hook name from profile.json>
hook_rationale: <one line: why this hook matches the JD>
---

## T1 manager email
Subject: <subject from profile.json>

<body>

## T2 recruiter email
Subject: <subject from profile.json>

<body>

## T3 connection note manager

<text>

## T3 connection note recruiter

<text>

## T4 linkedin message manager

<text>

A contact whose name is `none` has the single word `none` as the body of each of their
sections. Optional, added later for a follow-up (no Subject line; it goes out as a reply
on the first email's thread):

## N1 nudge manager

<text>

## N2 nudge recruiter

<text>
"""

# profile.json "messages" overrides these (lists in ADDITIVE are extended, word_limits merged).
DEFAULTS = {
    "language": "English",
    "subject": "{role} application, {name}",
    "greeting": "Hi {first},",
    "closing": "Best regards,",
    "opener_regex": r"\b(applied|submitted (an|my) application)\b",
    "fallback_opener_regex": r"\bI am applying for\b.*\bwith this email\b",
    "attachment_phrases": ["CV attached", "CV is attached", "resume attached", "resume is attached"],
    "banned": ["!", "passionate", "—", "–", "I hope this finds you well"],
    "today_words": ["today"],
    "manager_required_regex": "",
    "recruiter_must_mention": [],
    "word_limits": {"T1": [120, 180], "T2": [120, 180], "T4": [0, 130], "N1": [15, 90], "N2": [15, 90]},
    "note_char_limit": 200,
}

ADDITIVE = ("banned", "attachment_phrases")
REGEX_KEYS = ("opener_regex", "fallback_opener_regex", "manager_required_regex")
STR_KEYS = ("language", "subject", "greeting", "closing") + REGEX_KEYS
LIST_KEYS = ("attachment_phrases", "banned", "today_words", "recruiter_must_mention")

META_KEYS = ["company", "role", "channel", "applied", "cv", "hm_name", "hm_email",
             "hm_email_confidence", "rec_name", "rec_email", "rec_email_confidence",
             "hook", "hook_rationale"]
PLACEHOLDER = re.compile(r"\{[^}\n]*\}|<[^>\n]+>|\[[^\]\n]*\]|\bTBD\b|\bX{2,}\b|lorem ipsum", re.I)
ADDRESS = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
HEAD = {"## T1 manager email": "T1", "## T2 recruiter email": "T2",
        "## T3 connection note manager": "T3M", "## T3 connection note recruiter": "T3R",
        "## T4 linkedin message manager": "T4",
        "## N1 nudge manager": "N1", "## N2 nudge recruiter": "N2"}
SECTIONS = ["T1", "T2", "T3M", "T3R", "T4"]
OPTIONAL = ["N1", "N2"]
SIDE = {"T1": "hm", "T3M": "hm", "T4": "hm", "N1": "hm", "T2": "rec", "T3R": "rec", "N2": "rec"}
EMAILS = ("T1", "T2", "N1", "N2")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _check_messages(path, m):
    """Hard-fail on any messages setting that would crash or silently weaken check()."""
    for k in STR_KEYS:
        if not isinstance(m[k], str):
            die(f"{path}: messages.{k} must be text")
    for k in LIST_KEYS:
        if not isinstance(m[k], list) or not all(isinstance(x, str) and x for x in m[k]):
            die(f"{path}: messages.{k} must be a list of non-empty texts")
    for k, sample in (("subject", {"role": "r", "name": "n", "company": "c"}), ("greeting", {"first": "f"})):
        try:
            m[k].format(**sample)
        except (KeyError, IndexError, ValueError):
            die(f"{path}: messages.{k} '{m[k]}' may only use the placeholders "
                f"{', '.join('{' + x + '}' for x in sample)}")
    for k in REGEX_KEYS:
        try:
            re.compile(m[k])
        except re.error as e:
            die(f"{path}: messages.{k} is not a valid regular expression: {e}")
    for k in ("subject", "greeting", "closing", "opener_regex", "fallback_opener_regex"):
        if not m[k].strip():
            die(f"{path}: messages.{k} is empty")
    wl = m["word_limits"]
    for k, pair in wl.items():
        if k not in DEFAULTS["word_limits"]:
            die(f"{path}: messages.word_limits has unknown text '{k}'; allowed {sorted(DEFAULTS['word_limits'])}")
        if (not isinstance(pair, list) or len(pair) != 2
                or not all(isinstance(n, int) and not isinstance(n, bool) for n in pair)
                or not 0 <= pair[0] <= pair[1]):
            die(f"{path}: messages.word_limits.{k} must be [min, max] as two whole numbers, e.g. [120, 180]")
    n = m["note_char_limit"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        die(f"{path}: messages.note_char_limit must be a whole number")


def load_profile(path=None):
    path = Path(path) if path else ROOT / "profile" / "profile.json"
    if not path.exists():
        die(f"{path} missing: run ONBOARDING.md first")
    try:
        p = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        die(f"{path}: invalid JSON: {e}")
    if not isinstance(p, dict):
        die(f"{path}: must be a JSON object")
    for k in ("name", "email", "phone", "location"):
        if not isinstance(p.get(k), str) or not p[k].strip():
            die(f"{path}: '{k}' missing or empty")
    for k in ("cvs", "hooks"):
        if not isinstance(p.get(k), list) or not p[k]:
            die(f"{path}: '{k}' must be a non-empty list")
    own = p.get("messages", {})
    if not isinstance(own, dict):
        die(f"{path}: 'messages' must be an object of settings")
    scan = {k: v for k, v in p.items() if k != "messages"}
    scan["messages"] = {k: v for k, v in own.items() if k not in REGEX_KEYS}
    left = [s for s in _strings(scan) if re.search(r"<[^>]+>", s)]
    if left:
        die(f"{path}: unfilled placeholder(s): {left[:3]}")
    if not ADDRESS.fullmatch(p["email"].strip()):
        die(f"{path}: email '{p['email']}' is not an address")
    if not all(isinstance(h, str) and h.strip() for h in p["hooks"]):
        die(f"{path}: 'hooks' must be a list of names")
    for cv in p["cvs"]:
        if not isinstance(cv, dict) or not cv.get("file") or not cv.get("use_when"):
            die(f"{path}: each cvs entry needs 'file' and 'use_when'")
        if not (ROOT / cv["file"]).is_file():
            die(f"{path}: CV file {cv['file']} not found")
    links = p.setdefault("links", {})
    if not isinstance(links, dict) or not all(isinstance(u, str) and u.strip() for u in links.values()):
        die(f"{path}: 'links' must map a label to a non-empty link; remove unused labels")
    unknown = set(own) - set(DEFAULTS)
    if unknown:
        die(f"{path}: unknown messages keys {sorted(unknown)}; allowed: {sorted(DEFAULTS)}")
    merged = {**DEFAULTS, **own}
    for k in ADDITIVE:
        extra = own.get(k, [])
        if not isinstance(extra, list):
            die(f"{path}: messages.{k} must be a list")
        merged[k] = DEFAULTS[k] + [x for x in extra if x not in DEFAULTS[k]]
    if not isinstance(own.get("word_limits", {}), dict):
        die(f"{path}: messages.word_limits must be an object like {{\"T1\": [120, 180]}}")
    merged["word_limits"] = {**DEFAULTS["word_limits"], **own.get("word_limits", {})}
    _check_messages(path, merged)
    p["messages"] = merged
    for k, default in (("signature_phone", p["phone"]), ("signature_name", p["name"]),
                       ("current_role_line", "")):
        p.setdefault(k, default)
        if not isinstance(p[k], str):
            die(f"{path}: '{k}' must be text")
    for k in ("signature_name", "signature_phone"):
        if not p[k].strip():
            die(f"{path}: '{k}' is empty")
    cap = p.setdefault("max_emails_per_day", 20)
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        die(f"{path}: 'max_emails_per_day' must be a whole number, 1 or more")
    return p


def parse(path):
    path = Path(path)
    if not path.is_file():
        die(f"{path} not found")
    txt = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    m = re.match(r"---\n(.*?)\n---\n(.*)", txt, re.S)
    if not m:
        die("no front matter; run validate.py --format")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    missing = [k for k in META_KEYS if not meta.get(k)]
    if missing:
        die(f"front matter missing {missing}; run validate.py --format")
    secs, cur = {}, None
    for line in m.group(2).splitlines():
        if line.strip() in HEAD:
            cur = HEAD[line.strip()]
            if cur in secs:
                die(f"section {cur} appears twice")
            secs[cur] = []
        elif cur:
            secs[cur].append(line)
    missing = [s for s in SECTIONS if s not in secs]
    if missing:
        die(f"missing sections {missing}; run validate.py --format")
    out = {}
    for s, lines in secs.items():
        body = "\n".join(lines).strip()
        subj = None
        if not body:
            die(f"section {s} is empty (write the text, or the single word none)")
        if s in ("T1", "T2") and body.lower() != "none":
            if not body.startswith("Subject:") or "\n" not in body:
                die(f"{s} must start with a 'Subject:' line followed by the body")
            subj, body = body.split("\n", 1)
            subj = subj[len("Subject:"):].strip()
            body = body.strip()
        out[s] = (subj, body)
    return meta, out


def words(t):
    return len(re.findall(r"\S+", t))


def is_none(x):
    return x.strip().lower() == "none"


def greet_name(full):
    """First name, or the whole thing for a group such as 'Hiring Team'."""
    return full if full.lower().endswith(" team") else full.split()[0]


def check(path, profile):
    """Return (violations, stats line). Hard-fails on unparseable input."""
    meta, secs = parse(path)
    m = profile["messages"]
    name = profile["signature_name"]
    first_name = name.split()[0]
    hooks = profile["hooks"]
    role, company, hook = meta["role"], meta["company"], meta["hook"]
    absent = {t: is_none(meta[f"{t}_name"]) for t in ("hm", "rec")}
    group = {t: meta[f"{t}_name"].lower().endswith(" team") for t in ("hm", "rec")}
    v = []

    if all(absent.values()):
        v.append("both contacts are none: there is nobody to write to")
    if hook not in hooks:
        v.append(f"hook '{hook}' not one of {hooks}")
    try:
        if date.fromisoformat(meta["applied"]) > date.today():
            v.append(f"applied '{meta['applied']}' is in the future")
    except ValueError:
        v.append(f"applied '{meta['applied']}' must be the date the application went in, as YYYY-MM-DD")
    # CV: a profile CV, snapshotted next to messages.md
    cv_names = [Path(c["file"]).name for c in profile["cvs"]]
    if meta["cv"] not in cv_names:
        v.append(f"cv '{meta['cv']}' is not a profile CV {cv_names}")
    if not (Path(path).resolve().parent / meta["cv"]).is_file():
        v.append(f"snapshot CV {meta['cv']} missing from the application folder")
    # recipients
    for tag in ("hm", "rec"):
        c = meta[f"{tag}_email_confidence"]
        e = meta[f"{tag}_email"]
        if c not in ("High", "Medium", "Low"):
            v.append(f"{tag}_email_confidence must be High|Medium|Low")
        if absent[tag] and not is_none(e):
            v.append(f"{tag}_name is none, so {tag}_email must be none")
        if c == "Low" and not is_none(e):
            v.append(f"{tag}_email is Low confidence; set {tag}_email: none (LinkedIn only)")
        if not is_none(e) and not ADDRESS.fullmatch(e):
            v.append(f"{tag}_email '{e}' is not an address")
    if not is_none(meta["hm_email"]) and meta["hm_email"].lower() == meta["rec_email"].lower():
        v.append("hm_email and rec_email are the same address: one person gets one email; "
                 "set one of them to none")

    fallback = meta["channel"] == "email"
    subject = m["subject"].format(role=role, name=name, company=company)
    for s in SECTIONS + [o for o in OPTIONAL if o in secs]:
        subj, body = secs[s]
        tag, side = f"[{s}]", SIDE[s]
        if absent[side]:
            if not is_none(body):
                v.append(f"{tag} {side}_name is none: this section must be the single word 'none'")
            continue
        if is_none(body):
            linkedin_text_for_group = group[side] and s in ("T3M", "T3R", "T4")
            unsendable_email = s in ("T1", "T2") and is_none(meta[f"{side}_email"])
            if s not in OPTIONAL and not linkedin_text_for_group and not unsendable_email:
                v.append(f"{tag} is 'none' but {side}_name is set: write the text")
            continue
        if PLACEHOLDER.search(body) or (subj and PLACEHOLDER.search(subj)):
            v.append(f"{tag} unresolved placeholder or bracketed note")
        # length
        if s in m["word_limits"]:
            lo, hi = m["word_limits"][s]
            n = words(body)
            if not lo <= n <= hi:
                v.append(f"{tag} {n} words, need {lo}-{hi}")
        if s.startswith("T3") and len(body) > m["note_char_limit"]:
            v.append(f"{tag} {len(body)} chars > {m['note_char_limit']}")
        # greeting
        greet = m["greeting"].format(first=greet_name(meta[f"{side}_name"]))
        if not body.startswith(greet):
            v.append(f"{tag} must open '{greet}'")
        # apply-first opener
        paras = body.split("\n\n")
        if s in ("T1", "T2"):
            first = paras[1] if len(paras) > 1 else body
            rx = m["fallback_opener_regex"] if fallback else m["opener_regex"]
            if not re.search(rx, first, re.I):
                v.append(f"{tag} first paragraph must say the application is in (regex: {rx})")
        elif s not in OPTIONAL and not (re.search(m["fallback_opener_regex"], body, re.I)
                                        or re.search(m["opener_regex"], body, re.I)):
            v.append(f"{tag} must say the application is in")
        if role not in body:
            v.append(f"{tag} role '{role}' not named")
        if s.startswith("T3") and company not in body:
            v.append(f"{tag} company name missing")
        # one hook
        named = [h for h in hooks if h in body]
        if s in ("T1", "T4", "T3M") and named not in ([hook], []):
            v.append(f"{tag} names {named}; manager texts name only the hook '{hook}'")
        if s in ("T1", "T4") and hook not in body:
            v.append(f"{tag} hook '{hook}' absent")
        if s == "T2" and (len(named) > 2 or hook not in named):
            v.append(f"{tag} names {named}; need the hook plus at most one more")
        # current role line, exactly once
        line = profile["current_role_line"]
        if line and s in ("T1", "T2") and body.count(line) != 1:
            v.append(f"{tag} current role line must appear exactly once: '{line}'")
        # manager vs recruiter content
        if s in ("T1", "T4"):
            if m["manager_required_regex"] and not re.search(m["manager_required_regex"], body, re.I):
                v.append(f"{tag} manager text must match /{m['manager_required_regex']}/")
            if not absent["rec"] and not group["rec"] and meta["rec_name"] in body:
                v.append(f"{tag} manager text names the recruiter")
        if s == "T2":
            for needle in m["recruiter_must_mention"]:
                if needle.lower() not in body.lower():
                    v.append(f"{tag} recruiter email must mention '{needle}'")
            if not is_none(meta["hm_email"]) and meta["hm_name"] not in body:
                v.append(f"{tag} other contact '{meta['hm_name']}' not mentioned")
        # banned strings, any letter case
        for b in m["banned"]:
            if b.lower() in body.lower() or (subj and b.lower() in subj.lower()):
                v.append(f"{tag} banned '{b}'")
        # sign-off
        if s in EMAILS:
            sig = f"{name}\n{profile['signature_phone']}"
            if not body.rstrip().endswith(sig):
                v.append(f"{tag} must end with {sig!r}")
            if m["closing"] not in body:
                v.append(f"{tag} '{m['closing']}' missing")
        if s in ("T1", "T2"):
            if not any(a.lower() in body.lower() for a in m["attachment_phrases"]):
                v.append(f"{tag} must say the CV is attached ({m['attachment_phrases'][0]})")
            for label, url in profile["links"].items():
                if url not in body:
                    v.append(f"{tag} {label} link {url} missing")
            if subj != subject:
                v.append(f"{tag} subject must be '{subject}'")
        if s == "T4" and not body.rstrip().endswith("\n" + first_name):
            v.append(f"{tag} must end with the first name only ('{first_name}')")

    def size(s):
        body = secs[s][1]
        if is_none(body):
            return "none"
        return f"{len(body)}c" if s.startswith("T3") else f"{words(body)}w"

    stats = " ".join(f"{s}={size(s)}" for s in SECTIONS + [o for o in OPTIONAL if o in secs])
    return v, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("messages", nargs="?")
    ap.add_argument("--profile")
    ap.add_argument("--format", action="store_true")
    ap.add_argument("--check-profile", action="store_true")
    ap.add_argument("--defaults", action="store_true")
    a = ap.parse_args()
    if a.defaults:
        print(json.dumps(DEFAULTS, indent=2, ensure_ascii=False))
        return
    if a.format:
        print(FORMAT)
        return
    profile = load_profile(a.profile)
    if a.check_profile:
        print(f"PROFILE OK  {profile['name']}  hooks={profile['hooks']}  "
              f"cvs={[c['file'] for c in profile['cvs']]}")
        return
    if not a.messages:
        die("give a messages.md path, or --format, --defaults, or --check-profile")
    v, stats = check(a.messages, profile)
    if v:
        print("FAIL")
        for x in v:
            print(" -", x)
        sys.exit(1)
    print("PASS ", stats)


if __name__ == "__main__":
    run(main)
