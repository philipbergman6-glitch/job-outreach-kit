#!/usr/bin/env python3
"""Validate outreach/<slug>/messages.md against the owner's profile and tone rules.

Usage:
  validate.py <messages.md> [--profile <profile.json>]   exit 0 = pass, 1 = violations
  validate.py --format                                   print the required file format
  validate.py --check-profile [--profile <profile.json>] check the profile alone

Default profile: profile/profile.json. Exit 2 = hard-fail (bad input)."""
import argparse
import json
import re
import sys
from pathlib import Path

from _common import ROOT, die

FORMAT = """---
company: <Company>
role: <Role>
channel: <comeet|greenhouse|lever|other-form|email|applied via ...>
cv: <file name of the snapshot CV in this folder>
hm_name: <First Last>
hm_email: <email or none>
hm_email_confidence: <High|Medium|Low>
rec_name: <First Last>
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
"""

# profile.json "messages" overrides any of these.
DEFAULTS = {
    "language": "English",
    "subject": "{role} application, {name}",
    "greeting": "Hi {first},",
    "closing": "Best regards,",
    "opener_regex": r"\b(applied|submitted (an|my) application)\b",
    "fallback_opener_regex": r"\bI am applying for\b.*\bwith this email\b",
    "attachment_phrases": ["CV attached", "CV is attached", "resume attached", "resume is attached"],
    "banned": ["!", "passionate", "—", "–", "I hope this finds you well"],
    "manager_required_regex": "",
    "recruiter_must_mention": [],
    "word_limits": {"T1": [120, 180], "T2": [120, 180], "T4": [0, 130]},
    "note_char_limit": 200,
}

META_KEYS = ["company", "role", "channel", "cv", "hm_name", "hm_email", "hm_email_confidence",
             "rec_name", "rec_email", "rec_email_confidence", "hook", "hook_rationale"]
PLACEHOLDER = re.compile(r"\{[^}]*\}|<[^>\n]+>|\bTBD\b|\[…\]|\[\.\.\.\]")
HEAD = {"## T1 manager email": "T1", "## T2 recruiter email": "T2",
        "## T3 connection note manager": "T3M", "## T3 connection note recruiter": "T3R",
        "## T4 linkedin message manager": "T4"}
SECTIONS = ["T1", "T2", "T3M", "T3R", "T4"]


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def load_profile(path=None):
    path = Path(path) if path else ROOT / "profile" / "profile.json"
    if not path.exists():
        die(f"{path} missing: run ONBOARDING.md first")
    try:
        p = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: invalid JSON: {e}")
    for k in ("name", "email", "phone", "location", "cvs", "hooks"):
        if not p.get(k):
            die(f"{path}: '{k}' missing or empty")
    left = [s for s in _strings({k: v for k, v in p.items() if k != "messages"})
            if re.search(r"<[^>]+>", s)]
    if left:
        die(f"{path}: unfilled placeholder(s): {left[:3]}")
    if not isinstance(p["hooks"], list) or not all(isinstance(h, str) for h in p["hooks"]):
        die(f"{path}: 'hooks' must be a list of names")
    for cv in p["cvs"]:
        if not isinstance(cv, dict) or not cv.get("file") or not cv.get("use_when"):
            die(f"{path}: each cvs entry needs 'file' and 'use_when'")
        if not (ROOT / cv["file"]).exists():
            die(f"{path}: CV file {cv['file']} not found")
    unknown = set(p.get("messages", {})) - set(DEFAULTS)
    if unknown:
        die(f"{path}: unknown messages keys {sorted(unknown)}; allowed: {sorted(DEFAULTS)}")
    p["messages"] = {**DEFAULTS, **p.get("messages", {})}
    p.setdefault("signature_phone", p["phone"])
    p.setdefault("links", {})
    p.setdefault("current_role_line", "")
    return p


def parse(path):
    path = Path(path)
    if not path.exists():
        die(f"{path} not found")
    txt = path.read_text(encoding="utf-8")
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
        die(f"front matter missing {missing}")
    secs, cur = {}, None
    for line in m.group(2).splitlines():
        if line.strip() in HEAD:
            cur = HEAD[line.strip()]
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
        if s in ("T1", "T2"):
            if not body.startswith("Subject:") or "\n" not in body:
                die(f"{s} must start with a 'Subject:' line followed by the body")
            subj, body = body.split("\n", 1)
            subj = subj[len("Subject:"):].strip()
            body = body.strip()
        out[s] = (subj, body)
    return meta, out


def words(t):
    return len(re.findall(r"\S+", t))


