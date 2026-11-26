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


KEYS = {"boards", "title", "location", "days"}
BOARD_KEYS = {"board", "search"}
NO_WATCHLIST = ("SKIP no watchlist yet: profile.json -> watch lists the boards to read on every run "
                "(ONBOARDING.md step 9)")


def check_watch(path, p):
    """profile.json -> watch as {"boards": [(ats, board, search)], "title", "location", "days"}, or
    None when the owner has no watchlist yet. Anything malformed hard-fails, naming it. Called by
    validate.load_profile too, so --check-profile catches a bad watchlist at onboarding."""
    w = p.get("watch")
    if w is None:
        return None
    if not isinstance(w, dict):
        die(f'{path}: \'watch\' must be an object: {{"boards": [...], "title": ..., "location": ..., "days": 30}}')
    if set(w) - KEYS:
        die(f"{path}: unknown watch key(s) {sorted(set(w) - KEYS)}; allowed: {sorted(KEYS)}")
    if not isinstance(w.get("boards"), list) or not w["boards"]:
        die(f'{path}: watch.boards must be a non-empty list of board names such as "greenhouse:acme" '
            f'(jobs.py find "<company>" prints them)')
    boards = []
    for b in w["boards"]:
        if isinstance(b, dict):
            if set(b) - BOARD_KEYS or "board" not in b:
                die(f'{path}: watch.boards entry {json.dumps(b)}: an object needs "board" and may have '
                    f'"search"; unknown key(s) {sorted(set(b) - BOARD_KEYS)}')
            name, search = b["board"], b.get("search", "")
        else:
            name, search = b, ""
        if not isinstance(name, str) or ":" not in name or name.strip().startswith("http"):
            die(f"{path}: watch.boards: {json.dumps(name).replace(chr(34), chr(39))} is not a board name; write "
                f"it as jobs.py detect prints it, such as greenhouse:acme")
        if not isinstance(search, str):
            die(f"{path}: watch.boards: the search for {name} must be text")
        ats, board = name.strip().split(":", 1)
        problem = jobs.board_problem(ats, board)
        if problem:
            die(f"{path}: watch.boards: {problem}")
        if any((ats, board) == (a, bd) for a, bd, _ in boards):
            die(f"{path}: watch.boards: {name} is listed twice")
        boards.append((ats, board, search.strip()))
    for key, required in (("title", True), ("location", False)):
        v = w.get(key, "")
        if not isinstance(v, str) or (required and not v.strip()):
            die(f'{path}: watch.{key} must be a pattern of words, such as "product marketing|PMM"'
                + ("" if required else '; "" for anywhere'))
        try:
            re.compile(v)
        except re.error as e:
            die(f"{path}: watch.{key} is not a valid pattern ({e}): '{v}'")
    days = w.get("days", 30)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        die(f"{path}: watch.days must be a whole number of days from 1 to 365, such as 30; it is {json.dumps(days)}")
    return {"boards": boards, "title": w["title"], "location": w.get("location", ""), "days": days}


def load_watchlist():
    if not PROFILE.exists():
        die(f"{PROFILE} missing: finish onboarding first")
    try:
        p = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        die(f"{PROFILE}: not valid JSON ({e})")
    if not isinstance(p, dict):
        die(f"{PROFILE}: must be a JSON object")
    return check_watch(PROFILE, p)


def load_state():
    if not STATE.exists():
        return {"seen": {}}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"{STATE}: not valid JSON ({e}). It only remembers which postings were already shown: "
            f"delete it and the next run shows every matching posting again")
    if not isinstance(state, dict) or not isinstance(state.get("seen"), dict):
        die(f"{STATE}: not a watch state file (no 'seen' table). Delete it and the next run shows every "
            f"matching posting again")
    return state


