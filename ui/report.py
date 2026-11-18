"""Writes every output after a run:
- plan_text(): plain-text plan for the terminal and final_report.txt
- write_all(): output/report.html (the MindMesh interface, see ui/web.py), trace.txt,
  final_report.txt (plan + messages + full trace, the file to upload) and plan.json"""
import json
import os

from engine.solver import clock, rs
from engine.state import OUT
from engine.trace import format_event
from ui.web import render_html


# ---------------------------------------------------------------- text
def plan_text(S):
    p = S["plan"]
    fg, v, fd, j, b, sc = p["figures"], p["venue"], p["food"], p["judging"], p["budget"], p["schedule"]
    L = []
    L.append("=" * 78)
    L.append(f" MINDMESH  -  EVENT PLAN  -  {'VALID' if p['valid'] else 'NOT VALID'}")
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


def write_all(S):
    os.makedirs(OUT, exist_ok=True)
    p = S["plan"]
    paths = {k: os.path.join(OUT, f) for k, f in
             (("html", "report.html"), ("trace", "trace.txt"), ("final", "final_report.txt"), ("json", "plan.json"))}
    with open(paths["html"], "w", encoding="utf-8") as fh:
        fh.write(render_html(S))
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
