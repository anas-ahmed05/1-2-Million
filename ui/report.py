"""Renders the plan, the messages (incl. rejected ones) and the trace:
- plan_text(): terminal / text file
- write_all(): output/report.html (the UI), trace.txt, final_report.txt, plan.json"""
import html
import json
import os

from engine.solver import clock, rs
from engine.state import OUT
from engine.trace import format_event

E = html.escape


# ---------------------------------------------------------------- text
def plan_text(S):
    p = S["plan"]
    fg, v, fd, j, b, sc = p["figures"], p["venue"], p["food"], p["judging"], p["budget"], p["schedule"]
    L = []
    L.append("=" * 78)
    L.append(f" HACKATHON PLAN  -  {'VALID' if p['valid'] else 'NOT VALID'}")
    L.append("=" * 78)
    L.append(f" People   {fg['students']} students in {fg['teams']} teams of {fg['team_size']} + {fg['staff']} staff"
             f" + {fg['judges']} judges + {fg['others_onsite']} others = {fg['onsite']} on site, {fg['fed']} to feed")
    L.append(f" VENUE    {v['name']} - seats {v['capacity']} ({v['spare']} spare) - {rs(v['cost'])}")
    for a in v["alternatives"]:
        L.append(f"          not {a['name']}: {a['why']}")
    items = fd.get("items") or [{"name": fd["name"], "qty": fd["quantity"], "price": fd["price"], "diet": None}]
    L.append(" FOOD     " + " + ".join(f"{i['name']} x {i['qty']} @ {rs(i['price'])}"
                                       + (f" ({i['diet']})" if i["diet"] else "") for i in items)
             + (f" + fee {rs(fd['fixed_fee'])}" if fd["fixed_fee"] else "") + f" = {rs(fd['cost'])}")
    L.append(f" JUDGING  {j['used']} judges (need {j['needed']}), {j['teams_per_judge']} teams each x "
             f"{j['minutes_per_team']} min = {j['window_minutes']} min window - {rs(j['cost'])}")
    L.append(" SCHEDULE")
    for bl in sc["blocks"]:
        L.append(f"          {clock(bl['start']):>8} - {clock(bl['end']):>8}  {bl['name']} ({bl['minutes']} min)")
    L.append(" BUDGET")
    for ln in b["lines"]:
        L.append(f"          {ln['item'][:52]:<52} {rs(ln['amount']):>14}")
    for d in b["declined"]:
        L.append(f"          (declined) {str(d['item'])[:41]:<41} {rs(d['amount']):>14}")
    L.append(f"          {'TOTAL':<52} {rs(b['spent']):>14}")
    L.append(f"          {'Budget':<52} {rs(b['total']):>14}")
    L.append(f"          {'Remaining':<52} {rs(b['remaining']):>14}")
    L.append(" CHECKS")
    for ch in p["checks"]:
        L.append(f"          [{'OK' if ch['ok'] else 'XX'}] {ch['label']}: {ch['detail']}")
    rej = [m for m in S["messages"] if m.get("status") == "rejected"]
    if rej:
        L.append(" REJECTED MESSAGES")
        for m in rej:
            L.append(f"          {m.get('id')} {m.get('from')}: {m.get('note')}")
    for a in p["assumptions"]:
        L.append(f" Assumption: {a}")
    L.append("=" * 78)
    return "\n".join(L)


def trace_text(S):
    return "\n".join(format_event(e) for e in S["trace"])


