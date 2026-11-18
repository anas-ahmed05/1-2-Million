"""MindMesh web interface (presentation only).

render_html(S) turns the saved state (plan, messages, trace, runs) into one
self-contained HTML page. It never computes plan figures itself; every number
comes from engine/solver.py via S["plan"]. The same page is served live by
ui/server.py (with the message composer) or opened as a read-only snapshot.
"""
import html
import json

from engine.solver import clock, rs

E = html.escape

AREAS = ("reading", "venue", "schedule", "food", "judging", "budget")
STATUS_LABEL = {"used": "Used", "superseded": "Superseded", "irrelevant": "Irrelevant", "rejected": "Rejected"}

LOGO = """<svg class="mark" viewBox="0 0 32 32" width="{s}" height="{s}" aria-hidden="true">
<path d="M5 25V8l11 10 11-10v17" fill="none" stroke="#292B27" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>
<path d="M5 8h22" stroke="#C9C3B5" stroke-width="1.2" stroke-dasharray="1.5 2.5" stroke-linecap="round"/>
<circle cx="5" cy="25" r="2.6" fill="#596B4F"/><circle cx="5" cy="8" r="2.6" fill="#596B4F"/>
<circle cx="27" cy="8" r="2.6" fill="#596B4F"/><circle cx="27" cy="25" r="2.6" fill="#596B4F"/>
<circle cx="16" cy="18" r="3.4" fill="#B8755B"/><circle cx="16" cy="18" r="1.3" fill="#FFFFFF"/></svg>"""

