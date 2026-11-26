#!/usr/bin/env python3
"""Does the shortlist hold the jobs the owner would really apply to? Stdlib only.

The kit scores jobs by judgement (flow/find-jobs.md); only the owner can say whether it judged
well. This script keeps the owner's own verdict per posting and measures the kit against it.

Usage:
  fit.py label <triage file> <row> <apply|maybe|skip> [--because <why>] [--reason "<their words>"]
               [--deal-breaker]
        the owner's verdict on one row of a triage list. <row> is the tier and number the list
        shows (A1, B3, C2), or D<n> for the n-th Dropped row. skip and maybe need --because and
        --reason; --deal-breaker (skip only) means the reason alone rules the job out, wherever
        it scored.
  fit.py label <posting link> <apply|maybe|skip> [same options] [--company "<C>" --role "<R>"]
        the same for a posting found by link. One the kit never showed (the owner found it
        elsewhere) needs --company and --role: it counts as a job the search missed.
  fit.py report
        how the kit's tiers agree with the owner's labels: the share of each list's top 10 the
        owner would apply to, deal-breaker leaks (skip for a deal-breaker, but tiered A or B),
        misses (apply, but tiered C, dropped or never found), the reasons given, and a table.

<why> is one of: title, seniority, place, pay, terms, company, work, skills, other. Each names
the brief.md section a change would go to (fit.py --help lists them below).
Labels live in outreach/fit-labels.md, one row per verdict; a later verdict on the same posting
replaces the earlier one in the report, and the same verdict twice writes nothing ("already").
--dir <folder> (default outreach/) is where fit-labels.md and the triage files are.
Exit 2 = hard-fail (bad input), naming the file and line."""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import ROOT, die, read_text, run
from triage import link_key, parse

VERDICTS = ("apply", "maybe", "skip")
# Each reason the owner gives, and the brief.md section a change for it goes to.
BECAUSE = {
    "title": "Targets → titles (wanted, close enough, to skip)",
    "seniority": "Targets → Seniority, or Stretch",
    "place": "Where (locations, work mode, relocation, work authorisation)",
    "pay": "Deal-breakers → Salary floor",
    "terms": "Deal-breakers → Contract, hours, travel",
    "company": "Companies (wanted, ruled out)",
    "work": "Story → More of / less of",
    "skills": "Hooks, and the CV (a must-have the owner lacks or does not want)",
    "other": "none: read the reason",
}
COLS = ["Date", "Triage", "Row", "Company", "Role", "Link", "Verdict", "Because", "Deal-breaker", "Reason"]
HEAD = ("# Fit labels\n\nThe owner's own verdict on postings (fit.py label writes this file; fit.py report reads it).\n\n"
        "| " + " | ".join(COLS) + " |\n|" + "---|" * len(COLS) + "\n")

__doc__ += "\n\nReasons (--because) and the brief.md section each points to:\n" + "".join(
    f"  {k:<10} {v}\n" for k, v in BECAUSE.items())


def cell(value, what):
    """A value safe for one table cell: no '|' and no line break."""
    v = (value or "").strip()
    if "|" in v or "\n" in v or "\r" in v:
        die(f"{what} must not contain '|' or a line break: {v[:60]}")
    return v or "-"


def find_row(lists, ref):
    """(row ref, row dict) for A1 / B3 / C2 / D<n> in a parsed triage list, or a hard-fail."""
    m = re.fullmatch(r"([ABCD])(\d+)", ref.strip().upper())
    if not m:
        die(f"row '{ref}' must be a tier and number as the list shows it (A1, B3, C2) or D<n> for the n-th Dropped row")
    tier, n = m.group(1), int(m.group(2))
    if tier == "D":
        rows = lists.get("Dropped", [])
        if 1 <= n <= len(rows):
            return f"D{n}", rows[n - 1]
    else:
        hit = [r for r in lists.get(tier, []) if r["#"] == str(n)]
        if len(hit) == 1:
            return f"{tier}{n}", hit[0]
    have = [f"{t}{r['#']}" for t in "ABC" for r in lists.get(t, [])] + [
        f"D{i}" for i in range(1, len(lists.get("Dropped", [])) + 1)]
    die(f"no row {ref} in that list; it has: {', '.join(have) or 'no rows'}")


