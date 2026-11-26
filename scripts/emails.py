#!/usr/bin/env python3
"""Find and check a person's work email without depending on any one service. Stdlib only.

Usage:
  emails.py find <first> <last> <domain> [--known "Name <addr>" ...] [--no-probe] [--no-site]
                 [--providers a,b] [--all-providers]
        the whole ladder: addresses published on the company site, the pattern they and
        --known reveal (run `github` first and pass what it finds as --known), every
        email-finder API configured in .env, then an SMTP check. Prints
        each candidate with its evidence and one confidence (High / Medium / Low). Finders are
        asked in order and the rest skipped once one reports a valid address (--all-providers
        asks every one); --no-site skips the site scan when it was already run for the company.
  emails.py site <domain> [--url URL ...]
        addresses published on the company's own pages (contact, about, team, careers,
        imprint, privacy, accessibility), including obfuscated and Cloudflare-protected ones.
  emails.py github <org> <domain>
        author addresses at <domain> in the public commits of the org's most recent repos.
  emails.py guess <first> <last> <domain> [--known "Name <addr>" ...]
        candidate addresses, ranked by the pattern the known addresses reveal.
  emails.py mx <domain>
        the domain's mail servers, mail provider, and SPF includes (the real mail domain
        often differs from the website's).
  emails.py probe <email>... [--from ADDR]
        ask the domain's mail server whether each mailbox exists, calibrated against a
        random address so an accept-all domain is called out instead of trusted.
  emails.py providers
        which email-finder APIs are configured, and how many lookups each has left.

Confidence: High = published by the person or company, a strict-domain SMTP "exists", or a
provider "valid" on a strict domain. Medium = two independent sources agree. Low = one guess.
Exit 2 = hard-fail (bad input)."""
import argparse
import random
import re
import smtplib
import string
import sys
import unicodedata
import urllib.parse
from html import unescape
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:  # python3 -I leaves the script's own folder off the import path
    sys.path.insert(0, _HERE)

from _common import NetBlocked, NetError, die, env_optional, http, run

DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
ADDR = re.compile(r"[a-z0-9][a-z0-9._%+-]{0,63}@(?:[a-z0-9-]+\.)+[a-z]{2,24}", re.I)
GENERIC = {"info", "hello", "contact", "jobs", "careers", "career", "hr", "people", "talent",
           "recruiting", "recruitment", "office", "admin", "support", "sales", "press", "media",
           "privacy", "legal", "security", "billing", "team", "hiring", "cv", "jobs-il", "noreply",
           "no-reply", "dpo", "gdpr", "accessibility", "marketing", "partners", "help", "service"}
# Pattern prior: rough order of how often each shape is seen at companies that publish it.
PATTERNS = ["{first}.{last}", "{first}", "{f}{last}", "{first}{last}", "{f}.{last}",
            "{first}_{last}", "{first}{l}", "{last}", "{last}.{first}", "{first}-{last}",
            "{last}{f}", "{f}{l}", "{last}{first}", "{first}.{l}"]
PAGES = ["", "contact", "contact-us", "about", "about-us", "team", "our-team", "company",
         "careers", "jobs", "impressum", "imprint", "legal", "privacy", "privacy-policy",
         "accessibility", "press"]
PROVIDERS_MX = [("google.com", "Google Workspace"), ("googlemail.com", "Google Workspace"),
                ("outlook.com", "Microsoft 365"), ("pphosted.com", "Proofpoint"),
                ("ppe-hosted.com", "Proofpoint"), ("mimecast", "Mimecast"),
                ("iphmx.com", "Cisco Secure Email"), ("barracudanetworks.com", "Barracuda"),
                ("zoho", "Zoho"), ("messagingengine.com", "Fastmail"), ("secureserver.net", "GoDaddy")]
