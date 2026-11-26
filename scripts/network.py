#!/usr/bin/env python3
"""Who the owner knows at a company: LinkedIn connections matched by employer, for the R1
referral ask (flow/messages.md). Stdlib only; reads a local file, no network.

Usage:
  network.py match "<company>" ["<company>" ...] [--file profile/connections.csv]

Input: LinkedIn's export of the owner's connections (Settings & Privacy > Data privacy > Get a
copy of your data > Connections), saved as profile/connections.csv (ONBOARDING.md step 6).
Its columns: First Name, Last Name, URL, Email Address, Company, Position, Connected On; a
notes paragraph above the header is skipped. Emails are never printed.

Tiers, best first:
  exact   the names agree once case, punctuation and legal suffixes (Ltd, Inc) are dropped
  strong  the same name plus generic words (Acme Robotics / Acme Robotics Israel, Check Point
          / Check Point Software Technologies) or a web suffix (monday.com / Monday)
  weak    they share one distinctive word (Acme / Acme Robotics, Acme Holdings / Acme
          Robotics): ask the owner whether that person works there
Company is each person's employer on the day of the export: a match is a lead for the owner
to confirm, never a fact to state in a message.

Exit 0 = at least one connection matched, 1 = none. Exit 2 = hard-fail (bad input)."""
import argparse
import csv
import io
import sys
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import ROOT, company_key, die, read_text, run

DEFAULT = ROOT / "profile" / "connections.csv"
COLUMNS = ("First Name", "Last Name", "URL", "Company", "Position", "Connected On")
WEB = ("com", "io", "ai", "co", "net", "org", "app", "dev", "tech")
GENERIC = set("the and of for group holdings global international israel technologies technology tech "
              "solutions systems software labs lab digital services data analytics health capital partners "
              "consulting networks security media ventures studio studios industries enterprises bank university "
              "college school institute hospital medical center centre foundation national united american "
              "first general insurance".split())
TIERS = ("exact", "strong", "weak")


def load(path):
    p = Path(path)
    if not p.is_file():
        die(f"{p} missing: export the owner's LinkedIn connections and save them there "
            f"(ONBOARDING.md step 6, item 6)")
    lines = read_text(p, export=True).splitlines()
    at = next((i for i, l in enumerate(lines) if l.lstrip('"').startswith("First Name")), None)
    if at is None:
        die(f"{p.name} has no header row starting 'First Name': is it LinkedIn's Connections.csv?")
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[at:]))))
    missing = [c for c in COLUMNS if c not in (rows[0].keys() if rows else lines[at].split(","))]
    if missing:
        die(f"{p.name} lacks the column(s) {', '.join(missing)}: is it LinkedIn's Connections.csv?")
    return [r for r in rows if (r.get("Company") or "").strip()]


def words_of(name):
    """A company name as words, a trailing web suffix dropped: 'monday.com' -> ['monday']."""
    w = company_key(name).split()
    return w[:-1] if len(w) > 1 and w[-1] in WEB else w


def distinctive(words):
    """Words that point at one company. A one-word name counts even when short (IBM, SAP, Wix)."""
    if len(words) == 1 and len(words[0]) >= 2 and words[0] not in GENERIC:
        return set(words)
    return {w for w in words if len(w) >= 4 and w not in GENERIC}


def tier(target, company):
    """'exact', 'strong', 'weak' or None for one connection's employer against a target company."""
    if not company_key(target) or not company_key(company):
        return None
    if company_key(target) == company_key(company):
        return "exact"
    a, b = words_of(target), words_of(company)
    if "".join(a) == "".join(b):
        return "strong"
    short, long_ = sorted((a, b), key=len)
    if distinctive(short) and long_[:len(short)] == short and all(w in GENERIC for w in long_[len(short):]):
        return "strong"
    if distinctive(a) & set(b):
        return "weak"
    return None


def match(target, rows):
    hits = [(tier(target, r["Company"]), r) for r in rows]
    hits = [(t, r) for t, r in hits if t]
    return sorted(hits, key=lambda h: TIERS.index(h[0]))


def cell(s):
    return " ".join((s or "").replace("|", "/").split())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("match", help="connections who work at each company")
    m.add_argument("companies", nargs="+")
    m.add_argument("--file", default=str(DEFAULT))
    a = ap.parse_args()
    if any(not company_key(c) for c in a.companies):
        die("give each company as a name, e.g. network.py match \"Acme Robotics\"")
    rows, found = load(a.file), 0
    for target in a.companies:
        hits = match(target, rows)
        found += len(hits)
        if not hits:
            print(f"{target}: no connection found\n")
            continue
        print(f"{target}: {len(hits)} connection(s)")
        print("| Tier | Name | Position | Company | Connected on | Profile |\n|---|---|---|---|---|---|")
        for t, r in hits:
            name = cell(f"{r['First Name']} {r['Last Name']}")
            print(f"| {t} | {name} | {cell(r['Position'])} | {cell(r['Company'])} | "
                  f"{cell(r['Connected On'])} | {cell(r['URL'])} |")
        print()
    if found:
        print("Company is each person's employer when the owner exported: confirm with the owner before "
              "the R1 ask; weak matches may be another company.")
    raise SystemExit(0 if found else 1)


if __name__ == "__main__":
    run(main)
