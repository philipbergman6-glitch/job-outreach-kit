#!/usr/bin/env python3
"""The owner's portfolio: the pieces of work that can prove a fit, and which one fits a job.

Usage:
  portfolio.py list                    every catalog entry, as profile.json holds it
  portfolio.py check                   the catalog is complete: own part, proof, keywords, links
  portfolio.py rank <slug|posting>     the entries ranked against a saved posting, each point quoted
  portfolio.py migrate                 an older profile ('hooks' names only): catalog entries to fill in
  portfolio.py github <user>           the owner's public GitHub repositories, as entries to confirm

The catalog is profile.json "portfolio", a list of entries:
  {"id": "launch-playbook",            short, lowercase letters, digits and dashes; unique
   "name": "Launch Playbook",          the hook name messages use; unique
   "what": "a repeatable launch process",
   "link": "https://..." or null,      where an employer can see it
   "shareable": true,                  true: the link may go into messages; false: it never does
   "no_link_why": "...",               shareable with no link: why there is none (yet)
   "own_part": "built and ran it",     what the owner did themselves, in the CV's or brief.md's words
   "proof": "conversion 11% to 16%",   the number or visible result; its figures trace to the CV or brief.md
   "skills": ["product launches"],     words a posting would use for what it proves
   "fits": ["product marketing"]}      the kinds of job it fits
Each entry's name is a hook: messages.md front matter `hook:` names one, `portfolio:` its id,
and `portfolio_link:` its link once the owner approved sharing it for that job (else none).
An older profile with only "hooks" (a list of names) still works for messages; `migrate` turns
it into catalog entries, prefilled from brief.md → "Hooks".

Default profile: profile/profile.json. Exit 1 = check found problems, 2 = hard-fail."""
import argparse
import re
import sys
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import die, run


ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TEXT_FIELDS = ("what", "no_link_why", "own_part", "proof")
LIST_FIELDS = ("skills", "fits")


def _entry_problem(i, e):
    """The first thing in catalog entry i that would break a script, or None."""
    if not isinstance(e, dict):
        return f"portfolio entry {i + 1}: each entry must be an object like {{\"id\": ..., \"name\": ...}}"
    name = e.get("name")
    if not isinstance(name, str) or not name.strip():
        return f"portfolio entry {i + 1} needs a name (the hook name messages use)"
    where = f"portfolio entry '{name}'"
    if not isinstance(e.get("id"), str) or not ID.fullmatch(e["id"]):
        return (f"{where}: id '{e.get('id')}' must be lowercase letters, digits and dashes, "
                f"e.g. '{slug(name)}'")
    link = e.get("link")
    if link is not None and (not isinstance(link, str) or not re.match(r"https?://[^\s/]+\.[^\s]+$", link)):
        return f"{where}: link must start with http:// or https:// and be one address, or be null"
    if not isinstance(e.get("shareable"), bool):
        return f"{where}: shareable must be true or false (may its link go into messages?)"
    for k in TEXT_FIELDS:
        if k in e and not isinstance(e[k], str):
            return f"{where}: {k} must be text"
    for k in LIST_FIELDS:
        if k in e and (not isinstance(e[k], list) or not all(isinstance(w, str) and w.strip() for w in e[k])):
            return f"{where}: {k} must be a list of words, e.g. [\"product launches\"]"
    unknown = set(e) - {"id", "name", "link", "shareable"} - set(TEXT_FIELDS) - set(LIST_FIELDS)
    if unknown:
        return f"{where}: unknown keys {sorted(unknown)} (portfolio.py --help lists the keys)"
    return None


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def load_catalog(path, p):
    """Read profile.json "portfolio" (or the older "hooks") into p["portfolio"] and p["hooks"].
    p["_catalog"] is False for an older profile with hook names only. Hard-fails on any entry a
    script could not use; whether the entries are complete is `portfolio.py check`'s question."""
    cat = p.get("portfolio")
    hooks = p.get("hooks")
    if cat is None:
        if not isinstance(hooks, list) or not hooks:
            die(f"{path}: 'portfolio' must be a non-empty list of projects (portfolio.py --help shows an entry)")
        if not all(isinstance(h, str) and h.strip() for h in hooks):
            die(f"{path}: 'hooks' must be a list of names")
        p["portfolio"], p["_catalog"] = [], False
        return
    if not isinstance(cat, list) or not cat:
        die(f"{path}: 'portfolio' must be a non-empty list of projects (portfolio.py --help shows an entry)")
    seen = {"id": set(), "name": set()}
    for i, e in enumerate(cat):
        bad = _entry_problem(i, e)
        if bad:
            die(f"{path}: {bad}")
        for k, v in (("id", e["id"]), ("name", e["name"].strip().casefold())):
            if v in seen[k]:
                die(f"{path}: portfolio {k} '{e[k]}' is used twice: each entry needs its own")
            seen[k].add(v)
    names = [e["name"] for e in cat]
    if hooks is not None:
        if not isinstance(hooks, list):
            die(f"{path}: 'hooks' must be a list of names; the hook names now come from 'portfolio', "
                f"so remove 'hooks'")
        extra = [h for h in hooks if h not in names]
        if extra:
            die(f"{path}: 'hooks' lists '{extra[0]}', which no portfolio entry is named: the hook names "
                f"now come from 'portfolio', so remove 'hooks'")
    p["hooks"], p["_catalog"] = names, True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()


if __name__ == "__main__":
    run(main)
