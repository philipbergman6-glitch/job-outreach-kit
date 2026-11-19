#!/usr/bin/env python3
"""Read live postings straight from company job boards: their public APIs, no login. Stdlib only.

Usage:
  jobs.py detect <url>
        which job board a careers link belongs to, and its board name.
  jobs.py list <url | ats:board> [--title REGEX] [--location REGEX] [--days 30] [--search WORDS]
               [--save DIR] [--limit 40]
        every open posting on that board that matches, newest first, with posting date, place,
        salary and visa wording when the board publishes them. --save writes one file per kept
        posting (front matter + full text): the job-description file triage.py checks quotes
        against. --search is passed to boards that search server-side (Workday).

Boards: greenhouse, lever, ashby, smartrecruiters, workday, comeet, workable, recruitee, breezy,
personio (jobs.personio.de), rippling. Any other careers page: read it with the browser or a
fetch, as flow/find-jobs.md says. Comeet's token, and Breezy's and Rippling's job text, come
from the board's own public page; Rippling lists no dates, so its dates come with --save.
Board names look like: greenhouse:gongio  lever:palantir  ashby:linear
smartrecruiters:BoschGroup  workday:nvidia.wd5/NVIDIAExternalCareerSite  comeet:guardio/57.000
workable:amer-sports  recruitee:auditdata  breezy:atlas-rfid  personio:anyline-gmbh
rippling:duplocloud
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

ATS = ("greenhouse", "lever", "ashby", "smartrecruiters", "workday", "comeet", "workable", "recruitee", "breezy",
       "personio", "rippling")
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
PAGE_TEXT = ("breezy", "rippling")  # boards that list without the text; detail() reads the job page
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
    one_word = [
        ("workable", r"apply\.workable\.com/(?!api/|j/)([\w-]+)"),
        ("recruitee", r"https?://([\w-]+)\.recruitee\.com"),
        ("breezy", r"https?://([\w-]+)\.breezy\.hr"),
        ("personio", r"https?://([\w-]+)\.jobs\.personio\.de"),
        ("rippling", r"ats\.rippling\.com/(?!api/)([\w-]+)"),
    ]
    for ats, rx in one_word:
        m = re.search(rx, u)
        if m:
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


def pay_range(lo, hi, currency, per):
    if lo is None and hi is None:
        return ""
    lo, hi = (f"{n:,}" if isinstance(n, (int, float)) else "?" for n in (lo, hi))
    return f"{lo}–{hi} {currency or ''} {per or ''}".replace("  ", " ").strip()


def from_lever(x, board):
    parts = [x.get("descriptionPlain") or text_of(x.get("description", ""))]
    for lst in x.get("lists") or []:
        parts.append(lst.get("text", "") + "\n" + text_of(lst.get("content", "")))
    parts.append(x.get("additionalPlain") or text_of(x.get("additional", "")))
    sal = x.get("salaryRange") or {}
    salary = pay_range(sal.get("min"), sal.get("max"), sal.get("currency"),
                       (sal.get("interval") or "").replace("-salary", "").replace("-", " "))
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


def from_workable(x, board):
    place = ", ".join(v for v in (x.get("city"), x.get("state"), x.get("country")) if v)
    return _job(ats="workable", board=board, id=x["shortcode"], title=x["title"].strip(), company=board,
                location=place, remote=str(x.get("telecommuting")).lower() == "true",
                posted=_iso(x.get("published_on") or x.get("created_at")),
                url=f"https://apply.workable.com/{board}/j/{x['shortcode']}/", text=text_of(x.get("description", "")))


def from_recruitee(x, board):
    sal = x.get("salary") or {}
    place = x.get("location") or ", ".join(v for v in (x.get("city"), x.get("country")) if v)
    return _job(ats="recruitee", board=board, id=str(x["id"]), title=x["title"].strip(),
                company=x.get("company_name") or board, location=place,
                remote=True if x.get("remote") else (False if x.get("on_site") or x.get("hybrid") else None),
                posted=_iso((x.get("published_at") or "").replace(" UTC", "+00:00")),
                url=x["careers_url"], salary=pay_range(sal.get("min"), sal.get("max"), sal.get("currency"),
                                                       f"per {sal['period']}" if sal.get("period") else ""),
                text="\n\n".join(text_of(x.get(k) or "") for k in ("description", "requirements")).strip())


def from_breezy(x, board):
    loc = x.get("location") or {}
    return _job(ats="breezy", board=board, id=x["id"], title=x["name"].strip(),
                company=(x.get("company") or {}).get("name") or board, location=loc.get("name", ""),
                remote=loc.get("is_remote"), posted=_iso(x.get("published_date")), url=x["url"],
                salary=x.get("salary") or "", text="", detail=x["url"])


def from_personio(pos, board):
    """One <position> element of a Personio XML feed."""
    get = lambda tag: (pos.findtext(tag) or "").strip()
    parts = [f"{d.findtext('name') or ''}\n{text_of(d.findtext('value') or '')}".strip()
             for d in pos.iter("jobDescription")]
    return _job(ats="personio", board=board, id=get("id"), title=get("name"), company=get("subcompany") or board,
                location=get("office"), posted=_iso(get("createdAt")),
                url=f"https://{board}.jobs.personio.de/job/{get('id')}", text="\n\n".join(p for p in parts if p))


def from_rippling(x, board):
    places = [l.get("name", "") for l in x.get("locations") or [] if isinstance(l, dict)]
    return _job(ats="rippling", board=board, id=x["id"], title=x["name"].strip(), company=board,
                location="; ".join(p for p in places if p), posted=None, url=x["url"], text="", detail=x["url"])


def page_json(html, pattern, want=lambda d: True):
    """The JSON inside the first <script> whose opening tag matches pattern and whose content
    passes want(), or None."""
    import json
    for m in re.finditer(r"<script[^>]*" + pattern + r"[^>]*>(.*?)</script>", html, re.S | re.I):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if want(d):
            return d
    return None


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


def rows(d, key, ats, board):
    """The list of postings in a board's reply; anything else means the API changed or failed."""
    got = (d.get(key) if isinstance(d, dict) else None) if key else d
    if not isinstance(got, list):
        die(f"{ats} board '{board}' answered with something other than its list of jobs: {str(d)[:120]}")
    return [x for x in got if isinstance(x, dict)]


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
        if ats in ("workable", "recruitee", "breezy", "personio", "rippling") and not SLUG.fullmatch(board):
            die(f"{ats} board '{board}' must be one word of letters, digits and dashes (jobs.py detect <link>)")
        if ats == "workable":
            d = http(f"https://apply.workable.com/api/v1/widget/accounts/{board}?details=true", pinned=True)
            return [from_workable(x, board) for x in rows(d, "jobs", ats, board) if x.get("title") and x.get("shortcode")]
        if ats == "recruitee":
            d = http(f"https://{board}.recruitee.com/api/offers/", pinned=True)
            return [from_recruitee(x, board) for x in rows(d, "offers", ats, board)
                    if x.get("title") and x.get("id") and str(x.get("careers_url", "")).startswith("https://")
                    and x.get("status", "published") == "published"]
        if ats == "breezy":
            d = http(f"https://{board}.breezy.hr/json", pinned=True)
            return [from_breezy(x, board) for x in rows(d, None, ats, board) if x.get("name") and x.get("id")
                    and str(x.get("url", "")).startswith(f"https://{board}.breezy.hr/")]
        if ats == "personio":
            import xml.etree.ElementTree as ET
            raw = http(f"https://{board}.jobs.personio.de/xml", as_json=False, pinned=True)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as e:
                die(f"personio board '{board}' did not answer with its XML feed ({e}): {raw[:120]}")
            return [from_personio(p, board) for p in root.iter("position")
                    if (p.findtext("id") or "").strip().isdigit() and (p.findtext("name") or "").strip()]
        if ats == "rippling":
            out = []
            for page in range(10):
                d = http(f"https://ats.rippling.com/api/v2/board/{board}/jobs?page={page}&pageSize=50", pinned=True)
                out += [from_rippling(x, board) for x in rows(d, "items", ats, board) if x.get("name") and x.get("id")
                        and str(x.get("url", "")).startswith(f"https://ats.rippling.com/{board}/")]
                if page + 1 >= (d.get("totalPages") or 0):
                    break
            return out
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
    """Where a board's detail URLs must point: its own host."""
    return {"workday": f"https://{j['board'].split('/')[0]}.myworkdayjobs.com/",
            "breezy": f"https://{j['board']}.breezy.hr/",
            "rippling": f"https://ats.rippling.com/{j['board']}/"}.get(j["ats"], "https://api.smartrecruiters.com/")


