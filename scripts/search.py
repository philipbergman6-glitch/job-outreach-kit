#!/usr/bin/env python3
"""Semantic web search for people and companies, when the owner adds a search key. Optional:
without one, use your own web search tool; every flow works either way. Stdlib only.

Usage:
  search.py people "<who>" [-n 10] [--site DOMAIN ...]
        people by meaning, not keywords: "head of data engineering at Acme Robotics Tel Aviv".
        Exa's people index first; Brave on LinkedIn snippets when only Brave is set.
  search.py web "<query>" [-n 10] [--fresh pd|pw|pm|py] [--site DOMAIN ...]
        ordinary web results (Brave first, then Exa), e.g. press, talks, team pages.
  search.py company "<what>" [-n 10]
        companies by description: "Israeli computer-vision startups hiring in 2026".
  search.py keys
        which search keys are set.

Keys in .env: EXA_API_KEY (exa.ai, about $10 of free searches a month) and/or BRAVE_API_KEY
(api.search.brave.com, about 1,000 free searches a month). Results print as
  [date] title | url
      snippet
Keep only a name and a title from any result; confirm a person with a second source
(flow/people-discovery.md). Exit 2 = hard-fail (no key, bad input, or the service failed)."""
import argparse
import sys
import urllib.parse
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import NetError, die, env_optional, http, run


def exa(query, n, category=None, sites=()):
    key = env_optional("EXA_API_KEY").get("EXA_API_KEY")
    body = {"query": query, "type": "auto", "numResults": n,
            "contents": {"highlights": {"maxCharacters": 300}}}
    if category:
        body["category"] = category
    if sites:
        body["includeDomains"] = list(sites)
    d = http("https://api.exa.ai/search", method="POST", headers={"x-api-key": key}, body=body)
    out = []
    for r in d.get("results", []):
        snip = " … ".join(r.get("highlights") or []) or (r.get("text") or "")[:300]
        out.append({"title": r.get("title") or "", "url": r.get("url", ""),
                    "date": (r.get("publishedDate") or "")[:10], "snippet": snip.strip()})
    return out


def brave(query, n, fresh=None, sites=()):
    key = env_optional("BRAVE_API_KEY").get("BRAVE_API_KEY")
    q = query + "".join(f" site:{s}" for s in sites)
    params = {"q": q, "count": min(n, 20)}
    if fresh:
        params["freshness"] = fresh
    d = http("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(params),
             headers={"X-Subscription-Token": key})
    out = []
    for r in (d.get("web") or {}).get("results", []):
        snip = " … ".join([r.get("description") or ""] + (r.get("extra_snippets") or [])[:2])
        out.append({"title": r.get("title") or "", "url": r.get("url", ""),
                    "date": r.get("page_age", "")[:10] if r.get("page_age") else (r.get("age") or ""),
                    "snippet": strip_tags(snip)})
    return out


def strip_tags(s):
    import re
    return re.sub(r"<[^>]+>", "", s).strip()


def keys():
    return env_optional("EXA_API_KEY", "BRAVE_API_KEY")


def show(results):
    if not results:
        print("no results")
    for r in results:
        print(f"[{r['date'] or 'undated'}] {r['title']} | {r['url']}")
        if r["snippet"]:
            print(f"    {r['snippet'][:300]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("people", "web", "company"):
        p = sub.add_parser(name)
        p.add_argument("query")
        p.add_argument("-n", type=int, default=10)
        p.add_argument("--site", action="append", default=[])
        p.add_argument("--fresh", choices=["pd", "pw", "pm", "py"])
    sub.add_parser("keys")
    a = ap.parse_args(sys.argv[1:])
    k = keys()
    if a.cmd == "keys":
        print(f"EXA_API_KEY {'set' if 'EXA_API_KEY' in k else 'not set'}; "
              f"BRAVE_API_KEY {'set' if 'BRAVE_API_KEY' in k else 'not set'}")
        return
    if not k:
        die("no search key in .env (EXA_API_KEY or BRAVE_API_KEY). This script is optional: "
            "use your own web search tool instead")
    if not a.query.strip() or not 1 <= a.n <= 50:
        die("give a query and -n between 1 and 50")
    brave_runs = "BRAVE_API_KEY" in k and (a.cmd == "web" or (a.cmd == "people" and "EXA_API_KEY" not in k))
    if a.fresh and not brave_runs:
        die("--fresh works only with Brave search (BRAVE_API_KEY); Exa's people and company searches "
            "take no date filter. Drop --fresh, or use search.py web with a Brave key")
    if a.site and a.cmd == "company":
        die("--site does not apply to company search; use search.py web --site <domain>")
    if brave_runs and a.n > 20:
        die("Brave returns at most 20 results per search: use -n 20 or less")
    try:
        if a.cmd == "people":
            if "EXA_API_KEY" in k:
                show(exa(a.query, a.n, "people", a.site))
            else:
                show(brave(a.query, a.n, a.fresh, a.site or ["linkedin.com/in"]))
        elif a.cmd == "company":
            if "EXA_API_KEY" not in k:
                die("company search needs EXA_API_KEY; use search.py web or your own web search")
            show(exa(a.query, a.n, "company"))
        else:
            show(brave(a.query, a.n, a.fresh, a.site) if "BRAVE_API_KEY" in k else exa(a.query, a.n, None, a.site))
    except NetError as e:
        die(f"search failed: {e}")


if __name__ == "__main__":
    run(main)
