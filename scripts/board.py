#!/usr/bin/env python3
"""The board: outreach/board.html, every application on one page. Stdlib only.

Usage:
  board.py          build outreach/board.html from outreach/log.md, replies.md and followups.md
                    (and each application's messages.md for its contacts); open it in a browser

One row per application: company and role, date applied, stage, the manager and recruiter with
email confidence and what happened to each (emailed, nudged, replied), the reply, and the next due
action (the same reading as `tracker.py due`). Stages: needs you (a follow-up urgent, overdue or
made moot by a reply, an application gone cold, or one not in yet), reply in hand, waiting, closed.

The page works offline: no fonts, scripts or images are fetched; it follows the browser's light or
dark theme. Rebuild it after any change to the tables; never edit board.html by hand. Hard-fails,
and writes nothing, on the same bad input as tracker.py; a Status outside tracker.py's list is
printed as a WARN line and shown on the board."""
import html
import re
import sys
from pathlib import Path
from datetime import date

sys.path[:0] = [d for d in [str(Path(__file__).resolve().parent)] if d not in sys.path]  # python3 -I drops this folder

from _common import die, run
import tracker

OUT = tracker.OUT / "board.html"
STAGES = (("action", "Needs you"), ("live", "Reply in hand"), ("waiting", "Waiting"), ("closed", "Closed"))
PRESSING = ("overdue", "urgent", "answered", "cold")
NOT_IN_YET = ("started", "handoff-pending")


def esc(s):
    return html.escape(str(s), quote=True)


def link(url, text):
    """A link only for an http(s) URL; anything else is shown as text."""
    url = url.strip()
    if re.match(r"https?://[^\s\"'<>]+$", url):
        return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text)}</a>'
    return esc(text)


def stage(a, rows):
    if a["closed"]:
        return "closed"
    if a["log"]["Status"].strip().lower() in NOT_IN_YET or any(r["State"] in PRESSING for r in rows):
        return "action"
    return "live" if a["heard"] else "waiting"


def people_cell(a):
    got = tracker.recipients(a)
    if not got:
        return '<span class="quiet">none found</span>'
    return "".join(f'<div class="who"><b>{esc(label)}</b> {esc(who)}<span class="sub">{esc(state)}</span></div>'
                   for label, (who, state) in got.items())


def reply_cell(a):
    r = a["reply"]
    if not a["heard"]:
        text = r.get("Got back?", "") if r and r.get("Got back?", "").lower() not in ("no", "") else ""
        return f'<span class="quiet">{esc(text or "none yet")}</span>'
    head = " ".join(x for x in (r.get("Outcome", ""), r.get("Reply date", "")) if x)
    return f'{esc(head)}<span class="sub">{esc(r.get("Reply from", ""))}</span>' + (
        f'<span class="sub">{esc(r["Notes"])}</span>' if r.get("Notes") else "")


def next_cell(a, rows, st):
    if st == "closed":
        why = "Status closed" if a["closed_by"] == "status" else a["reply"].get("Outcome", "")
        return f'<span class="quiet">nothing: {esc(why)}</span>'
    if not rows:
        if a["log"]["Status"].strip().lower() in NOT_IN_YET:
            return "finish the application"
        return '<span class="quiet">wait</span>'
    out = []
    for r in rows[:3]:
        out.append(f'<div><span class="state {esc(r["State"])}">{esc(r["State"])}</span> {esc(r["Action"])}'
                   f'<span class="sub">{esc(r["Due"])} · {esc(r["Next"])}</span></div>')
    if len(rows) > 3:
        out.append(f'<span class="sub">and {len(rows) - 3} more</span>')
    return "".join(out)