PROBE_NOTES = {
    "Google Workspace": "usually rejects unknown mailboxes: a probe means something",
    "Microsoft 365": "one recipient per connection; often accept-all behind a gateway",
    "Proofpoint": "refuses some senders; the null sender usually works",
    "Mimecast": "often refuses probes from home connections",
    "Cisco Secure Email": "often refuses probes from home connections",
}

smtp_factory = smtplib.SMTP  # tests replace this and `http`
MISSING = re.compile(r"\b5\.1\.[0-9]\b|user unknown|unknown user|no such (user|mailbox|recipient)|"
                     r"mailbox (unavailable|not found|does not exist)|does not exist|invalid recipient|"
                     r"recipient not found|address not found", re.I)
POLICY = re.compile(r"\b5\.7\.[0-9]\b|blocked|spamhaus|blacklist|block list|denied|policy|client host", re.I)


# ---------- names and patterns ----------

# Letters that NFKD keeps whole (no accent mark to strip), spelled as mailbox names usually are
SPELL = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "ß": "ss", "æ": "ae", "Æ": "Ae", "œ": "oe",
                       "Œ": "Oe", "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "ı": "i"})


def norm(s):
    s = unicodedata.normalize("NFKD", s.translate(SPELL)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z-]", "", s)


def _split(first, last):
    """(first, [last variants]) in plain Latin letters, or None when either is empty."""
    f = norm(first.split()[0]).replace("-", "") if first.strip() else ""
    hyphen = [w for w in (norm(x) for x in last.split()) if w.strip("-")]
    parts = [w for w in re.split(r"[\s-]+", " ".join(hyphen)) if w]
    if not f or not parts:
        return None
    lasts = ["".join(parts)]
    if len(parts) > 1:
        if "-" in "".join(hyphen):
            lasts += ["-".join(parts), parts[0]]
        lasts.append(parts[-1])
    return f, list(dict.fromkeys(lasts))


def _parts(first, last):
    got = _split(first, last)
    if not got:
        die(f"need a first and a last name in Latin letters, got '{first}' '{last}'. "
            f"Names in another alphabet: pass each likely spelling separately")
    return got


def _local(pattern, f, l):
    return pattern.format(first=f, last=l, f=f[0], l=l[0])


def check_domain(domain):
    d = domain.lower().strip().rstrip(".")
    d = re.sub(r"^https?://", "", d).split("/")[0]
    d = d[4:] if d.startswith("www.") else d
    if not DOMAIN.match(d):
        die(f"'{domain}' is not a domain like acme.com")
    return d


def parse_known(text):
    m = re.match(r"\s*(.+?)\s*<\s*([^>\s]+@[^>\s]+)\s*>\s*$", text)
    if not m or len(m.group(1).split()) < 2:
        die(f"--known '{text}' must look like: First Last <first.last@acme.com>")
    name = m.group(1).split()
    return name[0], name[-1], m.group(2).lower()


def infer(known, domain):
    """[(pattern, votes)] best first, from (first, last, email) triples at the domain."""
    votes = {}
    for first, last, email in known:
        local, _, d = email.lower().partition("@")
        if not (d == domain or d.endswith("." + domain)) or local in GENERIC:
            continue
        got = _split(first, last)
        if not got:
            continue
        f, lasts = got
        for p in PATTERNS:
            if any(_local(p, f, l) == local for l in lasts):
                votes[p] = votes.get(p, 0) + 1
                break
    return sorted(votes.items(), key=lambda kv: (-kv[1], PATTERNS.index(kv[0])))


def candidates(first, last, domain, known=()):
    domain = check_domain(domain)
    f, lasts = _parts(first, last)
    order = [p for p, _ in infer(known, domain)] + PATTERNS
    out = []
    for p in dict.fromkeys(order):
        for l in lasts:
            out.append(f"{_local(p, f, l)}@{domain}")
    return list(dict.fromkeys(out))


# ---------- published addresses ----------

def _cf_decode(hexstr):
    try:
        b = bytes.fromhex(hexstr)
        return "".join(chr(c ^ b[0]) for c in b[1:])
    except (ValueError, IndexError):
        return ""


