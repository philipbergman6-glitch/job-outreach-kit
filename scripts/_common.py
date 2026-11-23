"""Shared helpers. Stdlib only."""
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def die(msg, code=2):
    print(f"HARD-FAIL: {msg}", file=sys.stderr)
    sys.exit(code)


def run(main):
    """Run a script's main(); turn any unexpected error into one HARD-FAIL line.
    Set KIT_DEBUG=1 to see the full traceback instead. A blocked network (NetBlocked) is an
    expected failure with its own explanation: always one line, never a traceback."""
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted")
    except NetBlocked as e:
        die(str(e))
    except Exception as e:
        if os.environ.get("KIT_DEBUG"):
            raise
        die(f"unexpected {type(e).__name__}: {e}. Nothing further was done. "
            f"Rerun with KIT_DEBUG=1 for details")


def _read_env():
    """KEY=VALUE pairs from <repo>/.env, or None when the file is absent.
    Tolerates a byte-order mark, `export KEY=`, quotes, and a trailing ` # comment`."""
    path = ROOT / ".env"
    if not path.exists():
        return None
    vals = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.startswith("export "):
            k = k[len("export "):].strip()
        if v and v[0] in "\"'" and v.find(v[0], 1) > 0:
            v = v[1:v.find(v[0], 1)]
        else:
            v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
        vals[k] = v
    return vals


def env(*names):
    """Require the given names in <repo>/.env and return all its values."""
    vals = _read_env()
    if vals is None:
        die(".env missing: copy .env.example to .env and fill it in")
    missing = [n for n in names if not vals.get(n)]
    if missing:
        die(f"{', '.join(missing)} missing or empty in .env")
    return vals

class NetError(Exception):
    """A network call failed. Callers decide whether that ends the run or only that source.
    status: the HTTP status when the server answered with an error, else None; reply: its text."""
    def __init__(self, msg, status=None, reply=""):
        super().__init__(msg)
        self.status, self.reply = status, reply


def in_cloud():
    """True inside a Claude Code cloud session (Anthropic sets CLAUDE_CODE_REMOTE=true there)."""
    return os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"


CLOUD_FIX = ("This is a Claude cloud session, not the owner's computer; the kit runs on their computer. "
             "Tell the owner, in plain words: start a new session in the Code tab, open the environment "
             "selector under the message box, choose their own computer under 'Local', pick the "
             "job-outreach-kit folder, and type 'continue'. Do not ask them to allow sites or update the "
             "environment (flow/tools.md § Cloud session)")


class NetBlocked(Exception):
    """The network itself refused the request (a proxy or firewall), so every site will fail the
    same way. Deliberately not a NetError: callers that skip one failed source must not swallow
    this; it ends the run with one plain explanation."""


def blocked(target, detail):
    if in_cloud():
        return NetBlocked(f"the internet is blocked for this session: {target} was refused ({detail}). {CLOUD_FIX}")
    return NetBlocked(f"the internet is blocked on this network: {target} was refused by a proxy or firewall "
                      f"({detail}). A work or school network may block job sites: try a home network, or "
                      f"turn off a VPN (flow/tools.md § Python setup)")