def detail(j):
    """Fill in the full text for boards that list without it."""
    if j.get("text") or not j.get("detail"):
        return j
    if not j["detail"].startswith(detail_home(j)):
        die(f"{j['url']}: the board pointed its details at {j['detail'].split('?')[0]}, off its own host; refused")
    try:
        d = http(j["detail"], pinned=True, as_json=j["ats"] not in PAGE_TEXT)
    except NetError as e:
        die(f"could not read {j['url']}: {e}")
    if j["ats"] == "workday":
        time.sleep(1)
    if j["ats"] == "smartrecruiters":
        secs = (d.get("jobAd") or {}).get("sections") or {}
        j["text"] = "\n\n".join(text_of((secs.get(k) or {}).get("text", "")) for k in
                                ("jobDescription", "qualifications", "additionalInformation", "companyDescription")).strip()
        j["url"] = d.get("postingUrl") or j["url"]
    elif j["ats"] == "breezy":
        ld = page_json(d, r"application/ld\+json", lambda x: isinstance(x, dict) and x.get("@type") == "JobPosting")
        j["text"] = text_of((ld or {}).get("description", ""))
    elif j["ats"] == "rippling":
        post = ((((page_json(d, r'id="__NEXT_DATA__"') or {}).get("props") or {}).get("pageProps") or {})
                .get("apiData") or {}).get("jobPost") or {}
        desc = post.get("description") or {}
        j["text"] = "\n\n".join(text_of(desc.get(k) or "") for k in ("role", "company") if desc.get(k)) \
            if isinstance(desc, dict) else text_of(str(desc))
        j["posted"] = _iso(post.get("createdOn")) or j["posted"]
    elif j["ats"] == "workday":
        info = d.get("jobPostingInfo") or {}
        j["text"] = text_of(info.get("jobDescription", ""))
        j["url"] = info.get("externalUrl") or j["url"]
        j["remote"] = "remote" in (info.get("location", "") + str(info.get("additionalLocations", ""))).lower() or None
    if j["ats"] in PAGE_TEXT and not j["text"]:
        die(f"could not find the job text on {j['url']}: read that page with the browser instead")
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
        cells = (j["posted"] or "unknown", j["title"], j["location"], REMOTE[j.get("remote")], j["salary"] or "-",
                 j["sponsorship"] or "-", j["url"])
        print("| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |"
              + (f" {paths[id(j)].name}" if a.save else ""))


if __name__ == "__main__":
    run(main)