def label(a, folder):
    if a.verdict not in VERDICTS:
        die(f"verdict '{a.verdict}' must be one of {', '.join(VERDICTS)}")
    if a.because and a.because not in BECAUSE:
        die(f"--because '{a.because}' must be one of {', '.join(BECAUSE)}")
    if a.verdict != "apply" and not (a.because and (a.reason or "").strip()):
        die(f"{a.verdict} needs --because <{'|'.join(BECAUSE)}> and --reason \"<the owner's words>\"")
    if a.deal_breaker and a.verdict != "skip":
        die("--deal-breaker goes with skip only: a deal-breaker rules the job out")
    if re.match(r"https?://", a.target):
        if a.row is not None:
            die("a posting link takes no row: fit.py label <link> <verdict> ...")
        triage, ref, company, role, link = "-", "-", a.company, a.role, a.target.strip()
        for p in sorted(folder.glob("triage-*.md"), reverse=True):  # newest list first
            lists = parse(p)
            for tier in ("A", "B", "C", "Dropped"):
                for i, r in enumerate(lists.get(tier, []), 1):
                    if link_key(r["Link"]) == link_key(link):
                        triage, ref = p.name, (f"{tier}{r['#']}" if tier != "Dropped" else f"D{i}")
                        company, role = company or r["Company"], role or r["Role"]
                        break
                if triage != "-":
                    break
            if triage != "-":
                break
        if triage == "-" and not (company and role):
            die("that link is in no triage list here: add --company and --role (it counts as a job the search missed)")
    else:
        if a.company or a.role:
            die("--company and --role go with a posting link; a triage row has its own")
        if a.row is None:
            die("fit.py label <triage file> <row> <verdict>: the row is missing (A1, B3, D2)")
        p = folder / Path(a.target).name
        if not p.is_file():
            die(f"{p} not found: give a triage list in {folder}")
        triage = p.name
        ref, r = find_row(parse(p), a.row)
        company, role, link = r["Company"], r["Role"], r["Link"]
    new = [date.today().isoformat(), triage, ref, cell(company, "--company"), cell(role, "--role"), cell(link, "link"),
           a.verdict, a.because or "-", "yes" if a.deal_breaker else "no", cell(a.reason, "--reason")]
    path = folder / "fit-labels.md"
    current = {link_key(r["Link"]): r for r in read_labels(path)} if path.exists() else {}
    old = current.get(link_key(link))
    if old and [old[c] for c in COLS[6:]] == new[6:]:
        print(f"already: {company}, {role} is labelled {a.verdict}")
        return
    if not path.exists():
        path.write_text(HEAD, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write("| " + " | ".join(new) + " |\n")
    print(f"{'changed' if old else 'recorded'}: {company}, {role} → {a.verdict}"
          + (f" ({a.because}{', deal-breaker' if a.deal_breaker else ''})" if a.because else ""))


def read_labels(path):
    """Every row of fit-labels.md as a dict with its line number under '_line'. Hard-fails on a
    header that is not the kit's, a row of the wrong width, or a cell outside its list."""
    rows, header = [], False
    for n, line in enumerate(read_text(path).splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        where = f"{path}, line {n}"
        if not header:
            if cells != COLS:
                die(f"{where}: the columns are {cells}; need {COLS}. Rewrite the header, or move the file aside "
                    f"and label again")
            header = True
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) != len(COLS):
            die(f"{where}: {len(cells)} cells, the header has {len(COLS)}: {s[:80]}")
        r = dict(zip(COLS, cells), _line=n)
        try:
            date.fromisoformat(r["Date"])
        except ValueError:
            die(f"{where}: Date '{r['Date']}' must be YYYY-MM-DD")
        if r["Verdict"] not in VERDICTS:
            die(f"{where}: Verdict '{r['Verdict']}' must be one of {', '.join(VERDICTS)}")
        if r["Because"] != "-" and r["Because"] not in BECAUSE:
            die(f"{where}: Because '{r['Because']}' must be one of {', '.join(BECAUSE)} or -")
        if r["Deal-breaker"] not in ("yes", "no"):
            die(f"{where}: Deal-breaker '{r['Deal-breaker']}' must be yes or no")
        if r["Deal-breaker"] == "yes" and r["Verdict"] != "skip":
            die(f"{where}: Deal-breaker yes goes with skip only")
        if not re.match(r"https?://", r["Link"]):
            die(f"{where}: Link '{r['Link'][:60]}' must be the posting's URL")
        rows.append(r)
    if not header:
        die(f"{path}: no labels table found (fit.py label writes it)")
    return rows


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    ap = argparse.ArgumentParser(prog="fit.py", add_help=False)
    ap.add_argument("--dir", default=str(ROOT / "outreach"))
    sub = ap.add_subparsers(dest="cmd")
    lb = sub.add_parser("label", add_help=False)
    lb.add_argument("target")
    lb.add_argument("rest", nargs="+")
    lb.add_argument("--because")
    lb.add_argument("--reason")
    lb.add_argument("--deal-breaker", action="store_true")
    lb.add_argument("--company")
    lb.add_argument("--role")
    lb.add_argument("--dir", dest="subdir")
    rp = sub.add_parser("report", add_help=False)
    rp.add_argument("--dir", dest="subdir")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        die(__doc__)
    folder = Path(a.subdir or a.dir)
    if not folder.is_dir():
        die(f"{folder} not found: the folder that holds the triage lists and fit-labels.md")
    if a.cmd == "label":
        if len(a.rest) == 1:
            a.row, a.verdict = None, a.rest[0]
        elif len(a.rest) == 2:
            a.row, a.verdict = a.rest
        else:
            die("fit.py label <triage file> <row> <verdict>, or fit.py label <link> <verdict>")
        label(a, folder)
    elif a.cmd == "report":
        report(folder)
    else:
        die(__doc__)


TIER_ORDER = {"A": 0, "B": 1, "C": 2}
TOP = 10
FEW = 10  # below this many labels, shares are shown but read the rows, not the numbers


def ranked(lists):
    """The kept rows of a parsed triage list in the kit's order: tier, then score, then number."""
    rows = [(t, r) for t in "ABC" for r in lists.get(t, [])]

    def key(tr):
        t, r = tr
        score = int(r["Score"]) if r["Score"].isdigit() else 0
        num = int(r["#"]) if r["#"].isdigit() else 0
        return TIER_ORDER[t], -score, num
    return sorted(rows, key=key)


def place(lists, link):
    """Where a triage list put a posting: (tier or 'Dropped', row ref, score or reason), or None."""
    for t in "ABC":
        for r in lists.get(t, []):
            if link_key(r["Link"]) == link_key(link):
                return t, f"{t}{r['#']}", f"score {r['Score']}"
    for i, r in enumerate(lists.get("Dropped", []), 1):
        if link_key(r["Link"]) == link_key(link):
            return "Dropped", f"D{i}", r["Reason"]
    return None


def located(folder, path):
    """The owner's latest label per posting, each with where the kit put it: '_tier' (A, B, C,
    Dropped, or 'not shown'), '_ref', '_kit' (its score or drop reason) and '_list'."""
    lists, latest = {}, {}

    def get(name):
        if name not in lists:
            lists[name] = parse(folder / name)
        return lists[name]
    for r in read_labels(path):
        latest[link_key(r["Link"])] = r
    names = sorted((p.name for p in folder.glob("triage-*.md")), reverse=True)
    out = []
    for r in latest.values():
        where = f"{path}, line {r['_line']}"
        if r["Triage"] != "-":
            if not (folder / r["Triage"]).is_file():
                die(f"{where}: triage list {folder / r['Triage']} not found. Put it back, or label that posting "
                    f"again by its link")
            hit = place(get(r["Triage"]), r["Link"])
            if not hit:
                die(f"{where}: {r['Link']} is not in {r['Triage']}. Label that posting again by its link")
            r["_list"] = r["Triage"]
        else:
            hit, r["_list"] = None, None
            for name in names:  # a later list may have found it after all
                hit = place(get(name), r["Link"])
                if hit:
                    r["_list"] = name
                    break
        r["_tier"], r["_ref"], r["_kit"] = hit or ("not shown", "-", "the search never found it")
        out.append(r)
    return out, {n: get(n) for n in {r["_list"] for r in out if r["_list"]}}


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "-"


def report(folder):
    path = folder / "fit-labels.md"
    if not path.is_file():
        die(f"{path} not found: no labels yet. Show the owner a triage list, ask which they would really apply "
            f"to, and record each answer with fit.py label (flow/find-jobs.md step 6)")
    labels, lists = located(folder, path)
    by_link = {link_key(r["Link"]): r for r in labels}
    print(f"Fit report: {len(labels)} postings labelled, from {len(lists)} triage list(s) ({path})")
    if len(labels) < FEW:
        print(f"Fewer than {FEW} labels: too few to tell. Read the rows below, not the shares.")
    print()
    seen = applied = 0
    per_list = []
    for name in sorted(lists):
        top = [by_link.get(link_key(r["Link"])) for _, r in ranked(lists[name])[:TOP]]
        mine = [r for r in top if r and r["_list"] == name]
        yes = sum(r["Verdict"] == "apply" for r in mine)
        seen, applied = seen + len(mine), applied + yes
        per_list.append(f"{name}: {yes} of {len(mine)}")
    print(f"Top {TOP}: you would apply to {applied} of the {seen} you labelled ({pct(applied, seen)}) among the kit's "
          f"first {TOP} jobs of each list.")
    if len(per_list) > 1:
        print("  " + "; ".join(per_list))

    def line(r, why=True):
        out = f"  {r['_ref']} {r['Company']}, {r['Role']} (kit: {r['_kit']})"
        if why and r["Because"] != "-":
            out += f": {r['Because']}, \"{r['Reason']}\" → brief.md {BECAUSE[r['Because']]}"
        elif why and r["Reason"] != "-":
            out += f": \"{r['Reason']}\""
        return out
    leaks = [r for r in labels if r["Verdict"] == "skip" and r["Deal-breaker"] == "yes" and r["_tier"] in ("A", "B")]
    print(f"\nDeal-breaker leaks: {len(leaks)} (you said skip, for a reason that rules the job out, but the kit "
          f"put it in A or B: a gate or a brief line is missing)")
    for r in leaks:
        print(line(r))
    misses = [r for r in labels if r["Verdict"] == "apply" and r["_tier"] in ("C", "Dropped", "not shown")]
    print(f"\nMisses: {len(misses)} (you would apply, but the kit put it in C, dropped it, or never found it)")
    for r in misses:
        print(line(r, why=False))
    counts = {}
    for r in labels:
        if r["Verdict"] != "apply" and r["Because"] != "-":
            counts[r["Because"]] = counts.get(r["Because"], 0) + 1
    print("\nReasons you gave for skip and maybe, most often first, and the brief.md section each points to:")
    for why, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {why:<10} {n}  {BECAUSE[why]}")
    if not counts:
        print("  none yet")
    print("\n| Kit put it in | apply | maybe | skip |\n|---|---|---|---|")
    for tier in ("A", "B", "C", "Dropped", "not shown"):
        cells = [sum(r["_tier"] == tier and r["Verdict"] == v for r in labels) for v in VERDICTS]
        print(f"| {tier} | " + " | ".join(map(str, cells)) + " |")


if __name__ == "__main__":
    run(main)
