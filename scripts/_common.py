"""Shared helpers. Stdlib only."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def die(msg, code=2):
    print(f"HARD-FAIL: {msg}", file=sys.stderr)
    sys.exit(code)


def env(*names):
    """Read KEY=VALUE pairs from <repo>/.env and require the given names."""
    path = ROOT / ".env"
    if not path.exists():
        die(".env missing: copy .env.example to .env and fill it in")
    vals = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    missing = [n for n in names if not vals.get(n)]
    if missing:
        die(f"{', '.join(missing)} missing or empty in .env")
    return vals
