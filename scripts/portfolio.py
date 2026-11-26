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
import json
import re
import sys
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import die, run


ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TEXT_FIELDS = ("what", "no_link_why", "own_part", "proof")
LIST_FIELDS = ("skills", "fits")
ASK = {"own_part": "ask the owner what they did themselves",
       "proof": "ask the owner for the number or visible result",
       "skills": "list the words a posting would use for what it proves",
       "fits": "list the kinds of job it fits"}


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


# ---------- the project and link one application's messages cite ----------
# A link is written with a scheme (https://...), with www., or as host/path on a common top-level
# domain (github.com/dana/x). Node.js/React and e.g. carry no link; an address after @ is an email.
TLDS = set("com org net io dev app ai co me il uk de fr eu info xyz site page tech so sh ly gg tv us ca au in "
           "nl es it ch se no fi dk pl pt be at ie nz jp br".split())
LINK = re.compile(r"(?<![\w@./-])(?:(https?://)|(www\.))?((?:[A-Za-z0-9-]+\.)+([A-Za-z]{2,}))"
                  r"(?::\d+)?(/[^\s<>()\[\]\"']*)?", re.I)


def norm_link(url):
    """A link folded for comparing: no scheme, no www., no trailing slash or punctuation, lowercase."""
    u = re.sub(r"^https?://", "", url.strip().lower())
    return re.sub(r"^www\.", "", u).rstrip(".,;:!?").rstrip("/")


def links_in(text):
    """Every link a text writes, as written (trailing punctuation dropped)."""
    out = []
    for m in LINK.finditer(text):
        scheme, www, _, tld, path = m.groups()
        if scheme or www or (path and tld.lower() in TLDS):
            out.append(m.group().rstrip(".,;:!?"))
    return out


def message_problems(p, meta, texts):
    """Violations of one messages.md against the catalog. texts: [(section, body)] that will be
    checked. Front matter `portfolio:` (an id) must be the entry `hook:` names; `portfolio_link:`
    the owner approved must be that entry's link, shareable, and in T1. In any text, a
    non-shareable entry's link never appears; in T1 and T2 no link appears but the profile's
    links and the approved one."""
    v = []
    pid = meta.get("portfolio", "").strip()
    approved = meta.get("portfolio_link", "").strip()
    pid = "" if pid.lower() == "none" else pid
    approved = "" if approved.lower() == "none" else approved
    if not p["_catalog"]:
        if pid or approved:
            v.append("messages.md records portfolio / portfolio_link, but profile.json has no portfolio catalog: "
                     "run portfolio.py migrate, or remove those two lines")
        return v
    by_id = {e["id"]: e for e in p["portfolio"]}
    entry = next((e for e in p["portfolio"] if e["name"] == meta["hook"]), None)
    if pid and pid not in by_id:
        v.append(f"portfolio '{pid}' is not an id in profile.json → portfolio {sorted(by_id)}")
    elif pid and by_id[pid]["name"] != meta["hook"]:
        v.append(f"portfolio '{pid}' is {by_id[pid]['name']}, but hook is {meta['hook']}: "
                 f"record the one project T1 cites in both")
    elif pid:
        entry = by_id[pid]
    if approved and entry:
        if not entry.get("link") or norm_link(entry["link"]) != norm_link(approved):
            v.append(f"portfolio_link {approved} is not {entry['name']}'s link ({entry.get('link') or 'none'} "
                     f"in profile.json → portfolio)")
        elif not entry["shareable"]:
            v.append(f"{entry['name']}'s link is not shareable (profile.json → portfolio): set portfolio_link: none")
        else:
            t1 = dict(texts).get("T1")
            if t1 is not None and norm_link(approved) not in {norm_link(u) for u in links_in(t1)}:
                v.append(f"[T1] the approved project link {approved} missing: cite it with the project, "
                         f"or set portfolio_link: none")
    private = {norm_link(e["link"]): e["name"] for e in p["portfolio"] if e.get("link") and not e["shareable"]}
    allowed = {norm_link(u) for u in p["links"].values()} | ({norm_link(approved)} if approved else set())
    catalog = {norm_link(e["link"]) for e in p["portfolio"] if e.get("link")}
    for s, body in texts:
        for u in links_in(body):
            n = norm_link(u)
            if n in private:
                v.append(f"[{s}] link {u} is {private[n]}'s, which profile.json marks not shareable: take it out")
            elif n not in allowed and (s in ("T1", "T2") or n in catalog):
                v.append(f"[{s}] link {u} is not approved for this job: messages carry the profile's links and "
                         f"the portfolio_link the owner approved (flow/apply.md step 0.8), nothing else")
    return v