def extract(html, domain):
    """Addresses at domain (or a subdomain) in a page, including common obfuscations."""
    text = unescape(urllib.parse.unquote(html))
    text += " " + " ".join(_cf_decode(h) for h in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html))
    text = re.sub(r"\s*[\[\(\{]\s*(?:at|@)\s*[\]\)\}]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*[\[\(\{]\s*(?:dot|\.)\s*[\]\)\}]\s*", ".", text, flags=re.I)
    found = []
    for a in ADDR.findall(text):
        a = a.lower().strip(".")
        d = a.split("@", 1)[1]
        if d == domain or d.endswith("." + domain):
            found.append(a)
    return list(dict.fromkeys(found))


def is_generic(addr):
    return addr.split("@", 1)[0].lower() in GENERIC


def site(domain, urls=()):
    domain = check_domain(domain)
    pages = list(urls) or [f"https://{domain}/{p}" for p in PAGES]
    from concurrent.futures import ThreadPoolExecutor

    def one(url):
        try:
            return url, http(url, as_json=False, timeout=20), None
        except NetError as e:
            return url, None, str(e)

    found, seen, errors = {}, 0, []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for url, html, err in pool.map(one, pages):
            if err:
                errors.append(err)
                continue
            seen += 1
            for addr in extract(html, domain):
                found.setdefault(addr, url)
    return found, seen, errors


def github(org, domain):
    domain = check_domain(domain)
    gh_auth = env_optional("GITHUB_TOKEN").get("GITHUB_TOKEN")
    hdr = {"Authorization": f"Bearer {gh_auth}"} if gh_auth else {}
    try:
        repos = http(f"https://api.github.com/orgs/{urllib.parse.quote(org)}/repos?sort=pushed&per_page=8",
                      headers=hdr)
    except NetError as e:
        die(f"GitHub org '{org}': {e}")
    people = {}
    for repo in [r for r in repos if not r.get("fork")][:5]:
        try:
            commits = http(f"https://api.github.com/repos/{repo['full_name']}/commits?per_page=100", headers=hdr)
        except NetError as e:
            print(f"  skipped {repo['full_name']}: {e}", file=sys.stderr)
            continue
        for c in commits:
            a = (c.get("commit") or {}).get("author") or {}
            email = (a.get("email") or "").lower()
            d = email.partition("@")[2]
            if d == domain or d.endswith("." + domain):
                people.setdefault(email, a.get("name") or "")
    return people


# ---------- DNS ----------

def parse_nslookup(out, kind):
    """nslookup's text (macOS, Linux and Windows layouts) as a DNS-over-HTTPS style answer:
    {"Status": 0 or 3, "Answer": [{"data": ...}]}. None when it holds no verdict at all."""
    if re.search(r"NXDOMAIN|Non-existent domain", out):
        return {"Status": 3}
    answer, lines = [], out.splitlines()
    for i, line in enumerate(lines):
        if kind == "MX":
            m = (re.search(r"mail exchanger = (\d+) (\S+)", line)
                 or re.search(r"MX preference = (\d+), mail exchanger = (\S+)", line))
            if m:
                answer.append({"data": f"{m.group(1)} {m.group(2)}"})
        elif "text =" in line:
            text = line.split("text =", 1)[1].strip()
            if not text:  # Windows puts the string on a later line
                text = next((x.strip() for x in lines[i + 1:] if x.strip()), "")
            if text.startswith('"'):
                answer.append({"data": text})
    if answer or re.search(r"No answer|Non-authoritative answer|Authoritative answers", out):
        return {"Status": 0, "Answer": answer}
    return None


