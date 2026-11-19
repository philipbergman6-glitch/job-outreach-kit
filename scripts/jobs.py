#!/usr/bin/env python3
"""Read live postings straight from company job boards (no login, no scraping of HTML). Stdlib only.

Usage:
  jobs.py detect <url>
        which job board a careers link belongs to, and its board name.
  jobs.py list <url | ats:board> [--title REGEX] [--location REGEX] [--days 30] [--search WORDS]
               [--save DIR] [--limit 40]
        every open posting on that board that matches, newest first, with posting date, place,
        salary and visa wording when the board publishes them. --save writes one file per kept
        posting (front matter + full text): the job-description file triage.py checks quotes
        against. --search is passed to boards that search server-side (Workday).

Boards: greenhouse, lever, ashby, smartrecruiters, workday, comeet. Any other careers page:
read it with the browser or a fetch, as flow/find-jobs.md says.
Board names look like: greenhouse:gongio  lever:palantir  ashby:linear
smartrecruiters:BoschGroup  workday:nvidia.wd5/NVIDIAExternalCareerSite  comeet:guardio/57.000
Comeet gives no posting date: its "posted" is the date the posting was last updated, and a
saved Comeet posting carries apply_email, the address Comeet accepts a CV at.
Exit 2 = hard-fail (bad input, or the board did not answer)."""
import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

from _common import NetError, die, http, run

ATS = ("greenhouse", "lever", "ashby", "smartrecruiters", "workday", "comeet")
REMOTE = {True: "yes", False: "no", None: "unknown"}
NO_SPONSOR = re.compile(r"(unable|not able|cannot|can't|do not|don't|won't|will not|no)\s+(to\s+)?"
                        r"(offer\s+|provide\s+)?(visa\s+)?sponsor", re.I)
SPONSOR = re.compile(r"visa|sponsor|relocation package|work permit|blue card", re.I)


def detect(url):
    u = url.strip()
    pats = [
        ("greenhouse", r"greenhouse\.io/embed/job_board\?for=([\w-]+)"),
        ("greenhouse", r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)"),
        ("lever", r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)"),
        ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)"),
        ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)"),
    ]
    for ats, rx in pats:
        m = re.search(rx, u)
        if m and m.group(1) not in ("embed",):
            return ats, m.group(1)
    m = re.search(r"comeet\.com?/jobs/([\w-]+)/([0-9A-F]{2}\.[0-9A-F]{3})\b", u)
    if m:
        return "comeet", f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", u)
    if m:
        return "workday", f"{m.group(1)}.{m.group(2)}/{m.group(3)}"
    return None, None


def text_of(html):
    t = unescape(html or "")
    t = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", t)
    t = re.sub(r"(?i)<\s*(br|/p|/div|/h\d|/ul|/ol|/li)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return "\n".join(line.strip() for line in t.splitlines()).strip()


def sponsorship(text):
    if NO_SPONSOR.search(text):
        return "no"
    return "mentioned" if SPONSOR.search(text) else ""


def _iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _job(**k):
    if k.get("remote") is None and re.search(r"\bremote\b", k.get("location", ""), re.I):
        k["remote"] = True
    k.setdefault("remote", None)
    k.setdefault("salary", "")
    k.setdefault("poster", "")
    k["sponsorship"] = sponsorship(k.get("text", ""))
    return k


def from_greenhouse(x, board):
    return _job(ats="greenhouse", board=board, id=str(x["id"]), title=x["title"].strip(),
                company=x.get("company_name") or board, location=(x.get("location") or {}).get("name", ""),
                posted=_iso(x.get("first_published")) or _iso(x.get("updated_at")),
                url=x["absolute_url"], text=text_of(x.get("content", "")))


def from_lever(x, board):
    parts = [x.get("descriptionPlain") or text_of(x.get("description", ""))]
    for lst in x.get("lists") or []:
        parts.append(lst.get("text", "") + "\n" + text_of(lst.get("content", "")))
    parts.append(x.get("additionalPlain") or text_of(x.get("additional", "")))
    sal = x.get("salaryRange") or {}
    salary = ""
    if sal.get("min") is not None or sal.get("max") is not None:
        per = (sal.get("interval") or "").replace("-salary", "").replace("-", " ")
        lo, hi = (f"{n:,}" if isinstance(n, (int, float)) else "?" for n in (sal.get("min"), sal.get("max")))
        salary = f"{lo}–{hi} {sal.get('currency') or ''} {per}".replace("  ", " ").strip()
    cat = x.get("categories") or {}
    return _job(ats="lever", board=board, id=x["id"], title=x["text"].strip(), company=board,
                location=cat.get("location", ""), remote=(x.get("workplaceType") == "remote") or None,
                posted=datetime.fromtimestamp(x["createdAt"] / 1000, timezone.utc).date() if x.get("createdAt") else None,
                url=x["hostedUrl"], salary=salary, text="\n\n".join(p for p in parts if p).strip())


def from_ashby(x, board):
    comp = (x.get("compensation") or {}).get("compensationTierSummary") or ""
    return _job(ats="ashby", board=board, id=x["id"], title=x["title"].strip(), company=board,
                location=x.get("location", ""), remote=bool(x.get("isRemote")),
                posted=_iso(x.get("publishedAt")), url=x["jobUrl"], salary=comp,
                text=x.get("descriptionPlain") or text_of(x.get("descriptionHtml", "")))


COMEET_BOARD = re.compile(r"([\w-]+)/([0-9A-F]{2}\.[0-9A-F]{3})")
WORKPLACE = {"remote": True, "on-site": False, "onsite": False, "hybrid": False}


def comeet_token(page, uid):
    """The positions-API token printed next to this company's uid in its public job-list page."""
    m = re.search(r'"company_uid":\s*"' + re.escape(uid) + r'"[^{}]{0,400}?"token":\s*"([0-9A-F]{16,})"', page)
    return m.group(1) if m else None


def from_comeet(x, board):
    wp = (x.get("workplace_type") or "").strip()
    loc = ((x.get("location") or {}).get("name") or "").strip()
    text = "\n\n".join(f"{d.get('name', '')}\n{text_of(d['value'])}" for d in
                        sorted(x.get("details") or [], key=lambda d: d.get("order") or 0) if d.get("value"))
    return _job(ats="comeet", board=board, id=x["uid"], title=x["name"].strip(),
                company=x.get("company_name") or board.split("/")[0],
                location=f"{loc} ({wp})" if loc and wp else loc or wp,
                remote=WORKPLACE.get(wp.lower()), posted=_iso(x.get("time_updated")),
                url=x["url_comeet_hosted_page"], text=text, apply_email=x.get("email") or "")


def workday_posted(s, today=None):
    today = today or date.today()
    s = (s or "").lower()
    if "today" in s:
        return today
    if "yesterday" in s:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)(\+?)\s+days?", s)
    if m:
        return today - timedelta(days=int(m.group(1)) + (1 if m.group(2) else 0))
    return None


