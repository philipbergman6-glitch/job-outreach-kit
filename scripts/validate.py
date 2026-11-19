#!/usr/bin/env python3
"""Validate outreach/<slug>/messages.md against the owner's profile and tone rules.

Usage:
  validate.py <messages.md> [--profile <profile.json>]   exit 0 = pass, 1 = violations
  validate.py --format                                   print the required file format
  validate.py --check-profile [--profile <profile.json>] check the profile alone
  validate.py --defaults                                 print the default message rules
  validate.py --answers <answers.md> [--profile ...]     check drafted form answers (format below)

Fact check, narrow on purpose: a figure in the texts or in a tailored CV's text (cv-<slug>.txt)
must appear in a profile CV's text (<cv>.txt beside the PDF), in brief.md beside profile.json,
or (texts only) in the application's jd.md; years, dates, times, links, the phone and
spelled-out numbers pass. And the owner's own verb (first on a line, or after "I") may not
claim a higher scope (helped < built < led) than the CV or brief line it matches.

Form answers (outreach/<slug>/answers.md drafts; profile/answers.md the bank of approved ones):
  ## <the question, exactly as the form asks it>
  Approved: no                      or a date once the owner approves: 2026-11-19 (<company>)
  Limit: 500                        optional: the form's character limit
  <the answer>
Each answer gets the same fact check (plus jd.md and offer.md beside it), no placeholders, and
fits its limit; the bank holds approved answers only. A negotiation.md (flow/offer.md) uses the
same format, one "## <point>" per ask.

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
cv_from: <optional: the profile CV that cv was tailored from for this job; needs cv-tailoring.md here>
hm_name: <First Last, or none>
hm_email: <email or none>
hm_email_confidence: <High|Medium|Low>
rec_name: <First Last, or Hiring Team for a published jobs@ address, or none>
rec_email: <email or none>
rec_email_confidence: <High|Medium|Low>
hook: <one hook name from profile.json>
hook_rationale: <one line: why this hook matches the JD>
language: <optional: a language set up in profile.json "languages"; omit for the main one>
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

Optional, only when the owner knows someone at the company (they send it themselves):

## R1 referral ask

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
        "## N1 nudge manager": "N1", "## N2 nudge recruiter": "N2",
        "## R1 referral ask": "R1"}  # R1 is sent by the owner personally: parsed, never checked or mailed
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


LANG_ONLY = ("signature_name", "hook_names")  # per-language extras that are not message rules


def _placeholders(node):
    """Template placeholders like <...> left unfilled; regular expressions are exempt."""
    if isinstance(node, dict):
        return [x for k, v in node.items() if k not in REGEX_KEYS for x in _placeholders(v)]
    if isinstance(node, list):
        return [x for v in node for x in _placeholders(v)]
    return [node] if isinstance(node, str) and re.search(r"<[^>]+>", node) else []


def _merge(path, base, own, where):
    """base settings + own overrides: lists in ADDITIVE extend, word_limits merge per text."""
    merged = {**base, **own}
    for k in ADDITIVE:
        extra = own.get(k, [])
        if not isinstance(extra, list):
            die(f"{path}: {where}.{k} must be a list")
        merged[k] = base[k] + [x for x in extra if x not in base[k]]
    if not isinstance(own.get("word_limits", {}), dict):
        die(f"{path}: {where}.word_limits must be an object like {{\"T1\": [120, 180]}}")
    merged["word_limits"] = {**base["word_limits"], **own.get("word_limits", {})}
    _check_messages(path, merged)
    return merged


def messages_for(profile, meta):
    """The message rules for this messages.md: its `language:` (optional) picks a set from
    profile.json "languages"; absent, the main "messages" set applies."""
    lang = meta.get("language", "").strip()
    if not lang or lang == profile["messages"]["language"]:
        return profile["messages"]
    if lang not in profile["_by_language"]:
        die(f"messages.md says language: {lang}, but profile.json has no languages.{lang} settings "
            f"(languages set up: {sorted(profile['_by_language']) or 'none'})")
    return profile["_by_language"][lang]


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
    scan = {k: v for k, v in p.items() if k not in ("messages", "languages")}
    scan["messages"] = own
    left = _placeholders(scan)
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
        if not cv["file"].lower().endswith(".pdf"):
            die(f"{path}: CV {cv['file']} must be a PDF: application forms and recruiters expect one. "
                f"Word: File > Save As > PDF. Google Docs: File > Download > PDF. Keep the original next to it")
        txt = (ROOT / cv["file"]).with_suffix(".txt")
        if not txt.is_file() or not txt.read_text(encoding="utf-8-sig").strip():
            die(f"{path}: CV text {Path(cv['file']).with_suffix('.txt')} missing or empty: read {cv['file']} fully "
                f"and save its text there, line by line (ONBOARDING.md step 2); the fact check reads it")
    links = p.setdefault("links", {})
    if not isinstance(links, dict) or not all(isinstance(u, str) and u.strip() for u in links.values()):
        die(f"{path}: 'links' must map a label to a non-empty link; remove unused labels")
    unknown = set(own) - set(DEFAULTS)
    if unknown:
        die(f"{path}: unknown messages keys {sorted(unknown)}; allowed: {sorted(DEFAULTS)}")
    merged = _merge(path, DEFAULTS, own, "messages")
    p["messages"] = merged
    langs = p.setdefault("languages", {})
    if not isinstance(langs, dict):
        die(f"{path}: 'languages' must map a language name to its message settings")
    p["_by_language"] = {}
    for lang, over in langs.items():
        if not isinstance(over, dict):
            die(f"{path}: languages.{lang} must be an object of message settings")
        bad = set(over) - set(DEFAULTS) - set(LANG_ONLY)
        if bad:
            die(f"{path}: unknown languages.{lang} keys {sorted(bad)}; allowed: {sorted(set(DEFAULTS) | set(LANG_ONLY))}")
        left = _placeholders({"languages": {lang: over}})
        if left:
            die(f"{path}: unfilled placeholder(s) in languages.{lang}: {left[:3]}")
        sig = over.get("signature_name", "")
        names = over.get("hook_names", {})
        if not isinstance(sig, str):
            die(f"{path}: languages.{lang}.signature_name must be text")
        if not isinstance(names, dict) or not all(isinstance(v, str) and v.strip() for v in names.values()):
            die(f"{path}: languages.{lang}.hook_names must map each hook to its name in {lang}")
        unknown_hooks = set(names) - set(p["hooks"])
        if unknown_hooks:
            die(f"{path}: languages.{lang}.hook_names has {sorted(unknown_hooks)}, which are not in 'hooks'")
        rules = {k: v for k, v in over.items() if k not in LANG_ONLY}
        m = _merge(path, merged, {**rules, "language": lang}, f"languages.{lang}")
        m["_signature_name"], m["_hook_names"] = sig.strip(), names
        p["_by_language"][lang] = m
    from accounts import check_accounts
    check_accounts(path, p)
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
    p["_path"], p["_brief"] = path, path.parent / "brief.md"
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


# ---------- fact check: numbers and scope verbs must trace to the CV text or brief.md ----------
# Scope tiers after career-ops verify-cv-facts.mjs (MIT, THIRD_PARTY_NOTICES.md): 1 took part,
# 2 did the work, 3 owned the mandate. A claim may not sit on a higher tier than its source line.
SCOPE = {w: 1 for w in "contribute contributed contributes contributing help helped helps helping "
         "support supported supports supporting assist assisted assisting".split()}
SCOPE.update({w: 2 for w in "build built builds building implement implemented implements implementing "
              "design designed designs designing create created creates creating".split()})
SCOPE.update({w: 3 for w in "lead led leads leading own owned owns owning architect architected architects "
              "architecting drive drove drives driving head headed heads heading".split()})
STOP = set("about after also been before being between both could each from have here into just like more most "
           "much only other over same some such than that their them then there these they this those through "
           "under very want were what when where which while will with would your ours mine".split())
NUMBER = re.compile(r"(?<![A-Za-z\d.,])\d[\d,]*(?:\.\d+)?(?:[kKmMxX]|bn)?(?![A-Za-z\d])")
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
NOT_CLAIMS = re.compile(r"\S*(?:https?://|www\.|\.com/|\.co/|linkedin\.com)\S*|\S+@\S+|\b\d{4}-\d{2}-\d{2}\b|"
                        r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + MONTH + r"|\b" + MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?\b|"
                        r"\b\d{1,2}:\d{2}\b", re.I)
SPELLED = {w: str(n) for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                           "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
SPELLED.update({"thirty": "30", "forty": "40", "fifty": "50", "hundred": "100", "half": "50", "fifth": "5"})
# A claimed verb is the owner's: first on a line (a CV bullet) or right after "I".
OWN_VERB = re.compile(r"\bI(?:'ve| have| had| also| then)?\s+([A-Za-z]+)|^([A-Za-z]+)")
MIN_SHARED = 3  # content words a source line must share with a claim to count as its source
PHONE_LIKE = re.compile(r"\+?\(?\d[\d ().-]{6,}\d")  # 8+ digits in a run: a phone, never a figure


def numbers(text, skip=(), spelled=False):
    """The figures a text states, as bare digits ('3,000' -> '3000'). Links, addresses, dates,
    times, years and the strings in skip carry no claim. spelled=True also reads 'five' as 5
    (for sources, so a message may write the digit)."""
    for s in skip:
        if s:
            text = text.replace(s, " ")
    out = {SPELLED[w] for w in re.findall(r"[a-z]+", text.lower()) if w in SPELLED} if spelled else set()
    for m in NUMBER.finditer(NOT_CLAIMS.sub(" ", text)):
        n = re.sub(r"[kKmMxX]|bn", "", m.group()).replace(",", "").rstrip(".")
        if not (len(n) == 4 and n.isdigit() and 1950 <= int(n) <= 2100):
            out.add(n)
    return out


def claim_lines(text):
    return [s.strip(" -•*\t") for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip(" -•*\t")]


def scope_of(line, claim=False):
    """(content words, highest scope tier, the verb at that tier) of one line. For a claim only
    the owner's own verbs count (OWN_VERB); a source line counts any verb, which keeps the check
    narrow."""
    words = re.findall(r"[a-z][a-z'-]+", line.lower())
    if claim:
        own = [w.lower() for m in OWN_VERB.finditer(line) for w in m.groups() if w]
        verbs = [(SCOPE[w], w) for w in own if w in SCOPE]
    else:
        verbs = [(SCOPE[w], w) for w in words if w in SCOPE]
    content = {w.rstrip("s") for w in words if len(w) >= 4 and w not in STOP and w not in SCOPE}
    tier, verb = max(verbs) if verbs else (0, "")
    return content, tier, verb


def fact_check(where, text, sources, skip, figures=()):
    """Violations for one claim text against the sources: [(line, content, tier, verb)].
    figures: extra texts (the job description) whose numbers a message may quote."""
    v = []
    known = set().union(set(), *(numbers(s[0], spelled=True) for s in sources), *(numbers(f) for f in figures))
    for n in sorted(numbers(text, skip) - known, key=lambda x: (len(x), x)):
        v.append(f"{where} the figure {n} is in neither the CV text nor brief.md: use the true figure, "
                 f"or ask the owner and add it to brief.md")
    for line in claim_lines(text):
        content, tier, verb = scope_of(line, claim=True)
        if tier < 2:
            continue
        matches = [s for s in sources if len(content & s[1]) >= MIN_SHARED]
        if matches and all(s[2] < tier for s in matches) and any(s[2] for s in matches):
            src = max((s for s in matches if s[2]), key=lambda s: len(content & s[1]))
            v.append(f"{where} '{verb}' claims more than its source says ('{src[3]}'): \"{src[0][:100]}\". "
                     f"Use the source's verb, or ask the owner and add the fact to brief.md")
    return v


def never_claims(profile):
    """Strings in any checked text that carry no figure: the phones, the hook names, the links."""
    return [profile["phone"], profile.get("signature_phone", "")] + profile["hooks"] + list(profile["links"].values())


def sources_for(profile):
    brief = profile["_brief"]
    if not brief.is_file():
        die(f"{brief} missing: the fact check reads it beside {profile['_path'].name} (ONBOARDING.md step 3)")
    texts = [brief.read_text(encoding="utf-8-sig"), profile.get("current_role_line") or ""]
    texts += [(ROOT / c["file"]).with_suffix(".txt").read_text(encoding="utf-8-sig") for c in profile["cvs"]]
    out = []
    for t in texts:
        t = PHONE_LIKE.sub(lambda m: " " if sum(c.isdigit() for c in m.group()) >= 8 else m.group(), t)
        for line in claim_lines(t):
            out.append((line,) + scope_of(line))
    return out


def parse_answers(path):
    """[(question, approved: 'no' or a date, limit or None, answer)]. Hard-fails on a bad shape."""
    p = Path(path)
    if not p.is_file():
        die(f"{p} missing")
    text = p.read_text(encoding="utf-8-sig")
    bad = re.search(r"^##(?!# )(?! ).*", text, re.M)
    if bad:
        die(f"{p.name}: '{bad.group()}' needs a space after '##'")
    parts = re.split(r"^## +(.+?)[ \t]*$", text, flags=re.M)
    if re.sub(r"^# .*$", "", parts[0], flags=re.M).strip():
        die(f"{p.name}: text before the first '## <question>': each answer goes under its question")
    out = []
    for q, body in zip(parts[1::2], parts[2::2]):
        lines = body.strip("\n").split("\n")
        approved = re.fullmatch(r"Approved: (no|\d{4}-\d{2}-\d{2})(?: \(.+\))?", lines[0].strip())
        if not approved:
            die(f"{p.name}: under '{q}' the next line must be 'Approved: no' or 'Approved: YYYY-MM-DD (<company>)'")
        if approved.group(1) != "no":
            try:
                date.fromisoformat(approved.group(1))
            except ValueError:
                die(f"{p.name}: under '{q}' {approved.group(1)} is not a real date")
        lines, limit = lines[1:], None
        if lines and lines[0].startswith("Limit:"):
            lm = re.fullmatch(r"Limit: (\d+)(?: characters)?", lines[0].strip())
            if not lm:
                die(f"{p.name}: under '{q}' write the limit as 'Limit: <number>'")
            lines, limit = lines[1:], int(lm.group(1))
        answer = "\n".join(lines).strip()
        if not answer:
            die(f"{p.name}: the answer to '{q}' is empty")
        out.append((q, approved.group(1), limit, answer))
    if not out:
        die(f"{p.name} has no '## <question>' entries (validate.py --help shows the format)")
    return out


def check_answers(path, profile):
    """(violations, stats line) for a file of form answers."""
    entries = parse_answers(path)
    folder = Path(path).resolve().parent
    bank = folder == profile["_path"].resolve().parent
    quotable = [(folder / f).read_text(encoding="utf-8-sig") for f in ("jd.md", "offer.md") if (folder / f).is_file()]
    skip = never_claims(profile)
    sources, v = sources_for(profile), []
    for q, approved, limit, answer in entries:
        where = f"[{q[:50]}]"
        if bank and approved == "no":
            v.append(f"{where} is not approved: the bank keeps only answers the owner approved")
        ph = PLACEHOLDER.search(answer)
        if ph:
            v.append(f"{where} has a placeholder: {ph.group()}")
        if limit and len(answer) > limit:
            v.append(f"{where} is {len(answer)} characters; the form allows {limit}")
        v += fact_check(where, answer, sources, skip, quotable)
    waiting = sum(e[1] == "no" for e in entries)
    return v, f"{len(entries)} answers, {waiting} waiting for the owner's approval"


def check(path, profile):
    """Return (violations, stats line). Hard-fails on unparseable input."""
    meta, secs = parse(path)
    m = messages_for(profile, meta)
    name = m.get("_signature_name") or profile["signature_name"]
    hook_label = {h: m.get("_hook_names", {}).get(h, h) for h in profile["hooks"]}
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
    # CV: a profile CV, or one tailored from a profile CV for this job (cv_from + cv-tailoring.md),
    # snapshotted next to messages.md
    folder = Path(path).resolve().parent
    cv_names = [Path(c["file"]).name for c in profile["cvs"]]
    origin = meta.get("cv_from", "")
    record = folder / "cv-tailoring.md"
    if origin and not is_none(origin):
        if origin not in cv_names:
            v.append(f"cv_from '{origin}' is not a profile CV {cv_names}")
        if not record.is_file():
            v.append(f"cv {meta['cv']} is tailored from {origin}, but cv-tailoring.md (the edits and the "
                     f"owner's approval) is missing from the application folder (flow/apply.md step 0.8)")
        elif origin not in record.read_text(encoding="utf-8-sig"):
            v.append(f"cv-tailoring.md does not name {origin}, the cv_from of messages.md: "
                     f"record which profile CV the tailored one was made from")
    elif meta["cv"] not in cv_names:
        v.append(f"cv '{meta['cv']}' is not a profile CV {cv_names}; a CV tailored for this job needs "
                 f"cv_from: <the profile CV it was made from> and cv-tailoring.md (flow/apply.md step 0.8)")
    if not meta["cv"].lower().endswith(".pdf"):
        v.append(f"cv {meta['cv']} must be a PDF")
    if not (folder / meta["cv"]).is_file():
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
        named = [h for h in hooks if hook_label[h] in body]
        if s in ("T1", "T4", "T3M") and named not in ([hook], []):
            v.append(f"{tag} names {named}; manager texts name only the hook '{hook_label.get(hook, hook)}'")
        if s in ("T1", "T4") and hook_label.get(hook, hook) not in body:
            v.append(f"{tag} hook '{hook_label.get(hook, hook)}' absent")
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

    # fact check: the texts that leave, and the tailored CV's text
    sources = sources_for(profile)
    jd = [(folder / "jd.md").read_text(encoding="utf-8-sig")] if (folder / "jd.md").is_file() else []
    skip = never_claims(profile) + [role, company] + list(hook_label.values())
    for s in SECTIONS + [o for o in OPTIONAL if o in secs]:
        body = secs[s][1]
        if not is_none(body):
            v += fact_check(f"[{s}]", body, sources, skip, jd)
    if origin and not is_none(origin):
        txt = folder / Path(meta["cv"]).with_suffix(".txt").name
        if not txt.is_file():
            v.append(f"{txt.name} missing: save the tailored CV's text there when you read it back "
                     f"(flow/apply.md step 0.8), so its facts can be checked")
        else:
            v += fact_check(f"[{txt.name}]", txt.read_text(encoding="utf-8-sig"), sources, skip)

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
    ap.add_argument("--answers")
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
    if bool(a.messages) == bool(a.answers):
        die("give one thing to check: a messages.md path or --answers <file> (or --format, --defaults, "
            "--check-profile)")
    v, stats = check_answers(a.answers, profile) if a.answers else check(a.messages, profile)
    if v:
        print("FAIL")
        for x in v:
            print(" -", x)
        sys.exit(1)
    print("PASS ", stats)


if __name__ == "__main__":
    run(main)
