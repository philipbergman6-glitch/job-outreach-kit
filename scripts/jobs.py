#!/usr/bin/env python3
"""Read live postings straight from company job boards: their public APIs, no login. Stdlib only.

Usage:
  jobs.py detect <url>
        which job board a careers link belongs to, and its board name.
  jobs.py alive <posting url>
        open (exit 0), closed (exit 1) or unknown (exit 3), with the reason. Closed only on the
        board's own word; unknown means read the page.
  jobs.py find "<company>"
        the company's job board: from the employer registry in scripts/data (CC BY 4.0, see
        THIRD_PARTY_NOTICES.md), else by trying its name on each board. A guessed board is
        marked "verify": board names collide, so confirm the company's careers page links to it.
  jobs.py list <url | ats:board> [--title REGEX] [--location REGEX] [--days 30] [--search WORDS]
               [--save DIR] [--limit 40]
        every open posting on that board that matches, newest first, with posting date, place,
        salary and visa wording when the board publishes them. --save writes one file per kept
        posting (front matter + full text): the job-description file triage.py checks quotes
        against. --search is passed to boards that search server-side (Workday).

Boards: greenhouse, lever, ashby, smartrecruiters, workday, comeet, workable, recruitee, breezy,
personio (personio:<slug> on .de, personio:com/<slug> on .com), rippling. Any other careers page: read it with the browser or a
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
import hashlib
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:  # python3 -I leaves the script's own folder off the import path
    sys.path.insert(0, _HERE)

from _common import NetError, company_key, die, http, run

ATS = ("greenhouse", "lever", "ashby", "smartrecruiters", "workday", "comeet", "workable", "recruitee", "breezy",
       "personio", "rippling")
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
PAGE_TEXT = ("breezy", "rippling")  # boards that list without the text; detail() reads the job page
REMOTE = {True: "yes", False: "no", None: "unknown"}
NO_SPONSOR = re.compile(r"(unable|not able|cannot|can't|do not|don't|won't|will not|are not|is not|no)\s+(to\s+)?"
                        r"(offer\s+|provide\s+)?(visa\s+)?sponsor|"
                        r"sponsorship\s+(is|are)\s+(not|un)\s*available", re.I)
SPONSOR = re.compile(r"visa|sponsor|relocation package|work permit|blue card", re.I)


def detect(url):
    u = url.strip()
    pats = [
        ("greenhouse", r"greenhouse\.io/embed/job_board\?for=([\w-]+)"),
        ("greenhouse", r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)"),
        ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)"),
        ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)"),
    ]
    for ats, rx in pats:
        m = re.search(rx, u)
        if m and m.group(1) not in ("embed",):
            return ats, m.group(1)
    m = re.search(r"https?://([\w-]+)\.jobs\.personio\.(de|com)\b", u)
    if m:
        return "personio", ("com/" if m.group(2) == "com" else "") + m.group(1)
    m = re.search(r"jobs\.(eu\.)?lever\.co/([\w.-]+)", u)
    if m:
        return "lever", ("eu/" if m.group(1) else "") + m.group(2)
    one_word = [
        ("workable", r"apply\.workable\.com/(?!api/|j/)([\w-]+)"),
        ("recruitee", r"https?://([\w-]+)\.recruitee\.com"),
        ("breezy", r"https?://([\w-]+)\.breezy\.hr"),
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
    t = html or ""
    if "<" not in t and "&lt;" in t:  # the whole page escaped (Greenhouse): unescape it once first
        t = unescape(t)
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


def _job(weak_remote=False, **k):
    """One posting in the kit's shape. A null or non-text place reads as no place. weak_remote:
    the board's remote flag says False when it was simply never set (Ashby, Workable), so a place
    that says remote wins over it."""
    loc = k.get("location")
    k["location"] = loc.strip() if isinstance(loc, str) else ""
    if (k.get("remote") is None or (weak_remote and k["remote"] is False)) \
            and re.search(r"\bremote\b", k["location"], re.I):
        k["remote"] = True
    k.setdefault("remote", None)
    k.setdefault("salary", "")
    k.setdefault("poster", "")
    k["sponsorship"] = sponsorship(k.get("text", ""))
    return k


def from_greenhouse(x, board):
    return _job(ats="greenhouse", board=board, id=str(x["id"]), title=x["title"].strip(),
                company=x.get("company_name") or board, location=(x.get("location") or {}).get("name") or "",
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
                location=cat.get("location") or "", remote=(x.get("workplaceType") == "remote") or None,
                posted=datetime.fromtimestamp(x["createdAt"] / 1000, timezone.utc).date() if x.get("createdAt") else None,
                url=x["hostedUrl"], salary=salary, text="\n\n".join(p for p in parts if p).strip())


def from_ashby(x, board):
    comp = (x.get("compensation") or {}).get("compensationTierSummary") or ""
    return _job(ats="ashby", board=board, id=x["id"], title=x["title"].strip(), company=board,
                unlisted=x.get("isListed") is False,
                location=x.get("location") or "", remote=bool(x.get("isRemote")), weak_remote=True,
                posted=_iso(x.get("publishedAt")), url=x["jobUrl"], salary=comp,
                text=x.get("descriptionPlain") or text_of(x.get("descriptionHtml", "")))


SR_API = "https://api.smartrecruiters.com/"
WORKDAY_BOARD = re.compile(r"([\w-]+)\.(wd\d+)/([\w-]+)")
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
                location=place, remote=str(x.get("telecommuting")).lower() == "true", weak_remote=True,
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


def personio_home(board):
    """personio:<slug> is on jobs.personio.de, personio:com/<slug> on jobs.personio.com."""
    tld, slug = board.split("/", 1) if board.startswith("com/") else ("de", board)
    return f"https://{slug}.jobs.personio.{tld}"


def from_personio(pos, board):
    """One <position> element of a Personio XML feed."""
    get = lambda tag: (pos.findtext(tag) or "").strip()
    parts = [f"{d.findtext('name') or ''}\n{text_of(d.findtext('value') or '')}".strip()
             for d in pos.iter("jobDescription")]
    return _job(ats="personio", board=board, id=get("id"), title=get("name"), company=get("subcompany") or board,
                location=get("office"), posted=_iso(get("createdAt")),
                url=f"{personio_home(board)}/job/{get('id')}", text="\n\n".join(p for p in parts if p))


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


def rows(d, key):
    """The list of postings in a board's reply; anything else means the API changed or failed."""
    got = (d.get(key) if isinstance(d, dict) else None) if key else d
    if not isinstance(got, list):
        raise NetError(f"the reply is not its list of jobs: {str(d)[:120]}")
    return [x for x in got if isinstance(x, dict)]