def save_state(state):
    OUT.mkdir(exist_ok=True)
    tmp = STATE.with_name(f".{STATE.name}.tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE)


def last_run(state):
    if not state.get("last_run"):
        return None
    try:
        t = datetime.fromisoformat(str(state["last_run"]))
    except ValueError:
        t = None
    if t is None or t.tzinfo is None:
        die(f"{STATE}: last_run '{state['last_run']}' is not a time with its time zone. Delete the file and "
            f"the next run shows every matching posting again")
    return t


def ago(gap):
    hours = int(gap.total_seconds() // 3600)
    return f"{hours} h" if hours < 48 else f"{hours // 24} days"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def row(cells):
    return "| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |"


HEAD = ["| Posted | Company | Title | Location | Link | JD file |", "|---|---|---|---|---|---|"]


def run(now=None, force=False):
    """Read every watched board; save and list the postings not seen before. Returns the lines to print."""
    now = now or _now()
    wl = load_watchlist()
    if wl is None:
        return [NO_WATCHLIST]
    state = load_state()
    last = last_run(state)
    if last and now - last < MIN_GAP and not force:
        return [f"SKIP last run {ago(now - last)} ago; --force to read the boards anyway"]
    today = now.astimezone().date()
    found, bad_boards, bad_posts = [], [], []
    for n, (ats, board, search) in enumerate(wl["boards"]):
        key = f"{ats}:{board}"
        if n:
            time.sleep(PAUSE)  # one board at a time, a pause between: the boards are not ours to hammer
        try:
            js = jobs.read_board(ats, board, search)
        except NetError as e:
            bad_boards.append((key, e))
            continue
        seen = state["seen"].setdefault(key, {})
        new = [j for j in jobs.keep(js, wl["title"], wl["location"], wl["days"], today=today)
               if str(j["id"]) not in seen][:PER_BOARD]
        for j in new:
            if j.get("detail") and not j.get("text"):
                time.sleep(1)
            try:
                jobs.read_detail(j)
            except NetError as e:  # not marked seen: the next run tries it again
                bad_posts.append(f"SKIPPED {j['url']}: {e}")
                continue
            name = jobs.save(j, JOBS).name
            seen[str(j["id"])] = {"first_seen": today.isoformat(), "file": name, "company": j["company"],
                                  "title": j["title"], "url": j["url"]}
            found.append(row([j["posted"] or "unknown", j["company"], j["title"], j["location"], j["url"], name]))
    read = len(wl["boards"]) - len(bad_boards)
    summary = f"WATCH {plural(len(found), 'new job')}: {plural(read, 'board')} read" + \
              (f", {plural(len(bad_boards), 'board')} skipped" if bad_boards else "")
    lines = [summary] + [f"SKIPPED {k}: {e}" for k, e in bad_boards] + bad_posts + (HEAD + found if found else [])
    report = OUT / f"watch-{today.isoformat()}.md"
    with report.open("a", encoding="utf-8") as f:
        f.write(f"## Run {now.astimezone():%H:%M}\n\n" + "\n".join(lines) + "\n\n")
    state["last_run"] = now.isoformat()
    state["last"] = {"new": len(found), "read": read, "skipped": [k for k, _ in bad_boards]}
    save_state(state)
    return lines + [f"SAVED {report.relative_to(ROOT)}"]


def decided():
    """Text of every file that settles a posting: the triage files, passed.md, log.md."""
    files = sorted(OUT.glob("triage-*.md")) + [OUT / "passed.md", OUT / "log.md"]
    return "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files if f.is_file())


def waiting(state):
    """The postings watch found that no triage file, pass or application has used yet."""
    done = decided()
    out = []
    for board in state["seen"].values():
        for e in (board.values() if isinstance(board, dict) else []):
            if not (isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("file", "url", "first_seen"))):
                continue  # an entry from a hand edit: still counts as seen, never listed
            if (JOBS / e["file"]).is_file() and e["file"] not in done and e["url"] not in done:
                out.append(e)
    return sorted(out, key=lambda e: e["first_seen"], reverse=True)


def status(now=None):
    now = now or _now()
    if load_watchlist() is None:
        return [NO_WATCHLIST]
    state = load_state()
    last = last_run(state)
    if not last:
        return ["WATCH no run yet: python3 scripts/watch.py run"]
    info = state.get("last", {})
    lines = [f"WATCH last run {ago(now - last)} ago ({last.astimezone():%Y-%m-%d %H:%M}): "
             f"{plural(info.get('read', 0), 'board')} read, {info.get('new', 0)} new"
             + (f", skipped {', '.join(info['skipped'])}" if info.get("skipped") else "")]
    w = waiting(state)
    lines.append(f"{len(w)} waiting to be scored (found by watch, in no triage file, passed.md or log.md yet)")
    if w:
        lines += ["| First seen | Company | Title | Link | JD file |", "|---|---|---|---|---|"]
        lines += [row([e["first_seen"], e["company"], e["title"], e["url"], e["file"]]) for e in w]
    return lines


def main():
    args = sys.argv[1:]
    if args in (["-h"], ["--help"]):
        print(__doc__)
    elif args[:1] == ["run"] and set(args[1:]) <= {"--force"} and len(args) <= 2:
        print("\n".join(run(force="--force" in args)))
    elif args == ["status"]:
        print("\n".join(status()))
    else:
        die(__doc__)


if __name__ == "__main__":
    run_script(main)