def system_dns(domain, kind):
    """Ask the computer's own resolver through nslookup. Raises NetError when it gives no verdict."""
    import subprocess
    try:
        p = subprocess.run(["nslookup", f"-type={kind}", domain], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise NetError(f"nslookup -type={kind} {domain}: {e}")
    d = parse_nslookup(p.stdout + p.stderr, kind)
    if d is None:
        raise NetError(f"nslookup -type={kind} {domain}: {(p.stdout + p.stderr).strip()[-200:]}")
    return d


def dns_mail(domain):
    """(mx hosts by preference, spf includes) via DNS over HTTPS, then the system resolver
    (networks that filter DNS, such as OpenDNS / Umbrella, often block DNS over HTTPS)."""
    domain = check_domain(domain)

    def ask(kind):
        why, refused = [], None
        for base in ("https://dns.google/resolve", "https://cloudflare-dns.com/dns-query"):
            try:
                d = http(f"{base}?name={domain}&type={kind}", headers={"Accept": "application/dns-json"})
            except NetError as e:
                why.append(str(e))
                continue
            except NetBlocked as e:  # a proxy refused DNS over HTTPS; the system resolver may still work
                why.append(str(e))
                refused = refused or e
                continue
            if d.get("Status") == 3:
                die(f"{domain} does not exist in DNS: check the spelling, or find the domain the company really uses")
            if d.get("Status", 0) == 0:
                return d
        if why:  # the network refused DNS over HTTPS: ask this computer's resolver instead
            try:
                d = system_dns(domain, kind)
            except NetError as e:
                if refused:  # nothing reached DNS: the blocked network is the cause to name
                    raise refused from None
                why.append(str(e))
            else:
                if d["Status"] == 3:
                    die(f"{domain} does not exist in DNS: check the spelling, or find the domain the company really uses")
                return d
        cause = (f"({'; '.join(why)}). Fix the cause named there, then try again" if why
                 else "(no usable answer). Try again in a few minutes")
        die(f"DNS lookup for {domain} failed on dns.google, cloudflare-dns.com and nslookup {cause}")

    mx = []
    for a in ask("MX").get("Answer", []):
        parts = a.get("data", "").split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].rstrip("."):  # "0 ." = takes no mail
            mx.append((int(parts[0]), parts[1].rstrip(".").lower()))
    spf = []
    for a in ask("TXT").get("Answer", []):
        t = a.get("data", "").replace('" "', "").strip('"')
        if t.startswith("v=spf1"):
            spf += re.findall(r"include:(\S+)", t)
    return [h for _, h in sorted(mx)], spf


def provider_of(mx):
    for host in mx:
        for needle, name in PROVIDERS_MX:
            if needle in host:
                return name
    return "other" if mx else "none"


# ---------- SMTP probe ----------

def _rcpt(mx, addr, sender):
    """One connection, one recipient. Returns (code, text) or raises OSError."""
    s = smtp_factory(mx, 25, timeout=15, local_hostname="localhost")
    try:
        s.ehlo()
        code, msg = s.mail(sender)
        if code >= 400:
            return -1, msg
        return s.rcpt(addr)
    finally:
        try:
            s.quit()
        except Exception:
            s.close()


