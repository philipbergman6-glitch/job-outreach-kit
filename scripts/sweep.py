#!/usr/bin/env python3
"""The inbox-sweep window: whether to sweep the mailbox now, and from when. Stdlib only.

Usage:
  sweep.py begin [--force]   start a sweep
  sweep.py done              finish it: the start time becomes the last sweep

`begin` prints either one line:
  SKIP <reason>                    do not sweep; say the reason to the owner
or two:
  SWEEP after:<epoch> (since <local time>)
  QUERY after:<epoch> -in:sent -category:promotions -from:<sender> ...
The QUERY line is a Gmail search for what arrived since the last sweep, leaving out the owner's own
mail, promotions, and each sender in profile.json -> sweep.skip_senders (a list of addresses or
@domains: job alerts, newsletters). Another mailbox: search from the time on the SWEEP line.

A sweep less than 3 hours after the last one is skipped, and so is one while another started less
than 30 minutes ago; --force sweeps anyway. `begin` records its start time in
outreach/.sweep-started, so mail that lands during the sweep is caught by the next one; `done`
moves it into outreach/sweep-last.txt. sweep-last.txt holds an ISO-8601 time with its time zone (a
bare YYYY-MM-DD means local midnight that day); none yet means seven days back.

Hard-fails on an unreadable or future time in either file, `done` without `begin`, and a
skip_senders that is not a list of addresses or @domains."""
import json
import re
import sys
from pathlib import Path
from datetime import date, datetime, time, timedelta, timezone

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import ROOT, die, run

OUT = ROOT / "outreach"
LAST = OUT / "sweep-last.txt"
LOCK = OUT / ".sweep-started"
PROFILE = ROOT / "profile" / "profile.json"
MIN_GAP = timedelta(hours=3)       # a sweep this recent is skipped
LOCK_TTL = timedelta(minutes=30)   # a start marker younger than this = a sweep in progress
FIRST_LOOK_BACK = timedelta(days=7)
SENDER = re.compile(r"(?:[^@\s]+@|@)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(path):
    text = path.read_text(encoding="utf-8").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.combine(date.fromisoformat(text), time()).astimezone().astimezone(timezone.utc)
        t = datetime.fromisoformat(text)
    except ValueError:
        die(f"{path}: '{text}' is not a date or an ISO-8601 time. Fix it, or delete the file to look back "
            f"{FIRST_LOOK_BACK.days} days")
    if t.tzinfo is None:
        die(f"{path}: '{text}' has no timezone: write it as 2026-11-20T09:00:00+00:00")
    return t.astimezone(timezone.utc)


def skip_senders():
    """profile.json -> sweep.skip_senders as Gmail from: terms (an @domain loses its @)."""
    if not PROFILE.exists():
        die(f"{PROFILE} missing: finish onboarding first")
    try:
        prof = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        die(f"{PROFILE}: not valid JSON ({e})")
    got = (prof.get("sweep") or {}).get("skip_senders", []) if isinstance(prof.get("sweep", {}), dict) else None
    if not isinstance(got, list) or not all(isinstance(s, str) and SENDER.fullmatch(s.strip()) for s in got):
        die(f"{PROFILE}: sweep.skip_senders must be a list of addresses or @domains, such as "
            f'["alerts@jobs.example.com", "@news.example.org"]; it is {json.dumps(got)}')
    return [s.strip().lstrip("@") for s in got]


def begin(force=False, now=None):
    """The lines to print; writes the start marker only when it says SWEEP."""
    now = now or _now()
    skip = skip_senders()
    if LOCK.exists() and not force:
        started = _parse(LOCK)
        if timedelta(0) <= now - started < LOCK_TTL:
            return [f"SKIP another sweep started {int((now - started).total_seconds() // 60)} min ago "
                    f"(outreach/.sweep-started); --force to sweep anyway"]
    last = _parse(LAST) if LAST.exists() else now - FIRST_LOOK_BACK
    if last > now:
        die(f"{LAST}: the last sweep, {last.isoformat()}, is in the future. Fix the file or delete it")
    if now - last < MIN_GAP and not force:
        return [f"SKIP last sweep {int((now - last).total_seconds() // 60)} min ago; --force to sweep anyway"]
    OUT.mkdir(exist_ok=True)
    LOCK.write_text(now.isoformat() + "\n", encoding="utf-8")
    epoch = int(last.timestamp())
    query = " ".join([f"after:{epoch}", "-in:sent", "-category:promotions"] + [f"-from:{s}" for s in skip])
    return [f"SWEEP after:{epoch} (since {last.astimezone():%Y-%m-%d %H:%M %Z})", f"QUERY {query}"]


def done():
    if not LOCK.exists():
        die("no sweep in progress (outreach/.sweep-started missing): run `sweep.py begin` first")
    started = _parse(LOCK)
    LAST.write_text(started.isoformat() + "\n", encoding="utf-8")
    LOCK.unlink()
    return f"DONE sweep-last.txt = {started.isoformat()}"


def main():
    args = sys.argv[1:]
    if args in (["-h"], ["--help"]):
        print(__doc__)
    elif args[:1] == ["begin"] and set(args[1:]) <= {"--force"} and len(args) <= 2:
        print("\n".join(begin("--force" in args)))
    elif args == ["done"]:
        print(done())
    else:
        die(__doc__)


if __name__ == "__main__":
    run(main)