# ---------------------------------------------------------------- html
CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mut:#6f6f6a;--line:#e6e6e1;--acc:#2f5bd3;
--ok:#1f7a3d;--okbg:#e3f4e8;--bad:#b42318;--badbg:#fdecea;--warn:#8a6100;--warnbg:#fdf3d7;--code:#f1f1ee}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--card:#1b1b1a;--ink:#ececea;--mut:#9a9a94;
--line:#2c2c2a;--acc:#7c9cff;--ok:#6fd08c;--okbg:#1d3324;--bad:#ff8a80;--badbg:#3a1f1d;--warn:#f0c860;
--warnbg:#3a3119;--code:#232322}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin-bottom:14px}
h1{font-size:20px;margin:0;font-weight:650}.meta{color:var(--mut);font-size:13px}
.pill{padding:3px 10px;border-radius:99px;font-weight:600;font-size:12px}
.ok{background:var(--okbg);color:var(--ok)}.bad{background:var(--badbg);color:var(--bad)}
.warn{background:var(--warnbg);color:var(--warn)}.mut{color:var(--mut)}
nav{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:16px}
nav a{padding:8px 14px;color:var(--mut);text-decoration:none;border-bottom:2px solid transparent;font-weight:550}
nav a.on{color:var(--ink);border-color:var(--acc)}
.tab{display:none}.tab.on{display:block}
.checks{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.chk{padding:6px 10px;border-radius:8px;font-size:12.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin:0 0 8px}
.big{font-size:22px;font-weight:650}.wide{grid-column:1/-1}
table{width:100%;border-collapse:collapse}td,th{padding:6px 8px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}th{font-size:12px;color:var(--mut);font-weight:600}
td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}tr.tot td{font-weight:650;border-bottom:none}
.banner{border-radius:10px;padding:10px 14px;margin-bottom:14px}
.ev{padding:5px 0;border-bottom:1px dashed var(--line);font-size:13px}
.ev .tag{display:inline-block;min-width:70px;font-size:11px;font-weight:650;color:var(--mut);text-transform:uppercase}
.run{margin:18px 0 6px;font-weight:650}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0}
summary{cursor:pointer;padding:10px 12px;font-weight:600}
pre{margin:0;padding:10px 12px;background:var(--code);white-space:pre-wrap;word-break:break-word;
font:12px/1.45 ui-monospace,Consolas,monospace;max-height:420px;overflow:auto}
.lbl{padding:6px 12px 2px;font-size:11px;font-weight:650;color:var(--mut);text-transform:uppercase}
.tool{margin-left:auto;font-size:12px;color:var(--mut)}button{font:inherit;font-size:12px;cursor:pointer;
background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:3px 8px}
#panel{display:none;margin-bottom:16px}#panel.live{display:block}
#panel textarea{width:100%;min-height:130px;resize:vertical;padding:10px;border-radius:8px;border:1px solid var(--line);
background:var(--bg);color:var(--ink);font:12.5px/1.45 ui-monospace,Consolas,monospace}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc);padding:7px 16px;font-size:13px;font-weight:600}
button.big{padding:7px 12px;font-size:13px}button:disabled{opacity:.5;cursor:wait}
#status{font-size:13px}
"""

PANEL = """
<div class=card id=panel><h2 id=ptitle>Run messages</h2>
<textarea id=msg placeholder="Paste the message pack (first run) or one new message (updates), exactly as given."></textarea>
<div class=row>
<button class=primary id=run>Run</button>
<label class=mut style="cursor:pointer"><input type=file id=file accept=".txt,text/plain" style="display:none">
<span class=chk style="border:1px solid var(--line)">Load .txt file</span></label>
<span id=srcname class=mut></span>
<button class=big id=reset style="margin-left:auto">Reset (new event)</button>
</div><div class=row><span id=status class=mut></span></div></div>
"""

PANEL_JS = """
const live=location.protocol.startsWith('http');
if(live){
 document.getElementById('panel').classList.add('live');
 const hasPlan=document.body.dataset.mode==='update';
 const btn=document.getElementById('run'), st=document.getElementById('status'), ta=document.getElementById('msg');
 let src='pasted text';
 document.getElementById('ptitle').textContent=hasPlan?'Add a new message (update)':'Paste the message pack (full run)';
 btn.textContent=hasPlan?'Run update':'Run full plan';
 ta.addEventListener('input',()=>{src='pasted text';document.getElementById('srcname').textContent=''});
 document.getElementById('file').onchange=e=>{const f=e.target.files[0];if(!f)return;
  f.text().then(t=>{ta.value=t.replace(/^\\uFEFF/,'');src=f.name;document.getElementById('srcname').textContent=f.name})};
 btn.onclick=async()=>{if(!ta.value.trim()){st.textContent='Paste a message first.';return}
  btn.disabled=true;const t0=Date.now();st.textContent='Running... (trace prints in the terminal too)';
  const tick=setInterval(()=>{st.textContent='Running... '+((Date.now()-t0)/1000).toFixed(0)+'s'},500);
  try{const r=await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:ta.value,src})});const j=await r.json();clearInterval(tick);
   if(!r.ok)throw new Error(j.error||r.status);
   sessionStorage.setItem('flash','Run '+j.run+' ('+j.kind+') done in '+j.seconds+'s, '+j.tokens+' tokens - plan '+(j.valid?'VALID':'NOT VALID'));
   location.reload();
  }catch(e){clearInterval(tick);st.textContent='Error: '+e.message;btn.disabled=false}};
 document.getElementById('reset').onclick=async()=>{if(!confirm('Forget the current plan and start a new event?'))return;
  await fetch('/reset',{method:'POST',body:'{}'});sessionStorage.setItem('flash','Reset done. Paste the new pack.');location.reload()};
 const fl=sessionStorage.getItem('flash');if(fl){st.textContent=fl;sessionStorage.removeItem('flash')}
}
"""

JS = """
const tabs=[...document.querySelectorAll('nav a')];
function show(){const h=(location.hash||'#plan').slice(1);
 tabs.forEach(a=>a.classList.toggle('on',a.hash==='#'+h));
 document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.id===h));}