def check(path, profile):
    """Return (violations, stats line). Hard-fails on unparseable input."""
    meta, secs = parse(path)
    m = profile["messages"]
    name = profile["name"]
    first_name = name.split()[0]
    hooks = profile["hooks"]
    role, company, hook = meta["role"], meta["company"], meta["hook"]
    hm_first, rec_first = meta["hm_name"].split()[0], meta["rec_name"].split()[0]
    v = []

    if hook not in hooks:
        v.append(f"hook '{hook}' not one of {hooks}")
    # CV: a profile CV, snapshotted next to messages.md
    cv_names = [Path(c["file"]).name for c in profile["cvs"]]
    if meta["cv"] not in cv_names:
        v.append(f"cv '{meta['cv']}' is not a profile CV {cv_names}")
    if not (Path(path).resolve().parent / meta["cv"]).exists():
        v.append(f"snapshot CV {meta['cv']} missing from the application folder")
    # recipient confidence
    for tag in ("hm", "rec"):
        c = meta[f"{tag}_email_confidence"]
        e = meta[f"{tag}_email"]
        if c not in ("High", "Medium", "Low"):
            v.append(f"{tag}_email_confidence must be High|Medium|Low")
        if c == "Low" and e.lower() != "none":
            v.append(f"{tag}_email is Low confidence; set {tag}_email: none (LinkedIn only)")
        if e.lower() != "none" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            v.append(f"{tag}_email '{e}' is not an address")

    fallback = meta["channel"] == "email"
    subject = m["subject"].format(role=role, name=name, company=company)
    for s in SECTIONS:
        subj, body = secs[s]
        tag = f"[{s}]"
        if PLACEHOLDER.search(body) or (subj and PLACEHOLDER.search(subj)):
            v.append(f"{tag} unresolved placeholder")
        # length
        if s in m["word_limits"]:
            lo, hi = m["word_limits"][s]
            n = words(body)
            if not lo <= n <= hi:
                v.append(f"{tag} {n} words, need {lo}-{hi}")
        if s.startswith("T3") and len(body) > m["note_char_limit"]:
            v.append(f"{tag} {len(body)} chars > {m['note_char_limit']}")
        # greeting
        greet = m["greeting"].format(first=hm_first if s in ("T1", "T3M", "T4") else rec_first)
        if not body.startswith(greet):
            v.append(f"{tag} must open '{greet}'")
        # apply-first opener
        paras = body.split("\n\n")
        if s in ("T1", "T2"):
            first = paras[1] if len(paras) > 1 else body
            rx = m["fallback_opener_regex"] if fallback else m["opener_regex"]
            if not re.search(rx, first, re.I):
                v.append(f"{tag} first paragraph must say the application is in (regex: {rx})")
        elif not re.search(m["fallback_opener_regex"] + "|" + m["opener_regex"], body, re.I):
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
            if meta["rec_name"] in body:
                v.append(f"{tag} manager text names the recruiter")
        if s == "T2":
            for needle in m["recruiter_must_mention"]:
                if needle.lower() not in body.lower():
                    v.append(f"{tag} recruiter email must mention '{needle}'")
            if meta["hm_name"] not in body:
                v.append(f"{tag} other contact '{meta['hm_name']}' not mentioned")
        # banned strings
        for b in m["banned"]:
            if b in body or (subj and b in subj):
                v.append(f"{tag} banned '{b}'")
        # sign-off
        if s in ("T1", "T2"):
            sig = f"{name}\n{profile['signature_phone']}"
            if not body.rstrip().endswith(sig):
                v.append(f"{tag} must end with {sig!r}")
            if m["closing"] not in body:
                v.append(f"{tag} '{m['closing']}' missing")
            if not any(a.lower() in body.lower() for a in m["attachment_phrases"]):
                v.append(f"{tag} must say the CV is attached ({m['attachment_phrases'][0]})")
            for label, url in profile["links"].items():
                if url not in body:
                    v.append(f"{tag} {label} link {url} missing")
            if subj != subject:
                v.append(f"{tag} subject must be '{subject}'")
        if s == "T4" and not body.rstrip().endswith("\n" + first_name):
            v.append(f"{tag} must end with the first name only ('{first_name}')")

    stats = (f"T1={words(secs['T1'][1])}w T2={words(secs['T2'][1])}w "
             f"T3M={len(secs['T3M'][1])}c T3R={len(secs['T3R'][1])}c T4={words(secs['T4'][1])}w")
    return v, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("messages", nargs="?")
    ap.add_argument("--profile")
    ap.add_argument("--format", action="store_true")
    ap.add_argument("--check-profile", action="store_true")
    a = ap.parse_args()
    if a.format:
        print(FORMAT)
        return
    profile = load_profile(a.profile)
    if a.check_profile:
        print(f"PROFILE OK  {profile['name']}  hooks={profile['hooks']}  "
              f"cvs={[c['file'] for c in profile['cvs']]}")
        return
    if not a.messages:
        die("give a messages.md path, or --format, or --check-profile")
    v, stats = check(a.messages, profile)
    if v:
        print("FAIL")
        for x in v:
            print(" -", x)
        sys.exit(1)
    print("PASS ", stats)


if __name__ == "__main__":
    main()
