#!/usr/bin/env python3
"""The watchlist: the job boards read again on every run, showing only the postings not seen
before. Stdlib only; reads boards through jobs.py.

Usage:
  watch.py run [--force]   read every watched board; print and save the new postings
  watch.py status          the last run, and the postings found that no triage file has used yet

The watchlist lives in profile/profile.json -> "watch", written at onboarding step 9:
  "watch": {"boards": ["greenhouse:acme", {"board": "workday:acme.wd5/External", "search": "marketing"}],
            "title": "product marketing|PMM", "location": "tel aviv|israel|remote", "days": 30}
boards: board names as jobs.py detect / find print them; an object adds a server-side search
(Workday). title and location: patterns, as jobs.py list --title / --location take them (location
"" = anywhere). days: postings older than this are left out (default 30).

`run` keeps each posting that matches and has not been seen before, saves its full text in
outreach/jobs/ (the JD file triage.py checks quotes against), and prints them as a table. It
records what it saw in outreach/watch-state.json and appends the run to outreach/watch-<date>.md.
A board that does not answer is named and skipped; the rest are still read. A run less than 20
hours after the last one is skipped; --force reads anyway.

Exit 2 = hard-fail (an invalid watchlist or state file)."""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

import jobs
from _common import ROOT, NetError, die, run as run_script

OUT = ROOT / "outreach"
JOBS = OUT / "jobs"
STATE = OUT / "watch-state.json"
PROFILE = ROOT / "profile" / "profile.json"
PAUSE = 2  # seconds between boards
PER_BOARD = 40  # new postings saved per board per run; the rest come next run
MIN_GAP = timedelta(hours=20)  # about a day: a run this recent is skipped


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def load_watchlist():
    p = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    w = p["watch"]
    boards = []
    for b in w["boards"]:
        name, search = (b, "") if isinstance(b, str) else (b["board"], b.get("search", ""))
        ats, board = name.split(":", 1)
        boards.append((ats, board, search))
    return {"boards": boards, "title": w["title"], "location": w.get("location", ""), "days": w.get("days", 30)}


def load_state():
    if not STATE.exists():
        return {"seen": {}}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(state):
    OUT.mkdir(exist_ok=True)
    tmp = STATE.with_name(f".{STATE.name}.tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE)


def last_run(state):
    if not state.get("last_run"):
        return None
    return datetime.fromisoformat(state["last_run"])


def ago(gap):
    hours = int(gap.total_seconds() // 3600)
    return f"{hours} h" if hours < 48 else f"{hours // 24} days"


def run(now=None, force=False):
    now = now or _now()
    wl = load_watchlist()
    state = load_state()
    last = last_run(state)
    if last and now - last < MIN_GAP and not force:
        return [f"SKIP last run {ago(now - last)} ago; --force to read the boards anyway"]
    found, skipped, read = [], [], 0
    for n, (ats, board, search) in enumerate(wl["boards"]):
        key = f"{ats}:{board}"
        if n:
            time.sleep(PAUSE)  # one board at a time, a pause between: the boards are not ours to hammer
        try:
            js = jobs.read_board(ats, board, search)
        except NetError as e:
            skipped.append(f"SKIPPED {key}: {e}")
            continue
        read += 1
        seen = state["seen"].setdefault(key, {})
        new = [j for j in jobs.keep(js, wl["title"], wl["location"], wl["days"], today=now.date())
               if str(j["id"]) not in seen][:PER_BOARD]
        for j in new:
            if j.get("detail") and not j.get("text"):
                time.sleep(1)
            try:
                jobs.read_detail(j)
            except NetError as e:
                skipped.append(f"SKIPPED {j['url']}: {e}")
                continue
            p = jobs.save(j, JOBS)
            seen[str(j["id"])] = {"first_seen": now.date().isoformat(), "file": p.name}
            found.append((j, p.name))
    state["last_run"] = now.isoformat()
    save_state(state)
    boards_skipped = sum(1 for l in skipped if not l.startswith("SKIPPED http"))
    lines = [f"WATCH {len(found)} new job{'' if len(found) == 1 else 's'}: {read} board{'' if read == 1 else 's'} read"
             + (f", {boards_skipped} board{'' if boards_skipped == 1 else 's'} skipped" if boards_skipped else "")]
    lines += skipped
    for j, name in found:
        lines.append(f"| {j['posted'] or 'unknown'} | {j['company']} | {j['title']} | {j['location']} | {j['url']} | {name} |")
    return lines


def main():
    args = sys.argv[1:]
    if args in (["-h"], ["--help"]):
        print(__doc__)
    elif args[:1] == ["run"] and set(args[1:]) <= {"--force"} and len(args) <= 2:
        print("\n".join(run(force="--force" in args)))
    else:
        die(__doc__)


if __name__ == "__main__":
    run_script(main)