def profile(path=None):
    from validate import load_profile
    return load_profile(path)


def no_catalog(p):
    return (f"{p['_path']} has no portfolio catalog yet, only hook names ({', '.join(p['hooks'])}): run "
            f"`python3 scripts/portfolio.py migrate`, fill in what it leaves open with the owner, and put "
            f"the entries in profile.json as \"portfolio\" in place of \"hooks\"")


def problems(p):
    """What keeps the catalog from proving anything: empty parts, a shareable entry with no link
    and no reason, a proof figure that traces to neither the CV text nor brief.md."""
    if not p["_catalog"]:
        return [no_catalog(p)]
    from validate import numbers, sources_for
    known = set().union(*(numbers(s[0], spelled=True) for s in sources_for(p)))
    out = []
    for e in p["portfolio"]:
        where = f"'{e['name']}'"
        for k, ask in ASK.items():
            if not (e.get(k) or "") or (isinstance(e[k], str) and not e[k].strip()):
                out.append(f"{where}: {k} is empty: {ask}")
        if e["shareable"] and not e.get("link") and not e.get("no_link_why", "").strip():
            out.append(f"{where} is shareable but has no link: add the link, or say why there is none in "
                       f"no_link_why")
        for n in sorted(numbers(e.get("proof", ""), [e.get("link") or ""]) - known, key=lambda x: (len(x), x)):
            out.append(f"{where}: proof figure {n} is in neither the CV text nor brief.md: use the true "
                       f"figure, or ask the owner and add it to brief.md")
    return out


def cmd_check(p):
    bad = problems(p)
    if bad:
        print("FAIL")
        for x in bad:
            print(" -", x)
        sys.exit(1)
    print(f"CATALOG OK  {len(p['portfolio'])} entries: {', '.join(e['id'] for e in p['portfolio'])}")


# ---------- rank: the catalog against one posting ----------
# A posting's lines fall under headings. Under a requirements heading a match is a must-have
# (3 points); under a nice-to-have heading, or on a line that calls itself an advantage, it is
# a nice-to-have (1); anywhere else it is mentioned (2). Each keyword counts once, at its best line.
POINTS = {"must-have": 3, "mentioned": 2, "nice-to-have": 1}
MUST_CUES = ("requirement", "qualification", "must", "what you bring", "what you'll need", "what you need",
             "looking for", "who you are", "about you", "you have", "you'll have", "you should have",
             "skills", "experience", "דרישות", "כישורים")
NICE_CUES = ("nice to have", "nice-to-have", "bonus", "advantage", "a plus", "preferred", "would be great",
             "יתרון")
HEADING_WORDS = ("about", "benefits", "perks", "what we offer", "responsibilities", "what you'll do",
                 "what you will do", "the role", "why join", "our team", "the team", "requirements",
                 "qualifications", "nice to have", "bonus points", "about you", "תיאור התפקיד", "דרישות",
                 "דרישות התפקיד")
META_LINE = re.compile(r"(URL|Fetched|Cross-check|Arrived as|Link|Posted|posted|closed):")