addEventListener('hashchange',show);show();
let auto=false;
const abtn=document.getElementById('auto');
if(location.protocol.startsWith('http')){abtn.style.display='none'}
else{try{auto=localStorage.getItem('auto')!=='0'}catch(e){}}
function lab(){abtn.textContent='Auto-refresh: '+(auto?'on':'off')}lab();
abtn.onclick=()=>{auto=!auto;try{localStorage.setItem('auto',auto?'1':'0')}catch(e){};lab()};
try{const y=sessionStorage.getItem('y');if(y)scrollTo(0,+y);
 JSON.parse(sessionStorage.getItem('open')||'[]').forEach(id=>{const d=document.getElementById(id);if(d)d.open=true});}catch(e){}
setInterval(()=>{if(!auto)return;try{sessionStorage.setItem('y',scrollY);
 sessionStorage.setItem('open',JSON.stringify([...document.querySelectorAll('details[open]')].map(d=>d.id)))}catch(e){}
 location.reload()},5000);
"""

STATUS_CLS = {"used": "ok", "superseded": "warn", "irrelevant": "mut", "rejected": "bad"}


def _plan_html(S):
    p = S["plan"]
    if not p:
        return "<p class=mut>No plan yet.</p>"
    fg, v, fd, j, b, sc = p["figures"], p["venue"], p["food"], p["judging"], p["budget"], p["schedule"]
    h = ['<div class=checks>']
    for ch in p["checks"]:
        h.append(f'<span class="chk {"ok" if ch["ok"] else "bad"}" title="{E(ch["detail"])}">'
                 f'{"&#10003;" if ch["ok"] else "&#10007;"} {E(ch["label"])}</span>')
    h.append('</div>')
    rej = [m for m in S["messages"] if m.get("status") == "rejected"]
    if rej:
        h.append('<div class="banner bad"><b>Rejected messages</b> (plan kept valid):<br>' +
                 "<br>".join(f"{E(str(m.get('from')))}: {E(str(m.get('note')))}" for m in rej) +
                 ' &nbsp;<a href="#messages">details</a></div>')
    for ch in p["checks"]:
        if not ch["ok"]:
            h.append(f'<div class="banner bad">{E(ch["label"])}: {E(ch["detail"])}</div>')
    h.append('<div class=grid>')
    h.append(f'<div class=card><h2>People</h2><div class=big>{fg["onsite"]} on site</div>'
             f'<div class=mut>{fg["students"]} students &middot; {fg["teams"]} teams of {fg["team_size"]} &middot; '
             f'{fg["staff"]} staff &middot; {fg["judges"]} judges' +
             (f' &middot; {fg["others_onsite"]} others' if fg["others_onsite"] else '') +
             f'<br>{fg["fed"]} people to feed</div></div>')
    alts = "".join(f'<div class=mut>&times; {E(str(a["name"]))}: {E(a["why"])}</div>' for a in v["alternatives"])
    h.append(f'<div class=card><h2>Venue</h2><div class=big>{E(str(v["name"]))}</div>'
             f'<div>Seats {v["capacity"]} &middot; {v["spare"]} spare &middot; {rs(v["cost"])}</div>'
             + (f'<div class=mut>{E(", ".join(map(str, v["features"])))}</div>' if v["features"] else "")
             + f'<div style="margin-top:6px">{alts}</div></div>')
    items = fd.get("items") or [{"name": fd["name"], "qty": fd["quantity"], "price": fd["price"], "diet": None}]
    h.append(f'<div class=card><h2>Food</h2><div class=big>{fd["quantity"]} meals</div>' +
             "".join(f'<div>{E(str(i["name"]))}: {i["qty"]} &times; {rs(i["price"])}'
                     + (f' <span class=mut>({E(i["diet"])})</span>' if i["diet"] else '') + '</div>' for i in items) +
             (f'<div>Delivery / fee {rs(fd["fixed_fee"])}</div>' if fd["fixed_fee"] else '') +
             f'<div>Total <b>{rs(fd["cost"])}</b></div></div>')
    h.append(f'<div class=card><h2>Judging</h2><div class=big>{j["used"]} judges</div>'
             f'<div>{j["needed"]} needed &middot; {j["teams_per_judge"]} teams each (max {j["max_teams_per_judge"] or "-"})'
             f' &middot; {j["minutes_per_team"]} min per team</div>'
             f'<div>{j["window_minutes"]}-min judging window &middot; {rs(j["cost"])}</div></div>')
    rows = "".join(f'<tr><td class=r>{clock(x["start"])}</td><td class=r>{clock(x["end"])}</td>'
                   f'<td>{E(x["name"])}</td><td class=r>{x["minutes"]} min</td>'
                   f'<td class=mut>{E(x.get("source", ""))}</td></tr>' for x in sc["blocks"])
    h.append(f'<div class="card"><h2>Schedule</h2><table><tr><th class=r>From</th><th class=r>To</th>'
             f'<th>Block</th><th class=r>Length</th><th>Source</th></tr>{rows}</table></div>')
    rows = "".join(f'<tr><td>{E(l["item"])}</td><td class=mut>{l["area"]}</td><td class=r>{rs(l["amount"])}</td></tr>'
                   for l in b["lines"])
    rows += "".join(f'<tr class=mut><td><s>{E(str(d["item"]))}</s> declined: {E(d["why"])}</td><td>budget</td>'
                    f'<td class=r>{rs(d["amount"])}</td></tr>' for d in b["declined"])
    rows += (f'<tr class=tot><td>Total</td><td></td><td class=r>{rs(b["spent"])}</td></tr>'
             f'<tr class=tot><td>Budget</td><td></td><td class=r>{rs(b["total"])}</td></tr>'
             f'<tr class=tot><td>Remaining</td><td></td><td class=r style="color:var(--{"ok" if b["remaining"] >= b["reserve"] else "bad"})">'
             f'{rs(b["remaining"])}</td></tr>')
    h.append(f'<div class="card"><h2>Budget</h2><table><tr><th>Item</th><th>Area</th><th class=r>Amount</th></tr>'
             f'{rows}</table></div>')
    if p["assumptions"] or p["decisions"]:
        items = "".join(f'<div class=ev><span class=tag>{a}</span>{E(t)}</div>' for a, t in p["decisions"])
        items += "".join(f'<div class=ev><span class=tag>assume</span>{E(t)}</div>' for t in p["assumptions"])
        h.append(f'<div class="card wide"><h2>Why this plan</h2>{items}</div>')
    h.append('</div>')
    return "".join(h)


def _messages_html(S):
    rows = []
    for m in S["messages"]:
        st = m.get("status", "")
        rows.append(f'<tr><td>{E(str(m.get("id")))}</td><td>{E(str(m.get("from")))}</td>'
                    f'<td>{E(str(m.get("date") or ""))}</td>'
                    f'<td><span class="pill {STATUS_CLS.get(st, "mut")}">{E(st)}</span></td>'
                    f'<td>{E(str(m.get("note") or ""))}'
                    + (f'<div class=mut>&ldquo;{E(m["text"])}&rdquo;</div>' if m.get("text") else "")
                    + f'</td><td class=mut>run {m.get("run")}</td></tr>')
    ups = "".join(f'<tr><td>run {u["run"]}</td><td>{E(u["source"])}</td><td>{E(u["result"])}</td>'
                  f'<td>{E(", ".join(u["areas"]) or "-")}</td></tr>' for u in S["updates"])
    out = ('<div class=card><h2>Messages</h2><table><tr><th>#</th><th>From</th><th>Date</th><th>Status</th>'
           f'<th>Why</th><th>Run</th></tr>{"".join(rows)}</table></div>')
    if ups:
        out += ('<div class=card style="margin-top:14px"><h2>Updates after first run</h2><table><tr><th>Run</th>'
                f'<th>File</th><th>Result</th><th>Areas touched</th></tr>{ups}</table></div>')
    return out


def _trace_html(S):
    h, run = [], None
    for e in S["trace"]:
        if e["type"] == "run":
            h.append(f'<div class=run>Run {e["run"]}: {E(e["text"])}</div>')
        elif e["type"] == "call":
            did = f'c{e["n"]}'
            h.append(f'<details id={did}><summary>#{e["n"]} &middot; area <b>{e["area"]}</b> &middot; '
                     f'{E(e["model"])} &middot; {e["total_tokens"]} tokens '
                     f'<span class=mut>(prompt {e["prompt_tokens"]}, completion {e["completion_tokens"]}, '
                     f'{e["seconds"]}s)</span></summary>'
                     f'<div class=lbl>Input &middot; system</div><pre>{E(e["input"]["system"])}</pre>'
                     f'<div class=lbl>Input &middot; user</div><pre>{E(e["input"]["user"])}</pre>'
                     f'<div class=lbl>Output</div><pre>{E(e["output"])}</pre></details>')
        elif e["type"] == "reject":
            h.append(f'<div class="ev bad" style="padding:6px 8px;border-radius:6px"><span class=tag>rejected</span>'
                     f'[{e["area"]}] {E(e["text"])}</div>')
        elif e["type"] == "total":
            h.append(f'<div class=ev><b>{E(e["text"])}</b></div>')
        else:
            h.append(f'<div class=ev><span class=tag>{e["area"]}</span>{E(e["text"])}</div>')
    return "".join(h) or "<p class=mut>No trace yet.</p>"


def write_all(S):
    os.makedirs(OUT, exist_ok=True)
    calls = [e for e in S["trace"] if e["type"] == "call"]
    total = sum(e["total_tokens"] or 0 for e in calls)
    models = sorted({e["model"] for e in calls})
    p = S["plan"]
    status = ('<span class="pill ok">PLAN VALID</span>' if p and p["valid"]
              else '<span class="pill bad">PLAN NOT VALID</span>' if p else '<span class="pill mut">NO PLAN</span>')
    nrej = sum(1 for m in S["messages"] if m.get("status") == "rejected")
    doc = (f'<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
           f'<title>Hackathon Planner</title><style>{CSS}</style></head>'
           f'<body data-mode="{"update" if S["facts"] is not None else "full"}"><div class=wrap>'
           f'<header><h1>Hackathon Planner</h1>{status}<span class=meta>{len(S["runs"])} run(s) &middot; '
           f'{len(calls)} model call(s) &middot; {total:,} tokens &middot; {E(", ".join(models))}</span>'
           f'<span class=tool><button id=auto></button></span></header>{PANEL}'
           f'<nav><a href="#plan">Plan</a><a href="#messages">Messages{f" ({nrej} rejected)" if nrej else ""}</a>'
           f'<a href="#trace">Trace</a></nav>'
           f'<section class=tab id=plan>{_plan_html(S)}</section>'
           f'<section class=tab id=messages>{_messages_html(S)}</section>'
           f'<section class=tab id=trace>{_trace_html(S)}</section>'
           f'</div><script>{JS}{PANEL_JS}</script></body></html>')
    paths = {k: os.path.join(OUT, f) for k, f in
             (("html", "report.html"), ("trace", "trace.txt"), ("final", "final_report.txt"), ("json", "plan.json"))}
    with open(paths["html"], "w", encoding="utf-8") as fh:
        fh.write(doc)
    tt = trace_text(S)
    with open(paths["trace"], "w", encoding="utf-8-sig") as fh:
        fh.write(tt)
    with open(paths["final"], "w", encoding="utf-8-sig") as fh:
        fh.write((plan_text(S) if p else "NO PLAN") + "\n\nMESSAGES\n" +
                 "\n".join(f"  {m.get('id')} [{m.get('status')}] {m.get('from')} ({m.get('date')}): {m.get('note')}"
                           for m in S["messages"]) + "\n\nFULL TRACE\n" + tt + "\n")
    with open(paths["json"], "w", encoding="utf-8") as fh:
        json.dump({"facts": S["facts"], "plan": p}, fh, ensure_ascii=False, indent=1)
    return paths