def row_html(a, rows):
    st = stage(a, rows)
    l = a["log"]
    search = " ".join((l["Company"], l["Role"], l["Contacts"], l["Status"], a["reply"].get("Outcome", ""))).lower()
    return st, f"""<tr data-stage="{st}" data-id="{esc(a['id'])}" data-s="{esc(search)}">
<td class="co"><strong>{link(l['JD URL'], l['Company'])}</strong><span class="sub">{esc(l['Role'])}</span><span class="id">{esc(a['id'])}</span></td>
<td class="num" data-label="Applied">{esc(l['Date'])}<span class="sub">{esc(l['Apply channel'])}</span></td>
<td data-label="Stage"><span class="pill {st}">{esc(dict(STAGES)[st])}</span><span class="sub">{esc(l['Status'])}</span></td>
<td data-label="Contacts">{people_cell(a)}</td>
<td class="em" data-label="Emails">{esc(l['Emails'] or '-')}</td>
<td data-label="Reply">{reply_cell(a)}</td>
<td data-label="Next">{next_cell(a, rows, st)}</td>
</tr>"""


CSS = """
:root{--ground:#f1f2f0;--surface:#fcfcfb;--ink:#161b19;--muted:#5d6763;--line:#d6dbd8;--accent:#2b47c4;
--action:#9a5600;--action-bg:#fbe7c6;--live:#1d7444;--live-bg:#d8efe1;--waiting:#46586c;--waiting-bg:#e0e6ec;
--closed:#7f8783;--closed-bg:#e7eae8;--bad:#a1261c;color-scheme:light}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;--ground:#0f1412;
--surface:#161d1a;--ink:#e3e9e6;--muted:#95a29c;--line:#28322e;--accent:#93a3ff;--action:#f1b457;--action-bg:#3a2a0d;
--live:#74d69e;--live-bg:#163424;--waiting:#a9b8ca;--waiting-bg:#1f2a35;--closed:#7c8682;--closed-bg:#1c2421;--bad:#ff8a7e}}
:root[data-theme="dark"]{color-scheme:dark;--ground:#0f1412;--surface:#161d1a;--ink:#e3e9e6;--muted:#95a29c;
--line:#28322e;--accent:#93a3ff;--action:#f1b457;--action-bg:#3a2a0d;--live:#74d69e;--live-bg:#163424;
--waiting:#a9b8ca;--waiting-bg:#1f2a35;--closed:#7c8682;--closed-bg:#1c2421;--bad:#ff8a7e}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
padding-block:28px 48px;padding-inline:max(16px,env(safe-area-inset-left,0px)) max(16px,env(safe-area-inset-right,0px))}
.page{max-width:1300px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
h1{font-size:clamp(24px,4vw,34px);line-height:1.1;margin:0;letter-spacing:-.02em}
.facts{color:var(--muted);margin:4px 0 0;font-size:13px}
.quiet{color:var(--muted)}
.warn{border:1px solid var(--bad);color:var(--bad);background:var(--surface);border-radius:6px;padding:10px 14px;margin:0;font-size:13px}
.warn li{margin-left:1em}
.tools{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}
.chip{font:inherit;font-size:13px;color:var(--ink);cursor:pointer;border:1px solid var(--line);background:var(--surface);
border-radius:99px;padding:4px 12px}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.chip span{opacity:.7;margin-left:4px;font-variant-numeric:tabular-nums}
input[type=search]{font:inherit;font-size:13px;color:var(--ink);background:var(--surface);border:1px solid var(--line);
border-radius:6px;padding:6px 10px;width:260px;max-width:100%;margin-left:auto}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;min-width:1000px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;
padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px;overflow-wrap:anywhere}
tbody tr:last-child td{border-bottom:0}
td:first-child{box-shadow:inset 3px 0 0 var(--c,transparent)}
tr[data-stage="action"]{--c:var(--action)} tr[data-stage="live"]{--c:var(--live)} tr[data-stage="waiting"]{--c:var(--waiting-bg)}
tr[data-stage="closed"] td{color:var(--muted)}
.co{min-width:180px;max-width:260px}
.co strong{display:block}
a{color:var(--accent)}
.sub{display:block;color:var(--muted);font-size:12px}
.id{display:block;color:var(--muted);font:11px ui-monospace,Menlo,monospace}
.em{min-width:96px}
.num{white-space:nowrap;font-variant-numeric:tabular-nums}
.who+.who{margin-top:6px}
.pill{display:inline-block;white-space:nowrap;border-radius:99px;padding:1px 9px;font-size:12px;font-weight:600}
.pill.action{color:var(--action);background:var(--action-bg)} .pill.live{color:var(--live);background:var(--live-bg)}
.pill.waiting{color:var(--waiting);background:var(--waiting-bg)} .pill.closed{color:var(--closed);background:var(--closed-bg)}
.state{font:600 11px ui-monospace,Menlo,monospace;text-transform:uppercase}
.state.overdue,.state.urgent{color:var(--action)} .state.answered{color:var(--live)} .state.waiting,.state.cold{color:var(--muted)}
td div+div{margin-top:6px}
@media (max-width:700px){table{min-width:0}thead{display:none}tr,td{display:block}
tr{border-bottom:1px solid var(--line);padding:6px 0}td{border:0;padding:4px 12px}
td[data-label]::before{content:attr(data-label);display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
"""