def posting_path(arg):
    """The posting text for a slug (outreach/<slug>/jd.md, outreach/jobs/<slug>.md) or a file path."""
    from _common import ROOT
    tried = [Path(arg), ROOT / "outreach" / arg / "jd.md", ROOT / "outreach" / "jobs" / f"{arg}.md"]
    for t in tried:
        if t.is_file():
            return t
    die(f"no saved posting for '{arg}': looked for " + ", ".join(str(t.relative_to(ROOT)) if t.is_absolute()
        and ROOT in t.parents else str(t) for t in tried) + ". Save the posting's full text first "
        "(flow/apply.md step 0.2 writes jd.md)")


def _heading(line):
    """The kind of section a heading line opens, or None when the line is not a heading."""
    raw = line.strip()
    bare = raw.strip("#*_ ").rstrip(":").strip("*_ ").strip()
    low = bare.lower()
    marked = raw.endswith(":") or raw.startswith("#") or (raw.startswith("**") and raw.endswith("**"))
    if not bare or len(bare) > 60 or not (marked or low in HEADING_WORDS):
        return None
    if any(c in low for c in NICE_CUES):
        return "nice-to-have"
    if any(c in low for c in MUST_CUES):
        return "must-have"
    return "mentioned"


def posting_lines(text):
    """[(kind, line)] for every line of the posting that could hold a match, bullets stripped."""
    kind, out = "mentioned", []
    for line in text.splitlines():
        h = _heading(line)
        if h:
            kind = h
            continue
        bare = line.strip().lstrip("-*•·–>").strip()
        if not bare or META_LINE.match(bare):
            continue
        low = bare.lower()
        out.append(("nice-to-have" if any(c in low for c in NICE_CUES) else kind, bare))
    return out


def keyword_rx(kw):
    """A keyword as a pattern: case-insensitive, spaces and dashes alike, a plural allowed."""
    words = [w for w in re.split(r"[\s-]+", kw.strip()) if w]
    last = words[-1]
    alts = {last} | ({last[:-2]} if last.lower().endswith("es") else set()) | (
        {last[:-1]} if last.lower().endswith("s") else set())
    tail = "(?:" + "|".join(re.escape(a) for a in sorted(alts, key=len, reverse=True) if a) + ")"
    if last[-1].isalpha():
        tail += "(?:s|es)?"
    body = r"[\s-]+".join([re.escape(w) for w in words[:-1]] + [tail])
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.I)