def probe(addrs, mx, sender=""):
    """{'catch_all': bool|None, 'results': {addr: verdict}, 'error': str|None}"""
    if not mx:
        return {"catch_all": None, "results": {}, "error": "the domain has no mail server (no MX record)"}
    domain = addrs[0].split("@", 1)[1]
    junk = "".join(random.choice(string.ascii_lowercase) for _ in range(14)) + "@" + domain
    # The null sender passes most gateways (Proofpoint refuses example.com); the second is a
    # placeholder that names no real person. Never the owner's own address.
    senders = [sender] if sender else ["", "probe@example.com"]

    def ask(addr):
        unreachable, refused = None, False
        for host in mx[:2]:
            for snd in senders:
                try:
                    code, msg = _rcpt(host, addr, snd)
                except (OSError, smtplib.SMTPException) as e:
                    unreachable = e
                    break
                if code == -1:
                    refused = True
                    continue
                return code, (msg.decode("utf-8", "replace") if isinstance(msg, bytes) else str(msg))
        if refused:
            return None, "the server refused every sender address"
        raise OSError(str(unreachable))

    try:
        jcode, jtext = ask(junk)  # a made-up mailbox: a strict server must say it is missing
    except OSError as e:
        return {"catch_all": None, "results": {}, "error":
                f"could not reach {mx[0]} on port 25 ({e}). Home and cloud networks often block "
                f"port 25: the probe is unavailable here, nothing is proven either way"}
    if jcode is not None and 200 <= jcode < 300:
        catch_all = True
    elif jcode is not None and jcode >= 500 and MISSING.search(jtext) and not POLICY.search(jtext):
        catch_all = False
    else:  # greylisted, refused, or blocked: the server's yes would prove nothing
        catch_all = None
    res = {}
    for a in addrs:
        if catch_all:
            res[a] = "unknown (accept-all domain)"
            continue
        try:
            code, msg = ask(a)
        except OSError as e:
            res[a] = f"unknown ({e})"
            continue
        if code is None:
            res[a] = f"unknown ({msg})"
        elif 200 <= code < 300:
            res[a] = "exists" if catch_all is False else "accepted (the server's test answer was unclear, so this proves little)"
        elif code >= 500 and MISSING.search(msg) and not POLICY.search(msg):
            res[a] = "missing"
        else:
            res[a] = f"unknown ({code} {msg[:60]})"
    return {"catch_all": catch_all, "results": res, "error": None}


# ---------- providers ----------

def _hunter_find(keys, first, last, domain):
    d = http("https://api.hunter.io/v2/email-finder?" + urllib.parse.urlencode(
        {"domain": domain, "first_name": first, "last_name": last, "api_key": keys["HUNTER_API_KEY"]}))["data"]
    st = ((d.get("verification") or {}).get("status")) or ""
    return d.get("email"), ("valid" if st == "valid" else "found")


def _hunter_left(keys):
    d = http("https://api.hunter.io/v2/account?api_key=" + keys["HUNTER_API_KEY"])["data"]
    s = (d.get("requests") or {}).get("searches") or {}
    return f"{(s.get('available') or 0) - (s.get('used') or 0)} searches left, reset {d.get('reset_date')}"


def _prospeo_find(keys, first, last, domain):
    try:
        d = http("https://api.prospeo.io/enrich-person", method="POST", headers={"X-KEY": keys["PROSPEO_API_KEY"]},
                  body={"only_verified_email": True,
                        "data": {"first_name": first, "last_name": last, "company_website": domain}})
    except NetError as e:
        if "NO_MATCH" in str(e):
            return None, ""
        raise
    em = ((d.get("person") or {}).get("email")) or {}
    return em.get("email"), ("valid" if str(em.get("status", "")).upper() == "VERIFIED" else "found")


def _prospeo_left(keys):
    r = http("https://api.prospeo.io/account-information", headers={"X-KEY": keys["PROSPEO_API_KEY"]}).get("response") or {}
    return f"{r.get('remaining_credits')} credits left, renews {r.get('next_quota_renewal_date')}"


def _tomba_hdr(keys):
    return {"X-Tomba-Key": keys["TOMBA_API_KEY"], "X-Tomba-Secret": keys["TOMBA_API_SECRET"]}


def _tomba_find(keys, first, last, domain):
    d = http("https://api.tomba.io/v1/email-finder?" + urllib.parse.urlencode(
        {"domain": domain, "first_name": first, "last_name": last}), headers=_tomba_hdr(keys)).get("data") or {}
    st = ((d.get("verification") or {}).get("status")) or ""
    return d.get("email"), ("valid" if st == "valid" and not d.get("accept_all") else "found")


def _tomba_left(keys):
    r = (http("https://api.tomba.io/v1/me", headers=_tomba_hdr(keys)).get("data") or {}).get("requests") or {}
    s = r.get("domains") or {}
    return f"{(s.get('available') or 0) - (s.get('used') or 0)} searches left"