ICON_OK = ('<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" '
           'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
ICON_BAD = ('<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4.5 4.5l7 7m0-7l-7 7" '
            'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>')


def _n(x):
    return f"{x:,}" if isinstance(x, (int, float)) else E(str(x))


def _tag(area):
    a = area if area in AREAS else "reading"
    return f'<span class="tag a-{a}"><i></i>{E(str(area))}</span>'


def _badge(status):
    return f'<span class="badge s-{E(status)}">{E(STATUS_LABEL.get(status, status.title()))}</span>'


def _card(title, body, aside="", cls=""):
    return (f'<section class="card {cls}"><header class=card-h><h3>{title}</h3>'
            f'{f"<span class=aside>{aside}</span>" if aside else ""}</header><div class=card-b>{body}</div></section>')


# ------------------------------------------------------------------ plan tab
def _verdict(S, p):
    b, sc = p["budget"], p["schedule"]
    ok = sum(c["ok"] for c in p["checks"])
    n = len(p["checks"])
    last = S["runs"][-1] if S["runs"] else None
    when = f'Run {last["run"]} &middot; {"full plan" if last["kind"] == "full" else "update"}' if last else ""
    if p["valid"]:
        title, cls, icon = "Plan validated", "ok", ICON_OK
        line = f"All {n} constraint checks pass"
    else:
        title, cls, icon = "Plan needs attention", "bad", ICON_BAD
        line = f"{n - ok} of {n} constraint checks failing"
    return (f'<div class="verdict {cls}"><div class=v-icon>{icon}</div><div class=v-body><h2>{title}</h2>'
            f'<p>{line} &middot; {rs(b["spent"])} committed of {rs(b["total"])} &middot; '
            f'{clock(sc["start"])} &ndash; {clock(sc["end"])}</p></div><div class=v-side>{when}</div></div>')


def _kpis(p):
    fg, v, fd, j, b = p["figures"], p["venue"], p["food"], p["judging"], p["budget"]
    pct = min(100, round(100 * b["spent"] / b["total"])) if b["total"] else 0
    items = fd.get("items") or []
    cells = [
        ("People on site", _n(fg["onsite"]),
         f'{fg["students"]} students &middot; {fg["teams"]} teams of {fg["team_size"]}'),
        ("Venue", E(str(v["name"] or "None")), f'{v["capacity"]} seats &middot; {v["spare"]} spare'),
        ("Meals", _n(fd["quantity"]), f'{len(items)} menu item{"s" * (len(items) != 1)} &middot; {rs(fd["cost"])}'),
        ("Judges booked", _n(j["used"]), f'of {j["available"]} confirmed &middot; {j["teams_per_judge"]} teams each'),
        ("Budget committed", rs(b["spent"]),
         f'of {rs(b["total"])} &middot; {pct}%<span class=meter><span style="width:{pct}%"></span></span>'),
    ]
    return '<div class=kpis>' + "".join(
        f'<div class=kpi><span class=k-l>{l}</span><span class="k-v num">{v_}</span><span class=k-s>{s}</span></div>'
        for l, v_, s in cells) + '</div>'


def _checks(p):
    rows = "".join(
        f'<li class="{"ok" if c["ok"] else "bad"}"><span class=glyph>{ICON_OK if c["ok"] else ICON_BAD}</span>'
        f'<div><b>{E(c["label"])}</b><span>{E(c["detail"])}</span></div></li>' for c in p["checks"])
    ok = sum(c["ok"] for c in p["checks"])
    return _card("Constraint checks", f'<ul class=checks>{rows}</ul>', f'{ok} / {len(p["checks"])} passing')


def _triage(S, p):
    """Message triage (how the reader classified every message) + any conflicts."""
    msgs = S["messages"]
    counts = {s: sum(1 for m in msgs if m.get("status") == s) for s in STATUS_LABEL}
    n = max(1, len(msgs))
    bars = "".join(
        f'<div class=tri><span class="badge s-{s}">{STATUS_LABEL[s]}</span>'
        f'<span class=tri-bar><span class="tb-{s}" style="width:{100 * counts[s] / n:.1f}%"></span></span>'
        f'<b class=num>{counts[s]}</b></div>' for s in STATUS_LABEL)
    conflicts = _conflict_items(S, p)
    tail = (conflicts if conflicts else
            '<p class="calm ok-line">' + ICON_OK + ' No conflicts. Every applied message is consistent with '
            'the plan and its rules.</p>')
    has = bool(conflicts)
    return _card("Message triage" + (" &amp; conflicts" if has else ""),
                 f'<div class=triage>{bars}</div><div class=tri-sep></div>{tail}',
                 f'{len(msgs)} message{"s" * (len(msgs) != 1)} read', "conflict" if has else "")


def _conflict_items(S, p):
    rej = [m for m in S["messages"] if m.get("status") == "rejected"]
    failed = [c for c in p["checks"] if not c["ok"]]
    if not rej and not failed:
        return ""
    items = []
    for c in failed:
        items.append(f'<li><span class="badge s-rejected">Check failing</span><div><b>{E(c["label"])}</b>'
                     f'<span>{E(c["detail"])}</span></div></li>')
    for m in rej:
        items.append(f'<li><span class="badge s-rejected">Rejected</span><div><b>{E(str(m.get("from")))}'
                     f'<em> &middot; {E(str(m.get("date") or ""))}</em></b><span>{E(str(m.get("note") or ""))}</span></div></li>')
    note = ("Rejected messages were not applied; the last valid plan was kept." if rej else "")
    return (f'<ul class=conflicts>{"".join(items)}</ul>'
            + (f'<p class=footnote>{note} <a href="#messages">View all messages</a></p>' if note else ""))


def _block_kind(b):
    name = b["name"].lower()
    if b["name"] == "Build time":
        return "build"
    if name.startswith("judging"):
        return "judging"
    if b.get("source") == "planner" and ("opening" in name or "closing" in name):
        return "ceremony"
    return "break"


def _schedule(p):
    sc = p["schedule"]
    total = max(1, sc["end"] - sc["start"])
    segs = []
    for b in sc["blocks"]:
        w = 100 * b["minutes"] / total
        left = 100 * (b["start"] - sc["start"]) / total
        k = _block_kind(b)
        label = E(b["name"].split(" - ")[0])
        segs.append(f'<span class="seg k-{k}" style="left:{left:.3f}%;width:{w:.3f}%" '
                    f'title="{clock(b["start"])}&ndash;{clock(b["end"])} &middot; {E(b["name"])} ({b["minutes"]} min)">'
                    f'{f"<em>{label}</em>" if w >= 9 else ""}</span>')
    ticks = []
    h = (sc["start"] // 60 + (1 if sc["start"] % 60 else 0)) * 60
    while h <= sc["end"]:
        hh = (h // 60) % 24
        ticks.append(f'<span style="left:{100 * (h - sc["start"]) / total:.3f}%"'
                     f'{" class=last" if sc["end"] - h < 20 else ""}>'
                     f'{hh % 12 or 12} {"AM" if hh < 12 else "PM"}</span>')
        h += 60
    legend = "".join(f'<span><i class="k-{k}"></i>{t}</span>' for k, t in
                     (("build", "Build"), ("break", "Breaks &amp; required blocks"), ("judging", "Judging"),
                      ("ceremony", "Opening / closing")))
    rows = "".join(
        f'<tr><td class="num nowrap">{clock(b["start"])} &ndash; {clock(b["end"])}</td>'
        f'<td><i class="sw k-{_block_kind(b)}"></i>{E(b["name"])}</td><td class="num r">{b["minutes"]} min</td>'
        f'<td class=r><span class="src src-{E(b.get("source", ""))}">{E(b.get("source", ""))}</span></td></tr>'
        for b in sc["blocks"])
    body = (f'<div class=timeline>{"".join(segs)}</div><div class=ticks>{"".join(ticks)}</div>'
            f'<div class=legend>{legend}</div>'
            f'<div class=tbl><table><thead><tr><th>Time</th><th>Block</th><th class=r>Length</th>'
            f'<th class=r>Source</th></tr></thead><tbody>{rows}</tbody></table></div>')
    return _card("Schedule", body, f'{clock(sc["start"])} &ndash; {clock(sc["end"])} &middot; '
                                   f'{sc["build_minutes"]} min build time', "wide")


def _venue(S, p):
    v = p["venue"]
    facts = {str(x.get("name")): x for x in (S["facts"] or {}).get("venues") or [] if isinstance(x, dict)}
    rows = []
    if v["name"]:
        rows.append(f'<tr class=sel><td><b>{E(str(v["name"]))}</b></td><td class="num r">{v["capacity"]}</td>'
                    f'<td class="num r">{rs(v["cost"])}</td><td><span class="badge s-used">Selected</span></td></tr>')
    for a in v["alternatives"]:
        f = facts.get(str(a["name"]), {})
        cap, cost = f.get("capacity"), f.get("cost")
        rows.append(f'<tr><td>{E(str(a["name"]))}</td><td class="num r muted">{_n(cap) if cap is not None else "&ndash;"}</td>'
                    f'<td class="num r muted">{rs(cost) if isinstance(cost, int) else "&ndash;"}</td>'
                    f'<td class=muted>{E(a["why"])}</td></tr>')
    feats = ", ".join(map(str, v["features"])) if v["features"] else ""
    body = (f'<div class=tbl><table><thead><tr><th>Venue</th><th class=r>Seats</th><th class=r>Cost</th><th>Decision</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            + (f'<p class=footnote>Features: {E(feats)}</p>' if feats else ""))
    return _card("Venue", body, f'{p["figures"]["onsite"]} people to seat')


def _food(p):
    fd = p["food"]
    items = fd.get("items") or [{"name": fd["name"], "qty": fd["quantity"], "price": fd["price"], "diet": None}]
    def diet(i):
        return f' <span class=diet>{E(str(i["diet"]))}</span>' if i.get("diet") else ""

    rows = "".join(
        f'<tr><td>{E(str(i["name"]))}{diet(i)}</td>'
        f'<td class="num r">{i["qty"]}</td><td class="num r">{rs(i["price"])}</td>'
        f'<td class="num r">{rs(i["qty"] * i["price"])}</td></tr>' for i in items)
    if fd["fixed_fee"]:
        rows += f'<tr><td>Delivery / fixed fee</td><td></td><td></td><td class="num r">{rs(fd["fixed_fee"])}</td></tr>'
    rows += f'<tr class=tot><td>Total</td><td class="num r">{fd["quantity"]}</td><td></td><td class="num r">{rs(fd["cost"])}</td></tr>'
    body = (f'<div class=tbl><table><thead><tr><th>Item</th><th class=r>Qty</th><th class=r>Unit</th>'
            f'<th class=r>Subtotal</th></tr></thead><tbody>{rows}</tbody></table></div>')
    return _card("Catering", body, f'{p["figures"]["fed"]} people to feed')


def _judging(p):
    j, fg = p["judging"], p["figures"]
    per_team = f' &times; {j["judges_per_team"]} judges' if j["judges_per_team"] != 1 else ""
    rows = [
        ("Confirmed", f'{j["available"]} judges'),
        ("Needed", f'{j["needed"]} <span class=muted>({fg["teams"]} teams{per_team}'
                   f' &divide; {j["max_teams_per_judge"] or "&ndash;"} each)</span>'),
        ("Booked", f'{j["used"]} judges'),
        ("Load", f'{j["teams_per_judge"]} teams each &times; {j["minutes_per_team"]} min'),
        ("Judging window", f'{j["window_minutes"]} min, judges in parallel'),
        ("Honoraria", f'{j["used"]} &times; {rs(j["honorarium"])} = <b>{rs(j["cost"])}</b>'),
    ]
    body = '<dl class=facts>' + "".join(f'<dt>{k}</dt><dd class=num>{v}</dd>' for k, v in rows) + '</dl>'
    return _card("Judging", body)


def _budget(p):
    b = p["budget"]
    total = max(1, b["total"])
    by = {}
    for ln in b["lines"]:
        by[ln["area"]] = by.get(ln["area"], 0) + ln["amount"]
    names = {"venue": "Venue", "food": "Catering", "judging": "Judging", "budget": "Other costs"}
    segs = "".join(f'<span class="a-{a}" style="width:{100 * by[a] / total:.3f}%" title="{names[a]}: {rs(by[a])}"></span>'
                   for a in ("venue", "food", "judging", "budget") if by.get(a))
    left = max(0, b["remaining"])
    segs += f'<span class=free style="width:{100 * left / total:.3f}%" title="Remaining: {rs(left)}"></span>'
    legend = "".join(f'<span><i class="a-{a}"></i>{names[a]} <b class=num>{rs(by[a])}</b></span>'
                     for a in ("venue", "food", "judging", "budget") if by.get(a))
    legend += f'<span><i class=free></i>Remaining <b class=num>{rs(b["remaining"])}</b></span>'
    rows = "".join(f'<tr><td>{E(ln["item"])}</td><td>{_tag(ln["area"])}</td><td class="num r">{rs(ln["amount"])}</td></tr>'
                   for ln in b["lines"])
    rows += "".join(f'<tr class=declined><td><s>{E(str(d["item"]))}</s> <em>declined, {E(d["why"])}</em></td>'
                    f'<td>{_tag("budget")}</td><td class="num r"><s>{rs(d["amount"])}</s></td></tr>' for d in b["declined"])
    rem_cls = "ok" if b["remaining"] >= b["reserve"] else "bad"
    rows += (f'<tr class=tot><td>Total committed</td><td></td><td class="num r">{rs(b["spent"])}</td></tr>'
             f'<tr class=sub><td>Approved budget</td><td></td><td class="num r">{rs(b["total"])}</td></tr>'
             + (f'<tr class=sub><td>Reserve held back</td><td></td><td class="num r">{rs(b["reserve"])}</td></tr>' if b["reserve"] else "")
             + f'<tr class="sub rem {rem_cls}"><td>Remaining</td><td></td><td class="num r">{rs(b["remaining"])}</td></tr>')
    body = (f'<div class=stack>{segs}</div><div class=legend>{legend}</div>'
            f'<div class=tbl><table><thead><tr><th>Line item</th><th>Area</th><th class=r>Amount</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    return _card("Budget", body, f'{rs(b["spent"])} of {rs(b["total"])}', "wide")


def _reasoning(p):
    if not p["decisions"] and not p["assumptions"]:
        return ""
    rows = "".join(f'<li>{_tag(a)}<span>{E(t)}</span></li>' for a, t in p["decisions"])
    rows += "".join(f'<li><span class="tag a-assume"><i></i>assumption</span><span>{E(t)}</span></li>'
                    for t in p["assumptions"])
    return _card("Reasoning", f'<ul class=reasons>{rows}</ul>', "Why the planner chose this", "wide")


def _empty(title, text, steps=None):
    s = ""
    if steps:
        s = '<ol class=steps>' + "".join(f"<li><span>{x}</span></li>" for x in steps) + '</ol>'
    return (f'<div class=empty>{LOGO.format(s=56)}<h2>{title}</h2><p>{text}</p>{s}</div>')


def _plan_tab(S):
    p = S["plan"]
    if not p:
        return _empty("No plan yet",
                      "MindMesh reads a pack of event messages, extracts the facts, resolves conflicts and builds a "
                      "validated plan for venue, schedule, catering, judging and budget.",
                      ["Paste the full message pack in the <b>Inbox</b>, or load a .txt file.",
                       "Click <b>Build plan</b>. One model call reads the messages; code does every calculation.",
                       "Add new messages one at a time. Each is accepted, ignored or rejected with a reason."])
    return (_verdict(S, p) + _kpis(p) +
            '<div class=grid2>' + _checks(p) + _triage(S, p) + '</div>' +
            _schedule(p) +
            '<div class=grid3>' + _venue(S, p) + _food(p) + _judging(p) + '</div>' +
            _budget(p) + _reasoning(p))


# ------------------------------------------------------------------ messages tab
def _messages_tab(S):
    msgs = S["messages"]
    if not msgs:
        return _empty("No messages yet", "Messages appear here after the first run, each with the status the "
                                         "reader gave it and the reason.")
    counts = {}
    for m in msgs:
        counts[m.get("status")] = counts.get(m.get("status"), 0) + 1
    chips = f'<button class=on data-f=all>All <b>{len(msgs)}</b></button>' + "".join(
        f'<button data-f="{s}">{STATUS_LABEL[s]} <b>{counts[s]}</b></button>'
        for s in ("used", "superseded", "irrelevant", "rejected") if counts.get(s))
    rows = []
    for m in msgs:
        st = str(m.get("status") or "")
        is_new = str(m.get("id", "")).startswith("N")
        rows.append(
            f'<article class="msg st-{E(st)}" data-status="{E(st)}"><div class=m-id>{E(str(m.get("id")))}</div>'
            f'<div class=m-main><div class=m-head><b>{E(str(m.get("from")))}</b>'
            f'<span class=muted>{E(str(m.get("date") or ""))}</span>'
            f'{"<span class=newtag>new message</span>" if is_new else ""}{_badge(st)}</div>'
            f'<p class=m-note>{E(str(m.get("note") or ""))}</p>'
            + (f'<blockquote>{E(m["text"])}</blockquote>' if m.get("text") else "")
            + f'</div><div class=m-run>run {m.get("run")}</div></article>')
    log = ""
    if S["updates"]:
        res_cls = lambda r: "rejected" if "reject" in r else ("used" if "updated" in r else "irrelevant")
        lr = "".join(f'<tr><td class=num>Run {u["run"]}</td><td>{E(u["source"])}</td>'
                     f'<td><span class="badge s-{res_cls(u["result"])}">{E(u["result"])}</span></td>'
                     f'<td>{" ".join(_tag(a) for a in u["areas"]) or "&ndash;"}</td></tr>' for u in S["updates"])
        log = _card("Change log", f'<div class=tbl><table><thead><tr><th>Run</th><th>Source</th><th>Result</th>'
                                  f'<th>Areas touched</th></tr></thead><tbody>{lr}</tbody></table></div>',
                    f'{len(S["updates"])} update{"s" * (len(S["updates"]) != 1)} after the first run')
    return (f'<div class=filters role=group aria-label="Filter messages">{chips}</div>'
            f'<div class="card list">{"".join(rows)}</div>{log}')


# ------------------------------------------------------------------ trace tab
def _pretty(out):
    try:
        return json.dumps(json.loads(out), indent=2, ensure_ascii=False), True
    except Exception:
        return out, False


def _trace_tab(S):
    ev = S["trace"]
    calls = [e for e in ev if e["type"] == "call"]
    if not ev:
        return _empty("No trace yet", "Every model call is recorded here: number, model, area, full input and "
                                      "output, and token counts exactly as the provider reports them.")
    pt = sum(e["prompt_tokens"] or 0 for e in calls)
    ct = sum(e["completion_tokens"] or 0 for e in calls)
    tt = sum(e["total_tokens"] or 0 for e in calls)
    models = sorted({e["model"] for e in calls})
    stats = [("Model calls", _n(len(calls))), ("Total tokens", _n(tt)), ("Prompt", _n(pt)),
             ("Completion", _n(ct)), ("Runs", _n(len(S["runs"])))]
    head = ('<div class=tstats>' + "".join(f'<div><span>{l}</span><b class=num>{v}</b></div>' for l, v in stats)
            + f'<div class=wide><span>Model{"s" * (len(models) != 1)}</span><b class=mono>{E(", ".join(models) or "-")}</b></div></div>')
    runs = {r["run"]: r for r in S["runs"]}
    groups, cur = [], None
    for e in ev:
        if e["type"] == "run" or cur is None or e["run"] != cur["run"]:
            cur = {"run": e["run"], "title": e.get("text", ""), "items": []}
            groups.append(cur)
            if e["type"] == "run":
                continue
        cur["items"].append(e)
    out = []
    for g in reversed(groups):
        r = runs.get(g["run"], {})
        kind = "Full plan" if r.get("kind") == "full" else "Update"
        meta = (f'{E(str(r.get("source", "")))} &middot; {r.get("seconds", "?")} s &middot; '
                f'{r.get("calls", 0)} call{"s" * (r.get("calls", 0) != 1)} &middot; {_n(r.get("tokens", 0))} tokens')
        items = []
        for e in g["items"]:
            if e["type"] == "call":
                body, is_json = _pretty(e["output"])
                items.append(
                    f'<details class=call id="c{e["n"]}"><summary><span class=cn>#{e["n"]}</span>{_tag(e["area"])}'
                    f'<span class="mono model">{E(e["model"])}</span>'
                    f'<span class="ctok num"><b>{_n(e["total_tokens"])}</b> tokens <em>prompt {_n(e["prompt_tokens"])} '
                    f'&middot; completion {_n(e["completion_tokens"])} &middot; {e["seconds"]} s</em></span></summary>'
                    f'<div class=io><details class=sys id="s{e["n"]}"><summary>Input &middot; system prompt '
                    f'<em>{len(e["input"]["system"]):,} chars</em></summary><pre>{E(e["input"]["system"])}</pre></details>'
                    f'<h5>Input &middot; user</h5><pre>{E(e["input"]["user"])}</pre>'
                    f'<h5>Output{" &middot; JSON, formatted for reading (raw in output/trace.txt)" if is_json else ""}</h5>'
                    f'<pre>{E(body)}</pre></div></details>')
            elif e["type"] == "reject":
                items.append(f'<div class="tl reject">{_tag(e["area"])}<span><b>Rejected.</b> {E(e["text"])}</span></div>')
            elif e["type"] == "total":
                items.append(f'<div class="tl total"><span class=mono>{E(e["text"])}</span></div>')
            else:
                items.append(f'<div class=tl>{_tag(e["area"])}<span>{E(e["text"])}</span></div>')
        out.append(f'<section class="card run"><header class=run-h><div><span class=eyebrow>Run {g["run"]} &middot; {kind}</span>'
                   f'<p class=muted>{meta}</p></div></header><div class=run-b>{"".join(items)}</div></section>')
    tools = '<div class=ttools><button class="btn ghost sm" id=expand>Expand all calls</button></div>'
    return head + tools + "".join(out)


# ------------------------------------------------------------------ chrome
def _composer(S):
    has_plan = S["facts"] is not None
    return (f'<section class="card composer live-only" id=composer data-mode="{"update" if has_plan else "full"}">'
            f'<header class=card-h><h3>Inbox</h3><span class=aside>{"Update mode" if has_plan else "New event"}</span></header>'
            f'<div class=card-b><p class=hint>{"Paste one new message exactly as received. MindMesh checks it against the "
                                               "plan and applies, ignores or rejects it." if has_plan else
                                               "Paste the full message pack exactly as received. MindMesh reads it once "
                                               "and builds the plan."}</p>'
            f'<textarea id=msg spellcheck=false placeholder="{"Paste a new message…" if has_plan else "Paste the message pack…"}"></textarea>'
            f'<div class=c-row><label class="btn ghost sm"><input type=file id=file accept=".txt,text/plain">Load .txt</label>'
            f'<span id=srcname class=muted></span><span id=chars class="muted num"></span></div>'
            f'<button class="btn primary block" id=run><span class=spin></span><span class=lbl>'
            f'{"Process message" if has_plan else "Build plan"}</span></button>'
            f'<p class=kbd>Ctrl + Enter to run</p><div id=cmsg class=cmsg role=status aria-live=polite></div></div>'
            f'<footer class=card-f><button class="btn link" id=reset>Start new event</button>'
            f'<span class=muted>Clears plan &amp; trace</span></footer></section>'
            f'<section class="card snapshot file-only"><div class=card-b><b>Read-only snapshot</b>'
            f'<p class=muted>Run <code>python plan.py</code> and open http://127.0.0.1:8000 to add messages.</p>'
            f'<button class="btn ghost sm" id=auto></button></div></section>')


def _history(S):
    if not S["runs"]:
        return ""
    upd = {u["run"]: u["result"] for u in S["updates"]}
    rows = []
    for r in reversed(S["runs"]):
        if r["kind"] == "full":
            res = "plan built" if S["plan"] else "stopped"
            cls = "used" if S["plan"] else "rejected"
        else:
            res = upd.get(r["run"], "stopped")
            cls = "rejected" if ("reject" in res or res == "stopped") else ("used" if "updated" in res else "irrelevant")
        rows.append(f'<li><div><b>Run {r["run"]}</b> <span class=muted>{"Full plan" if r["kind"] == "full" else "Update"}</span>'
                    f'<span class="badge s-{cls}">{E(res)}</span></div>'
                    f'<p class="muted num">{E(str(r["source"]))} &middot; {r["seconds"]} s &middot; {r["calls"]} call'
                    f'{"s" * (r["calls"] != 1)} &middot; {_n(r["tokens"])} tok</p></li>')
    return _card("Run history", f'<ul class=history>{"".join(rows)}</ul>', f'{len(S["runs"])} run{"s" * (len(S["runs"]) != 1)}')


def render_html(S):
    p = S["plan"]
    calls = [e for e in S["trace"] if e["type"] == "call"]
    tokens = sum(e["total_tokens"] or 0 for e in calls)
    models = sorted({e["model"] for e in calls})
    nrej = sum(1 for m in S["messages"] if m.get("status") == "rejected")
    if p:
        status = (f'<span class="chip status ok"><i class=dot></i>Plan valid</span>' if p["valid"] else
                  f'<span class="chip status bad"><i class=dot></i>Needs attention</span>')
    else:
        status = '<span class="chip status"><i class=dot></i>No plan</span>'
    meta = (f'<span class="chip num">{len(calls)} call{"s" * (len(calls) != 1)} &middot; {tokens:,} tokens</span>'
            + (f'<span class="chip mono hide-sm">{E(models[-1] if len(models) == 1 else f"{len(models)} models")}</span>' if models else ""))
    tabs = (f'<nav class=tabs role=tablist><a href="#plan">Plan</a>'
            f'<a href="#messages">Messages <span class=count>{len(S["messages"])}</span>'
            f'{f"<span class=alert>{nrej} rejected</span>" if nrej else ""}</a>'
            f'<a href="#trace">Trace <span class=count>{len(calls)}</span></a></nav>')
    return (
        '<!doctype html><html lang=en><head><meta charset=utf-8>'
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        '<title>MindMesh</title>'
        '<link rel=icon href="data:image/svg+xml,' + LOGO.format(s=32).replace('"', "'").replace("#", "%23").replace("\n", "") + '">'
        '<link rel=preconnect href="https://fonts.googleapis.com"><link rel=preconnect href="https://fonts.gstatic.com" crossorigin>'
        '<link rel=stylesheet href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&'
        'family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap">'
        f'<style>{CSS}</style></head>'
        f'<body data-mode="{"update" if S["facts"] is not None else "full"}">'
        f'<header class=top><div class=top-in><a class=brand href="#plan">{LOGO.format(s=30)}<b>MindMesh</b></a>'
        f'<span class=tagline>Intelligence that connects the dots.</span>'
        f'<div class=top-meta>{status}{meta}</div></div></header>'
        f'<div class=shell><aside>{_composer(S)}{_history(S)}</aside>'
        f'<main id=main>{tabs}<div class=busy-veil><div><span class=spin></span><b>Reading messages&hellip;</b>'
        f'<p>One model call reads the text; the plan is recomputed in code. The trace also prints in the terminal.</p></div></div>'
        f'<section class=tab id=tab-plan>{_plan_tab(S)}</section>'
        f'<section class=tab id=tab-messages hidden>{_messages_tab(S)}</section>'
        f'<section class=tab id=tab-trace hidden>{_trace_tab(S)}</section>'
        f'<footer class=foot>{LOGO.format(s=16)}<span>MindMesh &middot; plan figures computed in code, '
        f'messages read by the model &middot; full trace saved to output/final_report.txt</span></footer></main></div>'
        f'<div id=toast class=toast role=status aria-live=polite></div>'
        f'<script>{JS}</script></body></html>')


# ------------------------------------------------------------------ design system
CSS = """
:root{
 --paper:#F5F3ED;--surface:#FFFFFF;--sunk:#FAF9F5;--ink:#292B27;--ink2:#53554F;--muted:#85857D;
 --line:#E6E2D9;--line2:#D8D3C7;
 --olive:#596B4F;--olive-ink:#45543D;--olive-soft:#EDF0E8;--olive-line:#D3DBCB;
 --terra:#B8755B;--terra-ink:#95553E;--terra-soft:#F7EDE7;--terra-line:#EBD2C6;
 --ochre:#A3864C;--ochre-ink:#7C6533;--ochre-soft:#F4EEDF;
 --slate:#5F6C72;--slate-soft:#E7EBEB;--stone-soft:#EEECE6;
 --serif:"Newsreader",Georgia,"Times New Roman",serif;
 --sans:"IBM Plex Sans",-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 --mono:"IBM Plex Mono",ui-monospace,"Cascadia Mono",Consolas,monospace;
 --r:12px;--r2:8px;--shadow:0 1px 2px rgba(41,43,39,.04),0 2px 8px rgba(41,43,39,.04);
}
*{box-sizing:border-box}html{color-scheme:light;scroll-padding-top:80px}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
a{color:var(--olive-ink);text-underline-offset:3px}
.num{font-variant-numeric:tabular-nums}.mono{font-family:var(--mono);font-size:.92em}
.muted{color:var(--muted)}.nowrap{white-space:nowrap}.r{text-align:right}
code{font-family:var(--mono);font-size:12px;background:var(--stone-soft);padding:1px 5px;border-radius:4px}
[hidden]{display:none!important}

/* top bar */
.top{position:sticky;top:0;z-index:30;background:rgba(245,243,237,.9);backdrop-filter:saturate(1.2) blur(8px);border-bottom:1px solid var(--line)}
.top-in{max-width:1400px;margin:0 auto;padding:12px 28px;display:flex;align-items:center;gap:18px}
.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none}
.brand b{font:600 22px/1 var(--serif);letter-spacing:-.015em}
.tagline{color:var(--muted);font:italic 400 14px/1 var(--serif);padding-left:18px;border-left:1px solid var(--line2)}
.top-meta{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.chip{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 11px;border:1px solid var(--line);
 border-radius:999px;background:var(--surface);font-size:12.5px;color:var(--ink2);white-space:nowrap}
.chip .dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
.chip.status{font-weight:600}
.chip.status.ok{background:var(--olive-soft);border-color:var(--olive-line);color:var(--olive-ink)}.chip.status.ok .dot{background:var(--olive)}
.chip.status.bad{background:var(--terra-soft);border-color:var(--terra-line);color:var(--terra-ink)}.chip.status.bad .dot{background:var(--terra)}

/* shell */
.shell{max-width:1400px;margin:0 auto;padding:28px;display:grid;grid-template-columns:330px minmax(0,1fr);gap:28px;align-items:start}
aside{position:sticky;top:84px;display:flex;flex-direction:column;gap:18px}
main{position:relative;min-width:0}

/* cards */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);margin-bottom:20px;min-width:0}
aside .card{margin:0}
.card-h{display:flex;align-items:baseline;gap:12px;padding:16px 20px 0}
.card-h h3{margin:0;font:600 11.5px/1.3 var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--ink2)}
.card-h .aside{margin-left:auto;font-size:12.5px;color:var(--muted);text-align:right}
.card-b{padding:12px 20px 18px}
.card-f{display:flex;align-items:center;gap:10px;padding:12px 20px;border-top:1px solid var(--line);background:var(--sunk);border-radius:0 0 var(--r) var(--r);font-size:12.5px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
.grid2>.card,.grid3>.card{margin-bottom:20px}
.footnote{margin:10px 0 0;font-size:12.5px;color:var(--muted)}
.eyebrow{font:600 11.5px/1.3 var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--ink2)}

/* tabs */
.tabs{display:flex;gap:26px;border-bottom:1px solid var(--line2);margin:0 0 22px}
.tabs a{display:inline-flex;align-items:center;gap:8px;padding:2px 0 12px;color:var(--muted);text-decoration:none;
 font:500 15px/1.2 var(--sans);border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs a:hover{color:var(--ink)}
.tabs a.on{color:var(--ink);border-color:var(--ink)}
.count{font-size:11.5px;padding:1px 7px;border-radius:999px;background:var(--stone-soft);color:var(--ink2);font-variant-numeric:tabular-nums}
.alert{font-size:11.5px;padding:1px 7px;border-radius:999px;background:var(--terra-soft);color:var(--terra-ink);font-weight:600}

/* buttons */
.btn{font:500 13px/1 var(--sans);display:inline-flex;align-items:center;justify-content:center;gap:8px;height:36px;padding:0 14px;
 border-radius:var(--r2);border:1px solid var(--line2);background:var(--surface);color:var(--ink);cursor:pointer;transition:background .15s,border-color .15s}
.btn:hover{border-color:var(--muted)}.btn:focus-visible,textarea:focus-visible,.tabs a:focus-visible,.filters button:focus-visible{outline:2px solid var(--olive);outline-offset:2px}
.btn.primary{background:var(--ink);border-color:var(--ink);color:#F5F3ED;height:42px;font-weight:600;font-size:14px}
.btn.primary:hover{background:#3A3C37}
.btn.block{width:100%}.btn.sm{height:30px;padding:0 11px;font-size:12.5px}
.btn.ghost{background:transparent}.btn.link{border:0;background:none;padding:0;height:auto;color:var(--terra-ink);font-weight:600}
.btn.link:hover{text-decoration:underline}
.btn:disabled{opacity:.6;cursor:progress}
.btn input[type=file]{display:none}
.spin{display:none;width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.busy .btn.primary .spin{display:inline-block}

/* composer */
.composer .hint{margin:0 0 10px;color:var(--ink2);font-size:13px}
.composer textarea{width:100%;min-height:190px;resize:vertical;padding:12px;border:1px solid var(--line2);border-radius:var(--r2);
 background:var(--sunk);color:var(--ink);font:12.5px/1.55 var(--mono)}
.composer textarea::placeholder{color:#A9A79E}
.c-row{display:flex;align-items:center;gap:10px;margin:10px 0 12px;font-size:12.5px;min-height:30px}
#chars{margin-left:auto}
.kbd{margin:8px 0 0;text-align:center;font-size:11.5px;color:var(--muted)}
.cmsg{font-size:13px;margin-top:10px}.cmsg:empty{display:none}
.cmsg.err{padding:10px 12px;border-radius:var(--r2);background:var(--terra-soft);color:var(--terra-ink);border:1px solid var(--terra-line)}
.cmsg.run{color:var(--ink2)}
.snapshot p{margin:4px 0 10px;font-size:12.5px}
.file-only{display:none}body.file .file-only{display:block}body.file .live-only{display:none}

/* history */
.history{list-style:none;margin:0;padding:0}
.history li{padding:10px 0;border-top:1px solid var(--line)}.history li:first-child{border-top:0;padding-top:2px}
.history li>div{display:flex;align-items:center;gap:8px}.history .badge{margin-left:auto}
.history p{margin:3px 0 0;font-size:12px;overflow-wrap:anywhere}

/* badges & tags */
.badge{display:inline-flex;align-items:center;height:22px;padding:0 9px;border-radius:999px;font-size:11.5px;font-weight:600;white-space:nowrap;border:1px solid transparent}
.s-used{background:var(--olive-soft);color:var(--olive-ink);border-color:var(--olive-line)}
.s-superseded{background:var(--ochre-soft);color:var(--ochre-ink);border-color:#E8DCC0}
.s-irrelevant{background:var(--stone-soft);color:var(--ink2);border-color:var(--line)}
.s-rejected{background:var(--terra-soft);color:var(--terra-ink);border-color:var(--terra-line)}
.tag{display:inline-flex;align-items:center;gap:6px;font:500 11.5px/1 var(--mono);color:var(--ink2);white-space:nowrap}
.tag i{width:7px;height:7px;border-radius:2px;background:var(--muted)}
.a-reading i,i.a-reading{background:var(--muted)}.a-venue i{background:var(--olive)}.a-schedule i{background:var(--ochre)}
.a-food i{background:var(--terra)}.a-judging i{background:var(--slate)}.a-budget i{background:var(--ink)}.a-assume i{background:#C9C3B5}

/* verdict */
.verdict{display:flex;align-items:center;gap:18px;padding:22px 24px;border-radius:var(--r);border:1px solid;margin-bottom:20px}
.verdict.ok{background:var(--olive-soft);border-color:var(--olive-line)}
.verdict.bad{background:var(--terra-soft);border-color:var(--terra-line)}
.v-icon{flex:none;width:42px;height:42px;border-radius:50%;display:grid;place-items:center;color:#fff}
.verdict.ok .v-icon{background:var(--olive)}.verdict.bad .v-icon{background:var(--terra)}
.v-icon svg{width:20px;height:20px}
.v-body h2{margin:0;font:500 27px/1.15 var(--serif);letter-spacing:-.015em}
.v-body p{margin:4px 0 0;color:var(--ink2)}
.v-side{margin-left:auto;font-size:12.5px;color:var(--ink2);text-align:right}

/* kpis */
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));background:var(--surface);border:1px solid var(--line);border-radius:var(--r);margin-bottom:20px;box-shadow:var(--shadow)}
.kpi{padding:16px 18px;border-left:1px solid var(--line);display:flex;flex-direction:column;gap:4px;min-width:0}
.kpi:first-child{border-left:0}
.k-l{font:600 11px/1.3 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.k-v{font:500 25px/1.15 var(--serif);letter-spacing:-.01em;overflow-wrap:anywhere}
.k-s{font-size:12.5px;color:var(--ink2)}
.meter{display:block;height:4px;background:var(--stone-soft);border-radius:2px;margin-top:8px;overflow:hidden}
.meter span{display:block;height:100%;background:var(--olive)}

/* checks & conflicts */
.checks,.conflicts,.reasons{list-style:none;margin:0;padding:0}
.checks li{display:flex;gap:12px;padding:9px 0;border-top:1px solid var(--line)}.checks li:first-child{border-top:0;padding-top:2px}
.glyph{flex:none;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;margin-top:1px}
.checks li.ok .glyph{background:var(--olive-soft);color:var(--olive)}.checks li.bad .glyph{background:var(--terra);color:#fff}
.checks b,.conflicts b{display:block;font-weight:600;font-size:13.5px}
.checks span,.conflicts span{display:block;font-size:12.5px;color:var(--ink2)}
.checks li.bad span{color:var(--terra-ink)}
.card.conflict{border-color:var(--terra-line)}
.card.conflict .card-h h3{color:var(--terra-ink)}
.conflicts li{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--line)}
.conflicts li:first-child{border-top:0;padding-top:2px}.conflicts em{font-style:normal;color:var(--muted);font-weight:400}
.calm{margin:4px 0}

/* tables */
.tbl{overflow-x:auto;margin:0 -4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{font:600 11px/1.3 var(--sans);letter-spacing:.07em;text-transform:uppercase;color:var(--muted);text-align:left;padding:8px 4px;border-bottom:1px solid var(--line2)}
th.r{text-align:right}
td{padding:9px 4px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tr.sel td{background:var(--olive-soft)}tr.sel td:first-child{box-shadow:inset 3px 0 0 var(--olive)}
tr.tot td{border-top:1px solid var(--line2);font-weight:600}
tr.sub td{color:var(--ink2);border-bottom:0;padding-top:4px;padding-bottom:4px}
tr.rem.ok td{color:var(--olive-ink);font-weight:600}tr.rem.bad td{color:var(--terra-ink);font-weight:600}
tr.declined td{color:var(--muted)}tr.declined em{font-style:normal;font-size:12px}
.diet{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--olive-soft);color:var(--olive-ink);margin-left:4px}
.src{font:500 11px/1 var(--mono);color:var(--muted)}.src-message{color:var(--terra-ink)}.src-computed{color:var(--slate)}

/* facts list */
.facts{display:grid;grid-template-columns:auto 1fr;gap:9px 16px;margin:0;font-size:13px}
.facts dt{color:var(--muted)}.facts dd{margin:0;text-align:right}

/* timeline */
.timeline{position:relative;height:46px;border-radius:var(--r2);background:var(--stone-soft);overflow:hidden;margin-top:4px}
.seg{position:absolute;top:0;bottom:0;border-right:2px solid var(--surface);display:flex;align-items:center;padding:0 8px;overflow:hidden}
.seg em{font-style:normal;font-size:11.5px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.k-build{background:#DFE5D8;color:var(--olive-ink)}.k-break{background:#F1E4C9;color:var(--ochre-ink)}
.k-judging{background:#D9E0E1;color:#3F4A50}.k-ceremony{background:#E4E0D6;color:var(--ink2)}
.ticks{position:relative;height:20px;margin-top:6px;font:11px/1 var(--mono);color:var(--muted)}
.ticks span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.ticks span:first-child{transform:none}.ticks span.last{transform:translateX(-100%)}
.triage{display:grid;gap:9px}
.tri{display:grid;grid-template-columns:96px 1fr 28px;align-items:center;gap:12px}
.tri b{text-align:right;font-weight:600}.tri .badge{justify-self:start}
.tri-bar{height:6px;border-radius:3px;background:var(--stone-soft);overflow:hidden}.tri-bar span{display:block;height:100%}
.tb-used{background:var(--olive)}.tb-superseded{background:var(--ochre)}.tb-irrelevant{background:#B9B5AA}.tb-rejected{background:var(--terra)}
.tri-sep{height:1px;background:var(--line);margin:16px 0 12px}
.ok-line{display:flex;gap:8px;align-items:flex-start;color:var(--olive-ink);font-size:13px}.ok-line svg{flex:none;margin-top:3px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:8px 0 14px;font-size:12px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
.sw{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:9px;vertical-align:1px}

/* budget stack */
.stack{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--stone-soft);margin-top:4px}
.stack span{height:100%;border-right:2px solid var(--surface)}.stack span:last-child{border-right:0}
.stack .a-venue,.legend i.a-venue{background:var(--olive)}.stack .a-food,.legend i.a-food{background:var(--terra)}
.stack .a-judging,.legend i.a-judging{background:var(--slate)}.stack .a-budget,.legend i.a-budget{background:var(--ink)}
.stack .free,.legend i.free{background:repeating-linear-gradient(135deg,#E9E5DB 0 4px,#F4F1EA 4px 8px)}
.legend b{font-weight:600;color:var(--ink);margin-left:2px}

/* reasoning */
.reasons li{display:grid;grid-template-columns:110px 1fr;gap:12px;padding:8px 0;border-top:1px solid var(--line);font-size:13px}
.reasons li:first-child{border-top:0;padding-top:2px}
.reasons .tag{padding-top:2px}

/* messages */
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.filters button{font:500 12.5px/1 var(--sans);height:32px;padding:0 13px;border-radius:999px;border:1px solid var(--line2);
 background:var(--surface);color:var(--ink2);cursor:pointer}
.filters button b{font-weight:600;color:var(--ink);margin-left:3px}
.filters button.on{background:var(--ink);border-color:var(--ink);color:#F5F3ED}.filters button.on b{color:#F5F3ED}
.list{padding:4px 0}
.msg{display:grid;grid-template-columns:44px 1fr auto;gap:14px;padding:16px 20px;border-top:1px solid var(--line)}
.msg:first-child{border-top:0}
.msg.st-rejected{box-shadow:inset 3px 0 0 var(--terra);background:linear-gradient(90deg,#FBF4F0,transparent 40%)}
.m-id{font:500 12px/22px var(--mono);color:var(--muted)}
.m-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px}.m-head .badge{margin-left:auto}
.m-note{margin:4px 0 0;color:var(--ink2);font-size:13px}
.msg blockquote{margin:10px 0 0;padding:10px 14px;border-left:2px solid var(--line2);background:var(--sunk);
 font:12.5px/1.55 var(--mono);color:var(--ink2);white-space:pre-wrap;border-radius:0 var(--r2) var(--r2) 0}
.m-run{font:12px/22px var(--mono);color:var(--muted);white-space:nowrap}
.newtag{font-size:11px;color:var(--olive-ink);font-weight:600;letter-spacing:.03em}

/* trace */
.tstats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr)) 1.6fr;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);margin-bottom:14px;box-shadow:var(--shadow)}
.tstats div{padding:14px 16px;border-left:1px solid var(--line);min-width:0}.tstats div:first-child{border-left:0}
.tstats span{display:block;font:600 11px/1.3 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.tstats b{display:block;font:500 22px/1.3 var(--serif);overflow-wrap:anywhere}.tstats b.mono{font:500 12.5px/1.5 var(--mono);padding-top:6px}
.ttools{display:flex;justify-content:flex-end;margin-bottom:12px}
.run-h{display:flex;align-items:center;padding:16px 20px 12px;border-bottom:1px solid var(--line)}
.run-h p{margin:3px 0 0;font-size:12.5px}
.run-b{padding:8px 20px 14px}
.tl{display:grid;grid-template-columns:96px 1fr;gap:12px;padding:7px 0;font-size:13px;border-top:1px dashed var(--line)}
.tl:first-child{border-top:0}
.tl.reject{background:var(--terra-soft);border:1px solid var(--terra-line);border-radius:var(--r2);padding:9px 12px;margin:6px 0;color:var(--terra-ink)}
.tl.total{grid-template-columns:1fr;font-weight:500;color:var(--ink);border-top:1px solid var(--line2);margin-top:4px;padding-top:10px}
details.call{border:1px solid var(--line2);border-radius:var(--r2);margin:8px 0;background:var(--sunk)}
details.call>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;padding:11px 14px}
details.call>summary::-webkit-details-marker{display:none}
details.call>summary::after{content:"";margin-left:auto;width:8px;height:8px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(-45deg);transition:transform .15s}
details.call[open]>summary::after{transform:rotate(45deg)}
.cn{font:600 13px/1 var(--mono)}.model{color:var(--ink2)}
.ctok b{font-weight:600}.ctok em{font-style:normal;color:var(--muted);font-size:12px;margin-left:6px}
.io{padding:0 14px 14px;border-top:1px solid var(--line)}
.io h5{margin:14px 0 6px;font:600 11px/1.3 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.io pre{margin:0;padding:12px 14px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);
 font:12px/1.55 var(--mono);white-space:pre-wrap;word-break:break-word;max-height:440px;overflow:auto;color:var(--ink)}
details.sys{margin-top:12px}details.sys>summary{cursor:pointer;font:600 11px/1.3 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:2px 0 6px}
details.sys>summary em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;margin-left:6px}

/* empty / busy / toast / footer */
.empty{text-align:center;padding:56px 24px;background:var(--surface);border:1px dashed var(--line2);border-radius:var(--r)}
.empty h2{font:500 26px/1.2 var(--serif);margin:16px 0 6px}
.empty p{max-width:520px;margin:0 auto;color:var(--ink2)}
.steps{max-width:460px;margin:22px auto 0;padding:0;text-align:left;counter-reset:s;list-style:none}
.steps li{counter-increment:s;display:grid;grid-template-columns:28px 1fr;gap:10px;padding:8px 0;color:var(--ink2);font-size:13.5px}
.steps li::before{content:counter(s);width:24px;height:24px;border-radius:50%;background:var(--stone-soft);display:grid;place-items:center;font:600 12px/1 var(--mono);color:var(--ink)}
.busy-veil{display:none;position:absolute;inset:44px 0 auto 0;z-index:5;min-height:260px;background:rgba(245,243,237,.78);backdrop-filter:blur(1.5px);border-radius:var(--r)}
.busy-veil>div{position:sticky;top:120px;max-width:380px;margin:60px auto;text-align:center;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:22px;box-shadow:var(--shadow)}
.busy-veil .spin{display:inline-block;width:20px;height:20px;color:var(--olive);margin-bottom:8px}
.busy-veil b{display:block;font:500 19px/1.3 var(--serif)}.busy-veil p{margin:6px 0 0;font-size:12.5px;color:var(--ink2)}
.busy .busy-veil{display:block}
.toast{position:fixed;right:24px;bottom:24px;z-index:50;max-width:420px;padding:12px 16px;border-radius:var(--r2);background:var(--ink);color:#F5F3ED;
 font-size:13px;box-shadow:0 8px 30px rgba(41,43,39,.18);opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .2s,transform .2s}
.toast.show{opacity:1;transform:none}.toast.ok{border-left:4px solid #9DB08F}.toast.bad{border-left:4px solid var(--terra)}
.foot{display:flex;align-items:center;gap:10px;padding:8px 0 24px;color:var(--muted);font-size:12px}

/* responsive */
@media (max-width:1180px){.grid3{grid-template-columns:repeat(2,minmax(0,1fr))}.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}
 .kpi:nth-child(4){border-left:0}.kpi:nth-child(n+4){border-top:1px solid var(--line)}
 .tstats{grid-template-columns:repeat(3,minmax(0,1fr))}.tstats div:nth-child(4){border-left:0}.tstats div:nth-child(n+4){border-top:1px solid var(--line)}}
@media (max-width:980px){.shell{grid-template-columns:minmax(0,1fr);padding:18px 16px;gap:18px}aside{position:static;min-width:0}
 .top-meta{min-width:0}
 .tagline,.hide-sm{display:none}.top-in{padding:10px 16px}.grid2,.grid3{grid-template-columns:1fr;gap:0}
 .composer textarea{min-height:140px}}
@media (max-width:640px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.kpi{border-left:0!important;border-top:1px solid var(--line)}
 .kpi:nth-child(-n+2){border-top:0}.kpi:nth-child(even){border-left:1px solid var(--line)!important}
 .tstats{grid-template-columns:repeat(2,minmax(0,1fr))}.tstats div{border-left:0!important;border-top:1px solid var(--line)}
 .tstats div:nth-child(-n+2){border-top:0}.verdict{flex-wrap:wrap;padding:18px}.v-side{margin-left:0;text-align:left}
 .v-body h2{font-size:23px}.tabs{gap:18px}.msg{grid-template-columns:1fr;gap:6px;padding:14px 16px}.m-run{display:none}
 .reasons li,.tl{grid-template-columns:1fr;gap:4px}.chip.num{display:none}.toast{left:16px;right:16px}}
"""

JS = r"""
(()=>{
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const live=location.protocol.startsWith('http');
if(!live)document.body.classList.add('file');
const TABS=['plan','messages','trace'];
function show(){const h=(location.hash||'#plan').slice(1),t=TABS.includes(h)?h:'plan';
 $$('.tabs a').forEach(a=>{const on=a.hash==='#'+t;a.classList.toggle('on',on);a.setAttribute('aria-selected',on)});
 $$('.tab').forEach(s=>s.hidden=s.id!=='tab-'+t)}
addEventListener('hashchange',show);show();
$$('.filters button').forEach(b=>b.onclick=()=>{$$('.filters button').forEach(x=>x.classList.toggle('on',x===b));
 const f=b.dataset.f;$$('.msg').forEach(r=>r.hidden=f!=='all'&&r.dataset.status!==f)});
const ex=$('#expand');if(ex)ex.onclick=()=>{const o=ex.dataset.open!=='1';$$('details.call').forEach(d=>d.open=o);
 ex.dataset.open=o?'1':'0';ex.textContent=o?'Collapse all calls':'Expand all calls'};
const toastEl=$('#toast');function toast(t,k){toastEl.textContent=t;toastEl.className='toast show '+(k||'');
 clearTimeout(toastEl._t);toastEl._t=setTimeout(()=>toastEl.className='toast',6000)}
try{const f=sessionStorage.getItem('mm-flash');if(f){const o=JSON.parse(f);toast(o.t,o.k);sessionStorage.removeItem('mm-flash')}}catch(e){}
function keepView(){try{sessionStorage.setItem('mm-y',scrollY);
 sessionStorage.setItem('mm-open',JSON.stringify($$('details[open]').map(d=>d.id).filter(Boolean)))}catch(e){}}
try{JSON.parse(sessionStorage.getItem('mm-open')||'[]').forEach(id=>{const d=document.getElementById(id);if(d)d.open=true});
 const y=sessionStorage.getItem('mm-y');if(y)scrollTo(0,+y);sessionStorage.removeItem('mm-y')}catch(e){}
if(live){
 const ta=$('#msg'),btn=$('#run'),lbl=btn.querySelector('.lbl'),cm=$('#cmsg'),chars=$('#chars'),srcEl=$('#srcname');
 const label=lbl.textContent;let src='pasted text';
 const upd=()=>{const n=ta.value.length;chars.textContent=n?n.toLocaleString()+' chars':''};
 ta.addEventListener('input',()=>{src='pasted text';srcEl.textContent='';upd()});
 $('#file').onchange=e=>{const f=e.target.files[0];if(!f)return;f.text().then(t=>{ta.value=t.replace(/^﻿/,'');
  src=f.name;srcEl.textContent=f.name;upd();ta.focus()});e.target.value=''};
 async function run(){if(!ta.value.trim()){cm.className='cmsg err';cm.textContent='Paste a message or load a .txt file first.';ta.focus();return}
  btn.disabled=true;document.body.classList.add('busy');cm.className='cmsg run';const t0=Date.now();
  const tick=()=>{const s=((Date.now()-t0)/1000).toFixed(0);lbl.textContent='Working… '+s+' s';cm.textContent='Reading '+
   ta.value.length.toLocaleString()+' characters. Limit: '+(document.body.dataset.mode==='update'?'1 minute':'2 minutes')+'.'};
  tick();const iv=setInterval(tick,500);
  try{const r=await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:ta.value,src})});
   const j=await r.json();clearInterval(iv);if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
   const what=j.kind==='full'?'Plan built':'Message processed';
   sessionStorage.setItem('mm-flash',JSON.stringify({t:`Run ${j.run} · ${what} in ${j.seconds} s · ${Number(j.tokens).toLocaleString()} tokens · plan ${j.valid?'valid':'needs attention'}`,k:j.valid?'ok':'bad'}));
   keepView();location.reload();
  }catch(e){clearInterval(iv);document.body.classList.remove('busy');btn.disabled=false;lbl.textContent=label;
   cm.className='cmsg err';cm.textContent='Could not run: '+e.message+'. The existing plan is unchanged.'}}
 btn.onclick=run;ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();run()}});
 $('#reset').onclick=async()=>{if(!confirm('Start a new event? This clears the current plan, messages and trace.'))return;
  try{const r=await fetch('/reset',{method:'POST',body:'{}'});if(!r.ok)throw new Error('HTTP '+r.status);
   sessionStorage.setItem('mm-flash',JSON.stringify({t:'New event started. Paste the message pack to build a plan.',k:'ok'}));
   location.hash='#plan';location.reload()}catch(e){toast('Reset failed: '+e.message,'bad')}};
}else{
 const a=$('#auto');let on=false;try{on=localStorage.getItem('mm-auto')==='1'}catch(e){}
 const lab=()=>a.textContent='Auto-refresh: '+(on?'on':'off');lab();
 a.onclick=()=>{on=!on;try{localStorage.setItem('mm-auto',on?'1':'0')}catch(e){};lab()};
 setInterval(()=>{if(on){keepView();location.reload()}},5000);
}
})();
"""
