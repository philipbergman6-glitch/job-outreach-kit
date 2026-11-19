#!/usr/bin/env python3
"""Hand one CV page to the browser's Save as PDF, without giving the browser file access.
Stdlib only.

Usage:
  cv.py serve <cv.html> [--seconds 120]

Serves that one file on this computer only (127.0.0.1, a free port), prints its URL and
returns at once. The server stops after the page loads once, or after --seconds. Any other
path answers 404. Then, in the browser tool started with --caps=pdf (flow/tools.md):
browser_navigate to the URL, browser_pdf_save to the PDF's path. The page's own @page rule
sets the paper size and margins (playbooks/cv-template.html).

Exit 2 = hard-fail (bad input)."""
import argparse
import os
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from _common import die, run


def serve_once(path, seconds):
    """Runs in a detached child: serve path until it is loaded once or the time runs out."""
    page = Path(path)
    body = page.read_bytes()
    route = "/" + urllib.parse.quote(page.name)
    state = {"served": False}

    class One(BaseHTTPRequestHandler):
        def do_GET(self):
            if urllib.parse.urlsplit(self.path).path != route:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            state["served"] = True

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), One)
    server.timeout = 0.2
    print(f"http://127.0.0.1:{server.server_address[1]}{route}", flush=True)
    sys.stdout.close()
    end = time.time() + seconds
    while not state["served"] and time.time() < end:
        server.handle_request()
    server.server_close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="serve")
    s = sub.add_parser("serve", help="serve one CV page for the browser's Save as PDF")
    s.add_argument("page")
    s.add_argument("--seconds", type=float, default=120)
    child = sub.add_parser("_child")
    child.add_argument("page")
    child.add_argument("seconds", type=float)
    a = ap.parse_args()
    if a.cmd == "_child":
        serve_once(a.page, a.seconds)
        return
    page = Path(a.page).resolve()
    if page.suffix.lower() not in (".html", ".htm"):
        die(f"{page.name} is not an .html page: cv.py serves the CV page the PDF is printed from")
    if not page.is_file() or not page.stat().st_size:
        die(f"{page} missing or empty")
    if not 0 < a.seconds < 24 * 3600:  # also refuses nan and inf
        die("--seconds must be more than 0 and under a day")
    detach = {"start_new_session": True} if os.name != "nt" else \
        {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_child", str(page), str(a.seconds)],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         text=True, **detach)
    url = p.stdout.readline().strip()
    p.stdout.close()
    if not url.startswith("http://127.0.0.1:"):
        die("the local page server did not start")
    print(url)
    print(f"Open it with browser_navigate, then browser_pdf_save; it stops after one load or {a.seconds:g} seconds.")


if __name__ == "__main__":
    run(main)
