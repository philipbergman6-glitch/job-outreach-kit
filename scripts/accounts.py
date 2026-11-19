#!/usr/bin/env python3
"""The owner's permission, and a daily pace limit, for everything done inside their signed-in
accounts (LinkedIn, Jobify360, any job board, their mailbox). Stdlib only.

Usage:
  accounts.py check <site> <use>            ALLOWED (exit 0) or DENIED (exit 3), with today's count
  accounts.py record <site> <use> "<what>"  check, then log the action; DENIED logs nothing
  accounts.py status                        every permission and today's use

<use> is one of:
  search_jobs   read job searches and job pages inside the account
  read_people   open a person's profile or a company's people page
  apply         submit an application inside the site (Easy Apply, quick apply)
  invites       send a connection invite
  messages      send a message inside the site
  mailbox       in the owner's mailbox (webmail page or a mail tool): search it for replies and
                bounces, save drafts. Never send: emails leave only through mail.py send

The permissions live in profile/profile.json → "accounts", written at onboarding from the
owner's own answers, e.g.
  "accounts": {"linkedin": {"search_jobs": true, "read_people": true, "apply": false,
                            "invites": false, "messages": false}}
A site or use not listed there is DENIED. Each use has its own daily limit on each site (reading
pages and sending invites carry different risks): the defaults below, changed per site and use
in "account_caps", e.g. {"linkedin": {"read_people": 15}}.
Log: outreach/accounts-log.md. Exit 2 = hard-fail (bad input)."""
import sys
from datetime import datetime

from _common import ROOT, die, run

USES = ("search_jobs", "read_people", "apply", "invites", "messages", "mailbox")
DEFAULT_CAPS = {"search_jobs": 15, "read_people": 20, "apply": 10, "invites": 10, "messages": 10, "mailbox": 30}
LOG = ROOT / "outreach" / "accounts-log.md"
HEADER = "| When | Site | Use | What |\n|---|---|---|---|\n"


def check_accounts(path, p):
    """Validate profile 'accounts' and 'account_caps'; called by validate.load_profile."""
    acc = p.setdefault("accounts", {})
    if not isinstance(acc, dict):
        die(f"{path}: 'accounts' must map a site to its permissions, e.g. {{\"linkedin\": {{\"read_people\": true}}}}")
    for key in ("accounts", "account_caps"):  # site names match in any letter case
        block = p.get(key, {})
        if isinstance(block, dict):
            lower = {}
            for site, v in block.items():
                if site.strip().lower() in lower:
                    die(f"{path}: {key} lists '{site}' twice (sites match in any letter case)")
                lower[site.strip().lower()] = v
            p[key] = lower
    acc = p["accounts"]
    for site, perms in acc.items():
        if not isinstance(perms, dict):
            die(f"{path}: accounts.{site} must be an object of use: true/false")
        for use, v in perms.items():
            if use not in USES:
                die(f"{path}: accounts.{site}.{use} is not a use; one of {', '.join(USES)}")
            if not isinstance(v, bool):
                die(f"{path}: accounts.{site}.{use} must be true or false")
    caps = p.setdefault("account_caps", {})
    if not isinstance(caps, dict):
        die(f"{path}: 'account_caps' must map a site to {{use: number}}")
    for site, per in caps.items():
        if not isinstance(per, dict):
            die(f"{path}: account_caps.{site} must be an object of use: number")
        for use, n in per.items():
            if use not in USES or not isinstance(n, int) or isinstance(n, bool) or n < 0:
                die(f"{path}: account_caps.{site}.{use} must be a known use with a whole number")


def site_key(site):
    s = site.strip().lower()
    if not s or any(c.isspace() for c in s):
        die(f"site '{site}' must be one word, as in profile.json accounts (e.g. linkedin, jobify360)")
    return s


def used_today(site, use):
    if not LOG.exists():
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    n = 0
    for line in LOG.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].startswith(today) and cells[1] == site and cells[2] == use:
            n += 1
    return n


def decide(profile, site, use):
    """(allowed, message)"""
    site = site_key(site)
    if use not in USES:
        die(f"use '{use}' unknown; one of {', '.join(USES)}")
    perms = profile["accounts"].get(site)
    if perms is None:
        return False, (f"DENIED {site} {use}: the owner has not given permission for {site} at all. "
                       f"Ask them (ONBOARDING.md step 7), record the answer in profile.json accounts")
    if not perms.get(use, False):
        return False, (f"DENIED {site} {use}: the owner said no (or was not asked). Give them a checklist "
                       f"to do it themselves, or ask whether they want to change that answer")
    cap = profile["account_caps"].get(site, {}).get(use, DEFAULT_CAPS[use])
    n = used_today(site, use)
    if n >= cap:
        return False, (f"DENIED {site} {use}: today's limit of {cap} is reached ({n} done). "
                       f"Continue tomorrow; a burst is what gets accounts restricted")
    return True, f"ALLOWED {site} {use} ({n + 1} of {cap} today)"


def main():
    from validate import load_profile
    argv = sys.argv[1:]
    prof_path = None
    if "--profile" in argv:
        i = argv.index("--profile")
        if i + 1 >= len(argv):
            die("--profile needs a path")
        prof_path = argv[i + 1]
        del argv[i:i + 2]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    profile = load_profile(prof_path)
    cmd = argv[0]
    if cmd == "check" and len(argv) == 3:
        ok, msg = decide(profile, argv[1], argv[2])
        print(msg)
        if not ok:
            sys.exit(3)
    elif cmd == "record" and len(argv) == 4:
        what = argv[3].replace("|", "/").replace("\n", " ").strip()
        if not what:
            die("record needs a short description of the action, e.g. \"opened Dana Levi's profile\"")
        ok, msg = decide(profile, argv[1], argv[2])
        print(msg)
        if not ok:
            sys.exit(3)
        LOG.parent.mkdir(exist_ok=True)
        if not LOG.exists():
            LOG.write_text(HEADER, encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {site_key(argv[1])} | {argv[2]} | {what} |\n")
    elif cmd == "status" and len(argv) == 1:
        if not profile["accounts"]:
            print("no account permissions recorded: every use in every account is DENIED")
        for site, perms in profile["accounts"].items():
            row = []
            for use in USES:
                cap = profile["account_caps"].get(site, {}).get(use, DEFAULT_CAPS[use])
                row.append(f"{use}={'yes' if perms.get(use) else 'no'}" +
                           (f" {used_today(site, use)}/{cap}" if perms.get(use) else ""))
            print(f"{site:12} " + "  ".join(row))
    else:
        die(__doc__)


if __name__ == "__main__":
    run(main)
