#!/usr/bin/env python3
"""Hunter.io wrapper. Usage:
  hunter.py domain <domain>                 pattern + sample addresses
  hunter.py find <domain> <first> <last>    one person's address
  hunter.py verify <email>
  hunter.py quota
Reads HUNTER_API_KEY from <repo>/.env. Hard-fails on missing input or API error."""
import json
import sys
import urllib.parse
from pathlib import Path

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import NetError, die, env, http, run

API = "https://api.hunter.io/v2/"


def get(path, **params):
    """One Hunter API call through _common.http: the kit's User-Agent, a wait and retry on 429,
    the certificate hint. Errors name the endpoint only: the query carries the API key."""
    params["api_key"] = env("HUNTER_API_KEY")["HUNTER_API_KEY"]
    try:
        d = http(API + path + "?" + urllib.parse.urlencode(params), pinned=True)
    except NetError as e:
        die(f"Hunter {path}: {e}")
    if not isinstance(d, dict) or not isinstance(d.get("data"), dict):
        die(f"Hunter {path}: the reply has no data: {str(d)[:200]}")
    return d


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) == 2 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(argv) < 2:
        die(__doc__)
    cmd = argv[1]
    if cmd == "domain" and len(argv) == 3:
        d = get("domain-search", domain=argv[2], limit=10)["data"]
        print(f"domain={d['domain']} pattern={d.get('pattern')} org={d.get('organization')}")
        for e in d.get("emails", []):
            print(f"  {e['value']}  conf={e.get('confidence')}  "
                  f"{e.get('first_name', '')} {e.get('last_name', '')}  {e.get('position') or ''}")
    elif cmd == "find" and len(argv) == 5:
        d = get("email-finder", domain=argv[2], first_name=argv[3], last_name=argv[4])["data"]
        print(f"email={d.get('email')} score={d.get('score')} "
              f"verif={json.dumps(d.get('verification'))} position={d.get('position')}")
    elif cmd == "verify" and len(argv) == 3:
        d = get("email-verifier", email=argv[2])["data"]
        print(f"email={d['email']} status={d.get('status')} result={d.get('result')} "
              f"score={d.get('score')} accept_all={d.get('accept_all')} mx={d.get('mx_records')}")
    elif cmd == "quota" and len(argv) == 2:
        d = get("account")["data"]
        r = d.get("requests", {})
        s, v = r.get("searches", {}), r.get("verifications", {})
        print(f"searches {s.get('used')}/{s.get('available')}  "
              f"verifications {v.get('used')}/{v.get('available')}  reset={d.get('reset_date')}")
    else:
        die(__doc__)


if __name__ == "__main__":
    run(main)