JS = """
(function(){
  var chips=[].slice.call(document.querySelectorAll('.chip')), box=document.getElementById('q'),
      rows=[].slice.call(document.querySelectorAll('tbody tr')), shown=document.getElementById('shown'), f='all';
  function apply(){
    var q=(box.value||'').toLowerCase().trim(), n=0;
    rows.forEach(function(r){var ok=(f==='all'||r.dataset.stage===f)&&(!q||r.dataset.s.indexOf(q)>=0);r.hidden=!ok;n+=ok;});
    shown.textContent=n+' shown';
  }
  chips.forEach(function(c){c.addEventListener('click',function(){
    f=c.dataset.f; chips.forEach(function(x){x.setAttribute('aria-pressed',String(x===c));}); apply();});});
  box.addEventListener('input',apply); apply();
})();
"""


def build(today=None):
    today = today or date.today()
    apps = tracker.load(need=("log.md", "replies.md", "followups.md"))
    warns = tracker.warnings(apps)
    tracker.warn(apps)
    by_app = {}
    for r in tracker.due(today, apps):
        by_app.setdefault(r["App"], []).append(r)
    order = {k: i for i, (k, _) in enumerate(STAGES)}
    rows = [row_html(a, by_app.get(a["id"], [])) for a in apps]
    counts = {k: sum(st == k for st, _ in rows) for k, _ in STAGES}
    rows.sort(key=lambda x: order[x[0]])  # stable: log order within a stage
    chips = f'<button class="chip" data-f="all" aria-pressed="true">All<span>{len(rows)}</span></button>' + "".join(
        f'<button class="chip" data-f="{k}" aria-pressed="false">{esc(lbl)}<span>{counts[k]}</span></button>'
        for k, lbl in STAGES)
    warn_html = ('<ul class="warn">' + "".join(f"<li>{esc(w)}</li>" for w in warns) + "</ul>") if warns else ""
    body = "\n".join(h for _, h in rows) or '<tr data-stage="waiting" data-s=""><td colspan="7" class="quiet">No applications yet.</td></tr>'
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Applications board</title>
<style>{CSS}</style></head>
<body><main class="page">
<header><h1>Applications</h1>
<p class="facts">{len(apps)} applications · {counts['action']} need you · built {esc(today.isoformat())} from outreach/log.md, replies.md, followups.md</p></header>
{warn_html}
<div class="tools">{chips}<input type="search" id="q" placeholder="Search company, role, person" aria-label="Search"><span id="shown" class="quiet"></span></div>
<div class="wrap"><table>
<thead><tr><th>Company / role</th><th>Applied</th><th>Stage</th><th>Contacts</th><th>Emails</th><th>Reply</th><th>Next</th></tr></thead>
<tbody>
{body}
</tbody></table></div>
</main>
<script>{JS}</script>
</body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    return OUT


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(sys.argv) != 1:
        die(__doc__)
    out = build()
    print(f"wrote {out}")


if __name__ == "__main__":
    run(main)