def quote(line, m, width=200):
    """The posting's own words around a match: the whole line, or a window of it on word edges."""
    if len(line) <= width:
        return line
    a, b = max(0, m.start() - width // 2), min(len(line), m.end() + width // 2)
    a = line.rfind(" ", 0, a) + 1 if a else 0
    b = line.find(" ", b) if line.find(" ", b) != -1 else len(line)
    return line[a:b].strip()


def score(entry, lines):
    """(points, [(kind, keyword, quote)]) for one entry against the posting's lines."""
    hits = []
    for kw in dict.fromkeys(entry.get("skills", []) + entry.get("fits", [])):
        rx, best = keyword_rx(kw), None
        for kind, line in lines:
            m = rx.search(line)
            if m and (best is None or POINTS[kind] > POINTS[best[0]]):
                best = (kind, kw, quote(line, m))
        if best:
            hits.append(best)
    hits.sort(key=lambda h: -POINTS[h[0]])
    return sum(POINTS[h[0]] for h in hits), hits


def link_note(e):
    if e.get("link"):
        return f"link: {e['link']} ({'may be shared' if e['shareable'] else 'private: never in messages'})"
    return "link: none" + (f" ({e['no_link_why'].strip()})" if e.get("no_link_why", "").strip() else "")


def cv_for(p, folder):
    """The profile CV this application uses: the one copied into its folder, else the default."""
    names = {Path(c["file"]).name: c for c in p["cvs"]}
    if folder and folder.is_dir():
        for f in sorted(folder.glob("*.pdf")):
            if f.name in names:
                return names[f.name]
    return next((c for c in p["cvs"] if c["use_when"].strip().lower() == "default"), p["cvs"][0])


def cmd_rank(p, arg, top=2):
    if not p["_catalog"]:
        die(no_catalog(p))
    from _common import ROOT, read_text
    path = posting_path(arg).resolve()
    lines = posting_lines(read_text(path))
    ranked = sorted(((score(e, lines), i, e) for i, e in enumerate(p["portfolio"])),
                    key=lambda r: (-r[0][0], r[1]))
    print(f"RANK  {path.relative_to(ROOT) if ROOT in path.resolve().parents else path}")
    for n, ((points, hits), _, e) in enumerate(ranked, 1):
        if not hits:
            print(f"{n}. {e['id']}  {e['name']}  0 points: no posting words matched")
            continue
        print(f"{n}. {e['id']}  {e['name']}  {points} point{'s' if points != 1 else ''}  {link_note(e)}")
        for kind, kw, q in hits:
            print(f'   {kind} "{kw}": "{q}"')
    must = list(dict.fromkeys(kw for (_, hits), _, _ in ranked[:top] for kind, kw, _ in hits if kind == "must-have"))
    cv = cv_for(p, path.parent if path.name == "jd.md" else None)
    cv_text = read_text((ROOT / cv["file"]).with_suffix(".txt"))
    has = [kw for kw in must if keyword_rx(kw).search(cv_text)]
    lacks = [kw for kw in must if kw not in has]
    print(f"CV {cv['file']} names: {', '.join(has) or 'none of them'}; lacks: {', '.join(lacks) or 'none'}"
          f" (the must-have words the top {top} matched)")


def cmd_list(p):
    if not p["_catalog"]:
        print("Hook names only, no catalog yet:", ", ".join(p["hooks"]))
        print(no_catalog(p))
        return
    for e in p["portfolio"]:
        print(f"{e['id']}  {e['name']}  {link_note(e)}")
        for label, k in (("what", "what"), ("own part", "own_part"), ("proof", "proof")):
            if e.get(k, "").strip():
                print(f"   {label}: {e[k].strip()}")
        for k in LIST_FIELDS:
            print(f"   {k}: {', '.join(e.get(k, [])) or '(none)'}")


OPEN = {"what": "<one sentence: what it was>", "shareable": "<true or false: may its link go into messages?>",
        "own_part": "<what the owner did themselves>", "proof": "<the number or visible result>",
        "skills": "<words a posting would use for what it proves>", "fits": "<kinds of job it fits>"}
BRIEF_LABELS = {"what it was": "what", "the owner's own part": "own_part", "proof": "proof",
                "fits jobs that ask for": "skills"}
URL = re.compile(r"https?://[^\s,;)>]+")


def brief_hooks(text):
    """{hook name: {field: text}} from brief.md → "## Hooks" → "### <name>" blocks of "- Label: value"."""
    m = re.search(r"^## Hooks[ \t]*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    out, cur = {}, None
    for line in (m.group(1) if m else "").splitlines():
        h = re.match(r"### +(.+?)\s*$", line)
        if h:
            cur = out.setdefault(h.group(1), {})
            continue
        f = re.match(r"\s*[-*] +([^:]+):\s*(.+?)\s*$", line)
        if cur is not None and f and f.group(1).strip().lower() in BRIEF_LABELS:
            cur[BRIEF_LABELS[f.group(1).strip().lower()]] = f.group(2)
    return out


def cmd_migrate(p):
    """Catalog entries for an older profile's hook names, prefilled from brief.md. Prints only:
    the owner confirms each entry before it goes into profile.json."""
    if p["_catalog"]:
        print("nothing to migrate: profile.json already has a portfolio catalog (portfolio.py check)")
        return
    from _common import read_text
    known = brief_hooks(read_text(p["_brief"])) if p["_brief"].is_file() else {}
    entries, ids = [], set()
    for name in p["hooks"]:
        b = known.get(name, {})
        link = URL.search(b.get("proof", ""))
        i = slug(name)
        while i in ids:
            i += "-2"
        ids.add(i)
        skills = [w.strip() for w in re.split(r"[,;]", b.get("skills", "").rstrip(".")) if w.strip()]
        entries.append({"id": i, "name": name, "what": b.get("what") or OPEN["what"],
                        "link": link.group().rstrip(".") if link else None, "shareable": OPEN["shareable"],
                        "own_part": b.get("own_part") or OPEN["own_part"],
                        "proof": b.get("proof") or OPEN["proof"],
                        "skills": skills or [OPEN["skills"]], "fits": [OPEN["fits"]]})
    print(json.dumps({"portfolio": entries}, indent=2, ensure_ascii=False))


GH_USER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")


def cmd_github(user):
    """The owner's public, non-fork, non-archived repositories as catalog entries to confirm.
    Prints only: nothing is written, and the owner's own part and proof stay for them to give."""
    if not GH_USER.fullmatch(user):
        die(f"'{user}' is not a GitHub user name (letters, digits and single dashes, at most 39): "
            f"it is the part after github.com/ in the owner's profile link")
    import _common
    gh_auth = _common.env_optional("GITHUB_TOKEN").get("GITHUB_TOKEN")
    hdr = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {gh_auth}"} if gh_auth else {})}
    try:
        repos = _common.http(f"https://api.github.com/users/{user}/repos?type=owner&sort=pushed&per_page=100",
                             headers=hdr)
    except _common.NetError as e:
        if e.status == 404:
            die(f"GitHub has no user '{user}': check the name on the owner's GitHub profile page")
        die(f"GitHub user '{user}': {e}")
    if not isinstance(repos, list):
        die(f"GitHub user '{user}': the reply is not a list of repositories: {str(repos)[:150]}")
    repos = [r for r in repos if isinstance(r, dict) and r.get("name") and r.get("html_url")]
    keep = [r for r in repos if not r.get("fork") and not r.get("archived")]
    left = [f"{r['name']} ({'a fork' if r.get('fork') else 'archived'})" for r in repos if r not in keep]
    print(f"GITHUB  {user}: {len(repos)} public repositories{'' if len(repos) < 100 else ' (the 100 pushed to most recently)'}")
    for r in keep:
        print(f"  {r['name']}  {r['html_url']}  {r.get('language') or '-'}  stars {r.get('stargazers_count', 0)}  "
              f"pushed {(r.get('pushed_at') or '')[:10]}  {r.get('description') or ''}".rstrip())
    if left:
        print("  left out: " + ", ".join(left))
    print("Suggestions only: show each to the owner. Keep the ones that prove something for the jobs they "
          "want; for each, they say whether the link may be shared, what they did themselves and what it "
          "proved. Then it goes into profile.json → portfolio (portfolio.py check).")
    entries = [{"id": slug(r["name"]), "name": r["name"], "what": r.get("description") or OPEN["what"],
                "link": r["html_url"], "shareable": OPEN["shareable"], "own_part": OPEN["own_part"],
                "proof": OPEN["proof"],
                "skills": [w for w in [r.get("language")] + list(r.get("topics") or []) if w] or [OPEN["skills"]],
                "fits": [OPEN["fits"]]} for r in keep]
    print(json.dumps({"portfolio": entries}, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("list")
    sub.add_parser("migrate")
    g = sub.add_parser("github")
    g.add_argument("user", help="the owner's GitHub user name")
    r = sub.add_parser("rank")
    r.add_argument("posting", help="an application slug, a saved posting's slug in outreach/jobs/, or a file")
    a = ap.parse_args()
    if a.cmd == "github":
        return cmd_github(a.user)
    p = profile(a.profile)
    if a.cmd == "check":
        cmd_check(p)
    elif a.cmd == "list":
        cmd_list(p)
    elif a.cmd == "migrate":
        cmd_migrate(p)
    elif a.cmd == "rank":
        cmd_rank(p, a.posting)


if __name__ == "__main__":
    run(main)