def proxy_refusal(url, e):
    """NetBlocked when exception e is a proxy refusing to open the connection to url (403 forbidden,
    407 sign-in required), else None. A 502 or 504 means the proxy could not reach the site: an
    ordinary failure of that one site. The standard library gives no status code for a refused
    tunnel, only http.client's message "Tunnel connection failed: <code> <reason>", so this matches
    that text. Names only the host: a query string can carry an API key."""
    s = str(getattr(e, "reason", "") or e)
    if not re.search(r"Tunnel connection failed: 40[37]\b", s):
        return None
    return blocked(urlsplit(url).hostname or "the site", s)


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to HTTPS on the same host: a board read never lands elsewhere."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if new.scheme != "https" or (new.hostname or "") != (old.hostname or ""):
            raise NetError(f"{req.get_method()} {req.full_url.split('?')[0]}: redirected off the board "
                           f"to {newurl.split('?')[0]}; refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


UA = "job-outreach-kit/2 (+personal job search; one request at a time)"


def ascii_url(url):
    """Percent-encode non-ASCII characters (a Hebrew job title in a link, say) so the request can
    be sent; ASCII characters, existing %-escapes included, are left as they are."""
    from urllib.parse import quote
    return url if url.isascii() else quote(url, safe="".join(chr(c) for c in range(33, 127)))


def http(url, method="GET", headers=None, body=None, timeout=30, as_json=True, pinned=False):
    """One HTTP request. Returns parsed JSON (or text). Raises NetError with the status and
    the first 300 characters of the reply, never a bare traceback; raises NetBlocked (not a
    NetError) when a proxy or firewall refuses the connection itself. pinned=True: HTTPS only,
    and a redirect must stay on the same host (job boards)."""
    import json as _json
    import urllib.error
    import urllib.request
    data = None
    hdrs = {"User-Agent": UA, "Accept": "application/json" if as_json else "*/*"}
    hdrs.update(headers or {})
    if body is not None:
        data = body if isinstance(body, bytes) else _json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    import time
    if pinned and not url.startswith("https://"):
        raise NetError(f"{method} {url.split('?')[0]}: only https:// addresses are read")
    opener = urllib.request.build_opener(SameHostRedirect) if pinned else None
    url = ascii_url(url)
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with (opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            deny = (e.headers.get("x-deny-reason") or "") if e.headers else ""
            if deny:  # the cloud proxy answering for a plain-http site it does not allow
                raise blocked(urlsplit(url).hostname or "the site", f"HTTP {e.code}, {deny}") from None
            if e.code in (429, 503) and attempt < 2:
                wait = e.headers.get("Retry-After", "")
                time.sleep(min(int(wait) if wait.isdigit() else 4 * (attempt + 1), 30))
                continue
            reply = e.read().decode("utf-8", "replace")
            full = reply
            if "<html" in reply[:500].lower():
                reply = "an HTML error page" + (" (rate limit: wait a few minutes)" if e.code == 429 else "")
            raise NetError(f"{method} {url.split('?')[0]} HTTP {e.code}: {reply[:300]}", e.code, full) from None
        except NetError:
            raise
        except Exception as e:
            refused = proxy_refusal(url, e)
            if refused:
                raise refused from None
            import ssl
            hint = ""
            if isinstance(e, ssl.SSLCertVerificationError) or isinstance(getattr(e, "reason", None),
                                                                         ssl.SSLCertVerificationError):
                hint = (". This Python cannot check secure websites: a python.org install on a Mac needs "
                        "its 'Install Certificates.command' run once; on a work network, the network may "
                        "be inspecting secure traffic (flow/tools.md § Python setup)")
            raise NetError(f"{method} {url.split('?')[0]}: {e}{hint}") from None
    text = raw.decode("utf-8", "replace")
    if not as_json:
        return text
    try:
        return _json.loads(text)
    except ValueError:
        raise NetError(f"{method} {url.split('?')[0]}: reply is not JSON: {text[:200]}") from None


def env_optional(*names):
    """The given names that are set in .env; a missing file or key is not an error."""
    vals = _read_env() or {}
    return {n: vals[n] for n in names if vals.get(n)}


LEGAL = {"inc", "ltd", "llc", "gmbh", "ag", "sa", "bv", "nv", "plc", "corp", "corporation", "co", "limited",
         "company", "srl", "oy", "ab", "se", "pty", "spa", "sas", "kg", "lp", "llp", "בעמ"}


def company_key(name):
    """A company name folded for matching: accents, case, punctuation and legal suffixes dropped."""
    s = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).casefold()
    s = re.sub("[\"'\u05f3\u05f4]", "", s)  # Hebrew abbreviation marks: בע״מ -> בעמ
    words = re.sub(r"[\W_]+", " ", s).split()  # letters of any alphabet (Hebrew too), digits
    while len(words) > 1 and words[-1] in LEGAL:
        words.pop()
    return " ".join(words)
