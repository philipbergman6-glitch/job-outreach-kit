"""Shared helpers. Stdlib only."""
import os
import re
import sys
from pathlib import Path

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


def env(*names):
    """Read KEY=VALUE pairs from <repo>/.env and require the given names.
    Tolerates a byte-order mark, `export KEY=`, quotes, and a trailing ` # comment`."""
    path = ROOT / ".env"
    if not path.exists():
        die(".env missing: copy .env.example to .env and fill it in")
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
    missing = [n for n in names if not vals.get(n)]
    if missing:
        die(f"{', '.join(missing)} missing or empty in .env")
    return vals