def _apollo_find(keys, first, last, domain):
    d = http("https://api.apollo.io/api/v1/people/match?" + urllib.parse.urlencode(
        {"first_name": first, "last_name": last, "domain": domain}), method="POST", body={},
        headers={"x-api-key": keys["APOLLO_API_KEY"]})
    per = d.get("person") or {}
    if not per or per.get("match_confidence") == "none":
        return None, ""
    return per.get("email"), ("valid" if per.get("email_status") == "verified" else "found")


def _anymail_find(keys, first, last, domain):
    d = http("https://api.anymailfinder.com/v5.1/find-email/person", method="POST", timeout=180,
              headers={"Authorization": keys["ANYMAILFINDER_API_KEY"]},
              body={"domain": domain, "first_name": first, "last_name": last})
    if d.get("email_status") != "valid" or not d.get("email"):
        return None, ""
    return d["email"], "valid"


def _anymail_left(keys):
    d = http("https://api.anymailfinder.com/v5.1/account", headers={"Authorization": keys["ANYMAILFINDER_API_KEY"]})
    return f"{d.get('credits_left')} credits left"


def _findymail_find(keys, first, last, domain):
    d = http("https://app.findymail.com/api/search/name", method="POST",
              headers={"Authorization": "Bearer " + keys["FINDYMAIL_API_KEY"]},
              body={"name": f"{first} {last}", "domain": domain})
    return (d.get("contact") or {}).get("email"), "found"


def _findymail_left(keys):
    d = http("https://app.findymail.com/api/credits?type=finder",
              headers={"Authorization": "Bearer " + keys["FINDYMAIL_API_KEY"]})
    return f"{d.get('credits')} credits left"


def _see_dashboard(keys):
    return "credits: see the provider's dashboard"


# name -> (env keys, find(keys, first, last, domain) -> (email|None, "valid"|"found"), credits(keys) -> str)
# `find` asks them in this order, largest free tier first (each provider's docs, read 2026-11-17;
# free tiers change, so `emails.py providers` reports what is really left).
PROVIDERS = {
    "prospeo": (("PROSPEO_API_KEY",), _prospeo_find, _prospeo_left),
    "hunter": (("HUNTER_API_KEY",), _hunter_find, _hunter_left),
    "apollo": (("APOLLO_API_KEY",), _apollo_find, _see_dashboard),
    "tomba": (("TOMBA_API_KEY", "TOMBA_API_SECRET"), _tomba_find, _tomba_left),
    "anymailfinder": (("ANYMAILFINDER_API_KEY",), _anymail_find, _anymail_left),
    "findymail": (("FINDYMAIL_API_KEY",), _findymail_find, _findymail_left),
}


def configured(only=None):
    out = {}
    for name, (keys, find_fn, left_fn) in PROVIDERS.items():
        if only and name not in only:
            continue
        vals = env_optional(*keys)
        if all(k in vals for k in keys):
            out[name] = (vals, find_fn, left_fn)
    return out


# ---------- verdict ----------

def grade(addr, ev):
    """ev keys: site, github (bool), probe ('exists'|'missing'|...), catch_all (bool),
    providers {name: 'valid'|'found'}, pattern_votes (int: known addresses that fit)."""
    if ev.get("probe") == "missing":
        return "Low"
    if ev.get("site") or ev.get("github"):
        return "High"
    strict = ev.get("catch_all") is False
    if ev.get("probe") == "exists" and strict:
        return "High"
    provs = ev.get("providers") or {}
    if "valid" in provs.values():  # High only "on a domain that rejects unknown mailboxes"
        return "High" if strict else "Medium"
    sources = len(provs) + (1 if ev.get("pattern_votes", 0) >= 1 else 0)
    if ev.get("pattern_votes", 0) >= 2 or sources >= 2:
        return "Medium"
    return "Low"


# ---------- commands ----------

