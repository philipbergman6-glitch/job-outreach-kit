"""Shared helpers. Stdlib only."""
import os
import re
import sys
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
    Set KIT_DEBUG=1 to see the full traceback instead."""
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted")
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


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to HTTPS on the same host: a board read never lands elsewhere."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if new.scheme != "https" or (new.hostname or "") != (old.hostname or ""):
            raise NetError(f"{req.get_method()} {req.full_url.split('?')[0]}: redirected off the board "
                           f"to {newurl.split('?')[0]}; refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


UA = "job-outreach-kit/2 (+personal job search; one request at a time)"


def http(url, method="GET", headers=None, body=None, timeout=30, as_json=True, pinned=False):
    """One HTTP request. Returns parsed JSON (or text). Raises NetError with the status and
    the first 300 characters of the reply, never a bare traceback. pinned=True: HTTPS only,
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
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with (opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
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