def fetch(ats, board, search=""):
    """Every open posting on the board, normalised. Some boards list without the full text;
    detail() fills it in for the ones kept."""
    if ats not in ATS:
        die(f"unknown board type '{ats}'; one of {', '.join(ATS)}")
    try:
        return [j for j in read_board(ats, board, search) if not j.get("unlisted")]
    except NetError as e:
        die(f"{ats} board '{board}' did not answer with its jobs: {e}. Check the board name with jobs.py detect <link>")


WORKDAY_MAX = 200  # 10 requests a second apart; --search narrows a bigger board on the server


def capped(ats, board, got, total):
    print(f"NOTE: {ats}:{board} has {total} openings; read the first {got} only. Narrow it with "
          f"--search <words> (searched on the board's own server) to reach the rest", file=sys.stderr)


def read_board(ats, board, search=""):
    """fetch() without the stop: a board that does not answer, or answers with postings in a shape
    the kit does not know (a field null or of another type), raises NetError."""
    try:
        return _read_board(ats, board, search)
    except (TypeError, KeyError, AttributeError, ValueError) as e:
        raise NetError(f"its postings are not in the shape the kit reads ({type(e).__name__}: {e}); "
                       f"the board's API may have changed") from None


def _read_board(ats, board, search=""):
    if ats == "greenhouse":
        d = http(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true", pinned=True)
        return [from_greenhouse(x, board) for x in rows(d, "jobs")
                if x.get("id") and x.get("title") and str(x.get("absolute_url", "")).startswith("https://")]
    if ats == "lever":
        region, slug = board.split("/", 1) if board.startswith("eu/") else ("", board)
        d = http(f"https://api.{region + '.' if region else ''}lever.co/v0/postings/{slug}?mode=json", pinned=True)
        return [from_lever(x, slug) for x in rows(d, None) if x.get("id") and x.get("text") and x.get("hostedUrl")]
    if ats == "ashby":
        d = http(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true", pinned=True)
        return [from_ashby(x, board) for x in rows(d, "jobs")
                if x.get("id") and x.get("title") and str(x.get("jobUrl", "")).startswith("https://")]
    if ats == "smartrecruiters":
        out, offset = [], 0
        while offset < 300:
            d = http(f"https://api.smartrecruiters.com/v1/companies/{board}/postings?limit=100&offset={offset}",
                     pinned=True)
            for x in rows(d, "content"):
                if not (x.get("id") and x.get("name") and str(x.get("ref", "")).startswith(SR_API)):
                    continue
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
        else:
            capped(ats, board, len(out), d.get("totalFound", 0))
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
            raise NetError(f"its page shows no positions token for company {uid}: open "
                           f"https://www.comeet.com/jobs/{board} with the browser instead")
        d = http(f"https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={tok}&details=true",
                 pinned=True)
        return [from_comeet(x, board) for x in rows(d, None) if (x.get("name") or "").strip()
                and x.get("uid") and str(x.get("url_comeet_hosted_page", "")).startswith("https://")]
    if ats in ("workable", "recruitee", "breezy", "personio", "rippling") and \
            not SLUG.fullmatch(board[4:] if ats == "personio" and board.startswith("com/") else board):
        die(f"{ats} board '{board}' must be one word of letters, digits and dashes (jobs.py detect <link>)")
    if ats == "workable":
        d = http(f"https://apply.workable.com/api/v1/widget/accounts/{board}?details=true", pinned=True)
        return [from_workable(x, board) for x in rows(d, "jobs") if x.get("title") and x.get("shortcode")]
    if ats == "recruitee":
        d = http(f"https://{board}.recruitee.com/api/offers/", pinned=True)
        return [from_recruitee(x, board) for x in rows(d, "offers")
                if x.get("title") and x.get("id") and str(x.get("careers_url", "")).startswith("https://")
                and x.get("status", "published") == "published"]
    if ats == "breezy":
        d = http(f"https://{board}.breezy.hr/json", pinned=True)
        return [from_breezy(x, board) for x in rows(d, None) if x.get("name") and x.get("id")
                and str(x.get("url", "")).startswith(f"https://{board}.breezy.hr/")]
    if ats == "personio":
        import xml.etree.ElementTree as ET
        raw = http(f"{personio_home(board)}/xml", as_json=False, pinned=True)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            raise NetError(f"the reply is not its XML feed ({e}): {raw[:120]}") from None
        if root.tag != "workzag-jobs":
            raise NetError(f"the reply is XML but not its jobs feed (<{root.tag}>): {raw[:120]}")
        return [from_personio(p, board) for p in root.iter("position")
                if (p.findtext("id") or "").strip().isdigit() and (p.findtext("name") or "").strip()]
    if ats == "rippling":
        out = []
        for page in range(10):
            d = http(f"https://ats.rippling.com/api/v2/board/{board}/jobs?page={page}&pageSize=50", pinned=True)
            out += [from_rippling(x, board) for x in rows(d, "items") if x.get("name") and x.get("id")
                    and str(x.get("url", "")).startswith(f"https://ats.rippling.com/{board}/")]
            if page + 1 >= (d.get("totalPages") or 0):
                break
        else:
            capped(ats, board, len(out), f"{d.get('totalPages')} pages of")
        return out
    if ats == "workday":
        m = WORKDAY_BOARD.fullmatch(board)
        if not m:
            die(f"workday board '{board}' must look like <tenant>.<wdN>/<site>, e.g. nvidia.wd5/NVIDIAExternalCareerSite "
                f"(jobs.py detect <a myworkdayjobs.com link>)")
        host, site = board.split("/", 1)
        tenant = m.group(1)
        base = f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
        out, total = [], None
        for offset in range(0, WORKDAY_MAX, 20):
            d = http(base + "/jobs", method="POST", pinned=True,
                     body={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": search})
            if total is None:  # only the first page carries the count; later ones say 0
                total = d.get("total") or 0
            for x in rows(d, "jobPostings"):
                if not (x.get("title") and str(x.get("externalPath", "")).startswith("/job/")):
                    continue
                out.append(_job(ats=ats, board=board, id=x["externalPath"].rsplit("/", 1)[-1],
                                title=x["title"].strip(), company=tenant, location=x.get("locationsText", ""),
                                posted=workday_posted(x.get("postedOn")),
                                url=f"https://{host}.myworkdayjobs.com/{site}{x['externalPath']}",
                                text="", detail=base + x["externalPath"]))
            if offset + 20 >= total:
                break
            time.sleep(1)  # Workday rate-limits bursts
        else:
            capped(ats, board, len(out), total)
        return out
    raise NetError(f"no reader for board type '{ats}'")


def detail_home(j):
    """Where a board's detail URLs must point: its own host."""
    homes = {"workday": f"https://{j['board'].split('/')[0]}.myworkdayjobs.com/",
             "breezy": f"https://{j['board']}.breezy.hr/",
             "rippling": f"https://ats.rippling.com/{j['board']}/",
             "smartrecruiters": SR_API}
    if j["ats"] not in homes:
        die(f"{j['ats']} postings carry no detail link to read")
    return homes[j["ats"]]


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


LIST_ONLY = {  # boards whose API lists jobs but answers no per-job question: (link pattern -> job id)
    "ashby": r"jobs\.ashbyhq\.com/[^/]+/([0-9a-zA-Z-]+)",
    "comeet": r"comeet\.com?/jobs/[\w-]+/[0-9A-F]{2}\.[0-9A-F]{3}/[^/]+/([0-9A-F]{2}\.[0-9A-F]{3})",
    "recruitee": r"\.recruitee\.com/o/([\w-]+)",
    "breezy": r"\.breezy\.hr/p/([0-9a-f]+)",
    "personio": r"\.jobs\.personio\.(?:de|com)/job/(\d+)",
    "rippling": r"ats\.rippling\.com/[\w-]+/jobs/([\w-]+)",
}


def alive(url):
    """("open" | "closed" | "unknown", why). Closed only on the board's own word: a per-job 404 or
    410 where the board uses it for removal, a closed flag, or a full board list without this job.
    Anything ambiguous is unknown: a false "closed" costs the owner a real job."""
    u = url.strip()
    ats, board = detect(u)

    def per_job(api, read, gone_on_404=True):
        try:
            return read(http(api, pinned=True))
        except NetError as e:
            if e.status in (404, 410) and gone_on_404:
                return "closed", f"the {ats} API answers {e.status} for this posting"
            if e.status == 403 and ats == "workday" and '"S22"' in (e.reply or ""):
                return "closed", "Workday answers 403 S22: the posting was withdrawn"
            if e.status in (404, 410):
                return "unknown", f"the {ats} API answers {e.status}, which this board also gives some live " \
                                  f"postings: open the page and look for an Apply button"
            return "unknown", f"the board did not answer clearly ({e}): open the page"

    m = re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", u)
    if ats == "greenhouse" and m:
        return per_job(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}",
                       lambda d: ("open", "the Greenhouse API lists it"))
    m = re.search(r"jobs\.(eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})", u)
    if m:
        return per_job(f"https://api.{'eu.' if m.group(1) else ''}lever.co/v0/postings/{m.group(2)}/{m.group(3)}",
                       lambda d: ("open", "the Lever API lists it"), gone_on_404=False)
    m = re.search(r"jobs\.smartrecruiters\.com/([\w-]+)/(\d+)", u)
    if m:
        def flag(d):
            if isinstance(d, dict) and d.get("active") is False:
                return "closed", "SmartRecruiters marks the posting inactive"
            if isinstance(d, dict) and d.get("active") is True:
                return "open", "SmartRecruiters marks the posting active"
            return "unknown", "SmartRecruiters gave no active flag: open the page"
        return per_job(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}", flag,
                       gone_on_404=False)
    m = re.search(r"https://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)/job/([^?#]+?)/?(?:[?#]|$)", u)
    if m:
        tenant, wd, site, path = m.groups()
        return per_job(f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{path}",
                       lambda d: ("open", "the Workday API lists it"))
    m = re.search(r"apply\.workable\.com/([\w-]+)/j/([\w-]+)", u)
    if m:
        def state(d):
            s = str((d or {}).get("state", "")).lower() if isinstance(d, dict) else ""
            if s == "published":
                return "open", "Workable marks it published"
            if s in ("closed", "archived"):
                return "closed", f"Workable marks it {s}"
            return "unknown", f"Workable's state is '{s or 'missing'}': open the page"
        return per_job(f"https://apply.workable.com/api/v2/accounts/{m.group(1)}/jobs/{m.group(2)}", state)
    m = re.search(LIST_ONLY.get(ats, r"(?!)"), u)
    if m:
        try:
            js = read_board(ats, board)
        except NetError as e:
            return "unknown", f"the {ats} board did not answer clearly ({e}): open the page"
        job = m.group(1)
        if any(j["id"] == job or j["url"].rstrip("/").endswith("/" + job) for j in js):
            return "open", f"the {ats} board lists it"
        if ats == "rippling" and len(js) >= 500:
            return "unknown", "the Rippling board is longer than the kit reads: open the page"
        return "closed", f"the {ats} board lists {len(js)} open jobs and this one is not among them"
    try:
        http(u, as_json=False)
    except NetError as e:
        if e.status in (404, 410):
            return "closed", f"the page answers {e.status}"
        return "unknown", f"the page did not answer clearly ({e})"
    return "unknown", "the page loads: read it for a closed notice and an Apply button"


REGISTRY = Path(__file__).resolve().parent / "data" / "employers.tsv"
GUESS_ORDER = ("greenhouse", "ashby", "lever", "workable", "smartrecruiters", "recruitee", "breezy", "rippling",
               "personio")
SMALL_BOARD = 5


def registry():
    """[(name, ats, board)] from the vendored employer registry (CC BY 4.0, THIRD_PARTY_NOTICES.md)."""
    if not REGISTRY.is_file():
        die(f"{REGISTRY} is missing: restore it from git (git checkout -- scripts/data)")
    out, header = [], True
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if header and line.startswith("# "):
            continue
        header = False
        parts = line.split("\t")
        if len(parts) == 3:
            out.append(tuple(parts))
    return out


def find(company):
    """Where a company's jobs are: [(how, "ats:board", note)]. The registry first (every board it
    lists for that name), else the first guessed board name that answers with open jobs."""
    if not company_key(company):
        die(f"'{company}' has no letters or digits to look up")
    reg = registry()
    exact = [r for r in reg if r[0].casefold() == company.strip().casefold()]
    hits = exact or [r for r in reg if company_key(r[0]) == company_key(company)]
    if hits:
        return [("registry", f"{ats}:{board}", name) for name, ats, board in hits]
    words = [w for w in company_key(company).split() if w.isascii()]
    if not words:
        die(f"'{company}': board names are guessed from Latin letters. Pass the company's English "
            f"name, or run jobs.py detect on a link to its careers page")
    slugs = list(dict.fromkeys(["".join(words), "-".join(words)]))
    for ats in GUESS_ORDER:
        for slug in slugs:
            try:
                js = read_board(ats, slug)
            except NetError as e:  # NetBlocked is not a NetError: a blocked network still ends the run
                if e.status not in (404, 410):  # anything but "no such board" is worth a line
                    print(f"NOTE: {ats}:{slug} skipped: {e}", file=sys.stderr)
                continue
            if not js:
                continue
            said = js[0]["company"]
            note = f"{len(js)} open"
            if said and said.casefold() != slug.casefold():
                note += f"; the board calls itself {said}"
            if len(js) < SMALL_BOARD:
                note += "; small board, and board names collide"
            note += f"; verify it belongs to {company}: its careers page should link to it"
            return [("guessed", f"{ats}:{slug}", note)]
    return []


def undated_note(kept, days):
    n = sum(1 for j in kept if not j["posted"])
    return f"{n} kept with no posting date (--days cannot judge them)" if n else ""


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
    slug = re.sub(r"[^a-z0-9]+", "-", f"{j['company']}-{j['id']}".lower()).strip("-")
    if len(slug) > 80:  # cut, but keep the id's tail distinct: two long ids must not share a file
        slug = slug[:71].rstrip("-") + "-" + hashlib.sha1(str(j["id"]).encode()).hexdigest()[:8]
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
    fd = sub.add_parser("find")
    fd.add_argument("company")
    al = sub.add_parser("alive")
    al.add_argument("url")
    li = sub.add_parser("list")
    li.add_argument("board")
    li.add_argument("--title", default="")
    li.add_argument("--location", default="")
    li.add_argument("--days", type=int, default=30)
    li.add_argument("--search", default="")
    li.add_argument("--save")
    li.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(sys.argv[1:])

    if a.cmd == "alive":
        if not re.match(r"https?://", a.url.strip()):
            die(f"'{a.url}' is not a posting link")
        state, why = alive(a.url)
        print(f"{state}: {why}")
        sys.exit({"open": 0, "closed": 1}.get(state, 3))
    if a.cmd == "find":
        hits = find(a.company)
        for how, board, note in hits:
            print(f"{how}  {board}  {note}")
        if not hits:
            print(f"no board found for {a.company}. Comeet boards cannot be guessed: search "
                  f"site:comeet.com/jobs \"{a.company}\" and run jobs.py detect on a link; else read the "
                  f"company's careers page with the browser")
        return
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
    note = undated_note(kept, a.days)
    print(f"{ats}:{board}  {len(allj)} open, {len(kept)} match (title /{a.title}/, place /{a.location}/, "
          f"last {a.days} days)" + (f"; {note}" if note else ""))
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