def cmd_find(a):
    domain = check_domain(a.domain)
    known = [parse_known(k) for k in a.known]
    print(f"== {a.first} {a.last} at {domain}")
    pub, seen = ({}, 0) if a.no_site else site(domain)[:2]
    print(f"company site: {seen} pages read, {len(pub)} addresses published at {domain}")
    for addr in pub:
        print(f"  {addr}  ({'generic box' if is_generic(addr) else 'personal'}, {pub[addr]})")
    if any(not is_generic(x) for x in pub):
        print("  personal addresses teach the pattern: rerun with --known \"First Last <addr>\" "
              "for each one whose owner you can name")
    pats = infer(known, domain)
    if pats:
        print("pattern from known addresses: " + ", ".join(f"{p} x{n}" for p, n in pats))
    cands = candidates(a.first, a.last, domain, known)[:8]
    ev = {c: {"pattern_votes": dict(pats).get(pattern_of(c, a.first, a.last), 0)} for c in cands}
    for c in cands:
        if c in pub:
            ev[c]["site"] = True
    only = [n.strip() for n in a.providers.split(",")] if a.providers else None
    unknown = [n for n in only or [] if n not in PROVIDERS]
    if unknown:
        die(f"--providers: unknown {unknown}; the names are {', '.join(PROVIDERS)}")
    provs = configured(only)
    if not provs:
        print("email-finder APIs: none configured (emails.py providers shows how to add one)")
    for name, (keys, find_fn, _) in provs.items():
        if not a.all_providers and any("valid" in (e.get("providers") or {}).values() for e in ev.values()):
            print(f"  {name}: not asked, an earlier provider verified an address (--all-providers asks each)")
            continue
        try:
            email, status = find_fn(keys, a.first, a.last, domain)
        except NetError as e:
            print(f"  {name}: skipped, {e}")
            continue
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            print(f"  {name}: skipped, its reply had an unexpected shape ({type(e).__name__}: {e}); "
                  f"note it in playbooks/sources.md")
            continue
        print(f"  {name}: {email or 'nothing found'}" + (f" ({status})" if email else ""))
        if email:
            email = email.lower()
            if email.rsplit("@", 1)[-1] != domain:
                print(f"    {email} is not at {domain}: ignored (a placeholder or another company's)")
                continue
            ev.setdefault(email, {"pattern_votes": dict(pats).get(pattern_of(email, a.first, a.last), 0)})
            ev[email].setdefault("providers", {})[name] = status
            if email not in cands:
                cands.insert(0, email)
    mx, spf = dns_mail(domain)
    prov = provider_of(mx)
    print(f"mail: {prov}" + (f" ({PROBE_NOTES[prov]})" if prov in PROBE_NOTES else ""))
    if not mx:
        print(f"  {domain} receives no mail. Find the real mail domain: SPF of the site, "
              f"mailto links on the careers page")
    if a.no_probe or not mx:
        pr = None
    else:
        pr = probe(cands[:6], mx)
        if pr["error"]:
            print(f"probe: {pr['error']}")
        else:
            print("probe: domain is " + {True: "ACCEPT-ALL (a yes proves nothing)", False: "strict",
                                         None: "unclear (its answer for a made-up address was neither "
                                               "yes nor no, so a yes proves little)"}[pr["catch_all"]])
            for c, r in pr["results"].items():
                ev[c]["probe"] = r
                ev[c]["catch_all"] = pr["catch_all"]
    print("candidates:")
    ranked = sorted(cands, key=lambda c: ("High", "Medium", "Low").index(grade(c, ev[c])))
    for c in ranked:
        e = ev[c]
        why = []
        if e.get("site"):
            why.append("published on the company site")
        if e.get("pattern_votes"):
            why.append(f"fits the pattern of {e['pattern_votes']} known address(es)")
        for n, s in (e.get("providers") or {}).items():
            why.append(f"{n}: {s}")
        if e.get("probe"):
            why.append(f"probe: {e['probe']}")
        print(f"  {grade(c, e):6}  {c}  " + ("; ".join(why) or "pattern guess only"))
    best = ranked[0]
    print(f"BEST {best} {grade(best, ev[best])}")