def fetch(ats, board, search=""):
    """Every open posting on the board, normalised. Workday and SmartRecruiters list without
    the full text; detail() fills it in for the ones kept."""
    try:
        if ats == "greenhouse":
            d = http(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true", pinned=True)
            return [from_greenhouse(x, board) for x in d.get("jobs", [])]
        if ats == "lever":
            d = http(f"https://api.lever.co/v0/postings/{board}?mode=json", pinned=True)
            return [from_lever(x, board) for x in d]
        if ats == "ashby":
            d = http(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true", pinned=True)
            return [from_ashby(x, board) for x in d.get("jobs", []) if x.get("isListed", True)]
        if ats == "smartrecruiters":
            out, offset = [], 0
            while offset < 300:
                d = http(f"https://api.smartrecruiters.com/v1/companies/{board}/postings?limit=100&offset={offset}",
                         pinned=True)
                for x in d.get("content", []):
                    loc = x.get("location") or {}
                    out.append(_job(ats=ats, board=board, id=x["id"], title=x["name"].strip(),
                                    company=(x.get("company") or {}).get("name", board),
                                    location=", ".join(v for v in (loc.get("city"), (loc.get("country") or "").upper()) if v),
                                    remote=loc.get("remote"), posted=_iso(x.get("releasedDate")),
                                    url=f"https://jobs.smartrecruiters.com/{board}/{x['id']}",
                                    poster=(x.get("creator") or {}).get("name", ""), text="", detail=x["ref"]))
                offset += 100
                if offset >= d.get("totalFound", 0):
                    break
            return out
        if ats == "comeet":
            m = COMEET_BOARD.fullmatch(board)
            if not m:
                die(f"comeet board '{board}' must look like <slug>/<uid>, e.g. guardio/57.000 "
                    f"(jobs.py detect <a comeet.com/jobs link>)")
            uid = m.group(2)
            page = http(f"https://www.comeet.com/jobs/{board}", as_json=False, pinned=True)
            tok = comeet_token(page, uid)
            if not tok:
                die(f"the Comeet page for {board} shows no positions token for company {uid}: "
                    f"open https://www.comeet.com/jobs/{board} with the browser instead")
            d = http(f"https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={tok}&details=true",
                     pinned=True)
            if not isinstance(d, list):
                die(f"comeet board '{board}' answered with something other than a list of positions: "
                    f"{str(d)[:120]}")
            return [from_comeet(x, board) for x in d if isinstance(x, dict) and (x.get("name") or "").strip()
                    and x.get("uid") and str(x.get("url_comeet_hosted_page", "")).startswith("https://")]
        if ats == "workday":
            host, site = board.split("/", 1)
            tenant = host.split(".")[0]
            base = f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
            out = []
            for offset in range(0, 100, 20):
                d = http(base + "/jobs", method="POST", pinned=True,
                         body={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": search})
                for x in d.get("jobPostings", []):
                    out.append(_job(ats=ats, board=board, id=x["externalPath"].rsplit("/", 1)[-1],
                                    title=x["title"].strip(), company=tenant, location=x.get("locationsText", ""),
                                    posted=workday_posted(x.get("postedOn")),
                                    url=f"https://{host}.myworkdayjobs.com/{site}{x['externalPath']}",
                                    text="", detail=base + x["externalPath"]))
                if offset + 20 >= d.get("total", 0):
                    break
                time.sleep(1)  # Workday rate-limits bursts
            return out
    except NetError as e:
        die(f"{ats} board '{board}' did not answer: {e}. Check the board name with jobs.py detect <link>")
    die(f"unknown board type '{ats}'; one of {', '.join(ATS)}")


def detail_home(j):
    """Where a board's detail URLs must point: its own API host."""
    if j["ats"] == "workday":
        return f"https://{j['board'].split('/')[0]}.myworkdayjobs.com/"
    return "https://api.smartrecruiters.com/"


def detail(j):
    """Fill in the full text for boards that list without it."""
    if j.get("text") or not j.get("detail"):
        return j
    if not j["detail"].startswith(detail_home(j)):
        die(f"{j['url']}: the board pointed its details at {j['detail'].split('?')[0]}, off its own host; refused")
    try:
        d = http(j["detail"], pinned=True)
    except NetError as e:
        die(f"could not read {j['url']}: {e}")
    if j["ats"] == "workday":
        time.sleep(1)
    if j["ats"] == "smartrecruiters":
        secs = (d.get("jobAd") or {}).get("sections") or {}
        j["text"] = "\n\n".join(text_of((secs.get(k) or {}).get("text", "")) for k in
                                ("jobDescription", "qualifications", "additionalInformation", "companyDescription")).strip()
        j["url"] = d.get("postingUrl") or j["url"]
    elif j["ats"] == "workday":
        info = d.get("jobPostingInfo") or {}
        j["text"] = text_of(info.get("jobDescription", ""))
        j["url"] = info.get("externalUrl") or j["url"]
        j["remote"] = "remote" in (info.get("location", "") + str(info.get("additionalLocations", ""))).lower() or None
    j["sponsorship"] = sponsorship(j["text"])
    return j


def keep(js, title, location, days, today=None):
    today = today or date.today()
    try:
        t, loc = re.compile(title or "", re.I), re.compile(location or "", re.I)
    except re.error as e:
        die(f"--title / --location is not a valid pattern: {e}")
    out = []
    for j in js:
        if not t.search(j["title"]):
            continue
        place = j["location"] + (" remote" if j.get("remote") else "")
        if not loc.search(place):
            continue
        if j["posted"] and (today - j["posted"]).days > days:
            continue
        out.append(j)
    return sorted(out, key=lambda j: j["posted"] or date.min, reverse=True)


def save(j, folder):
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{j['company']}-{j['id']}".lower()).strip("-")[:80]
    p = folder / f"{slug}.md"
    meta = {"url": j["url"], "company": j["company"], "title": j["title"], "location": j["location"],
            "remote": REMOTE[j.get("remote")],
            "posted": j["posted"].isoformat() if j["posted"] else "unknown", "salary": j["salary"] or "not stated",
            "sponsorship": j["sponsorship"] or "not stated", "posted_by": j.get("poster") or "not stated",
            "fetched": date.today().isoformat()}
    if j.get("apply_email"):
        meta["apply_email"] = j["apply_email"]
    p.write_text("---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n\n" + j["text"] + "\n",
                 encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("url")
    li = sub.add_parser("list")
    li.add_argument("board")
    li.add_argument("--title", default="")
    li.add_argument("--location", default="")
    li.add_argument("--days", type=int, default=30)
    li.add_argument("--search", default="")
    li.add_argument("--save")
    li.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(sys.argv[1:])

    if a.cmd == "detect":
        ats, board = detect(a.url)
        print(f"{ats}:{board}" if ats else "unknown board: read the careers page with the browser or a fetch")
        return
    if ":" in a.board and not a.board.startswith("http"):
        ats, board = a.board.split(":", 1)
    else:
        ats, board = detect(a.board)
        if not ats:
            die(f"'{a.board}' is not a link to a known job board ({', '.join(ATS)})")
    allj = fetch(ats, board, a.search)
    kept = keep(allj, a.title, a.location, a.days)[:a.limit]
    print(f"{ats}:{board}  {len(allj)} open, {len(kept)} match (title /{a.title}/, place /{a.location}/, "
          f"last {a.days} days)")
    if kept:
        print("| Posted | Title | Location | Remote | Salary | Visa | Link |")
        print("|---|---|---|---|---|---|---|")
    if a.save:
        for j in kept:  # every full text first: a failure here leaves no half-saved set behind
            detail(j)
        paths = {id(j): save(j, Path(a.save)) for j in kept}
    for j in kept:
        print(f"| {j['posted'] or 'unknown'} | {j['title']} | {j['location']} | {REMOTE[j.get('remote')]} | "
              f"{j['salary'] or '-'} | {j['sponsorship'] or '-'} | {j['url']} |"
              + (f" {paths[id(j)].name}" if a.save else ""))


if __name__ == "__main__":
    run(main)