def pattern_of(addr, first, last):
    local = addr.split("@")[0]
    f, lasts = _parts(first, last)
    for p in PATTERNS:
        if any(_local(p, f, l) == local for l in lasts):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("first"), f.add_argument("last"), f.add_argument("domain")
    f.add_argument("--known", action="append", default=[])
    f.add_argument("--no-probe", action="store_true")
    f.add_argument("--providers", help="comma list, e.g. prospeo,hunter; default every configured one")
    f.add_argument("--all-providers", action="store_true")
    f.add_argument("--no-site", action="store_true", help="skip the company-site scan (already done)")
    s = sub.add_parser("site")
    s.add_argument("domain"), s.add_argument("--url", action="append", default=[])
    g = sub.add_parser("github")
    g.add_argument("org"), g.add_argument("domain")
    gu = sub.add_parser("guess")
    gu.add_argument("first"), gu.add_argument("last"), gu.add_argument("domain")
    gu.add_argument("--known", action="append", default=[])
    m = sub.add_parser("mx")
    m.add_argument("domain")
    p = sub.add_parser("probe")
    p.add_argument("email", nargs="+"), p.add_argument("--from", dest="sender", default="")
    sub.add_parser("providers")
    a = ap.parse_args(sys.argv[1:])

    if a.cmd == "find":
        cmd_find(a)
    elif a.cmd == "site":
        found, seen, errors = site(a.domain, a.url)
        print(f"{seen} pages read, {len(errors)} unreachable")
        for addr, url in found.items():
            print(f"  {addr}  {'(generic box)' if is_generic(addr) else ''}  {url}")
        if not found:
            print("  no address published on these pages")
    elif a.cmd == "github":
        people = github(a.org, a.domain)
        for email, name in people.items():
            print(f"  {name} <{email}>")
        if not people:
            print(f"  no commit author at {a.domain} in the org's recent public repos")
    elif a.cmd == "guess":
        known = [parse_known(k) for k in a.known]
        pats = infer(known, check_domain(a.domain))
        if known:
            print("pattern: " + (", ".join(f"{p} x{n}" for p, n in pats) or "none of the known addresses fit a pattern"))
        for c in candidates(a.first, a.last, a.domain, known)[:10]:
            print(f"  {c}")
    elif a.cmd == "mx":
        mx, spf = dns_mail(a.domain)
        prov = provider_of(mx)
        print(f"mx={','.join(mx) or 'none'}")
        print(f"provider={prov}" + (f"  ({PROBE_NOTES[prov]})" if prov in PROBE_NOTES else ""))
        print(f"spf_includes={','.join(spf) or 'none'}")
    elif a.cmd == "probe":
        doms = {e.split("@")[-1].lower() for e in a.email}
        if len(doms) != 1 or not all(ADDR.fullmatch(e) for e in a.email):
            die("probe takes addresses at one domain, e.g. dana@acme.com d.levi@acme.com")
        mx, _ = dns_mail(doms.pop())
        r = probe([e.lower() for e in a.email], mx, a.sender)
        if r["error"]:
            print(f"probe unavailable: {r['error']}")
            return
        print("domain: " + {True: "accept-all (a yes proves nothing)", False: "strict",
                            None: "unknown (its answer for a made-up address was neither yes nor no, "
                                  "so a yes proves little)"}[r["catch_all"]])
        for e, v in r["results"].items():
            print(f"  {e}  {v}")
    elif a.cmd == "providers":
        provs = configured()
        for name, (keys, _, _) in PROVIDERS.items():
            if name in provs:
                try:
                    left = provs[name][2](provs[name][0])
                except NetError as e:
                    left = f"credit check failed: {e}"
                print(f"  {name:10} configured  {left}")
            else:
                print(f"  {name:10} not configured (add {', '.join(keys)} to .env)")


if __name__ == "__main__":
    run(main)
