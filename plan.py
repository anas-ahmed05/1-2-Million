"""Hackathon planner - ONE pipeline for every message:

    python plan.py <messages.txt>     command line
    python plan.py                    web interface at http://127.0.0.1:8000 (paste messages there)
    python plan.py reset              forget the plan and start a new event

* No saved plan yet  -> FULL RUN: the whole pack is read and a plan is built.
* A plan exists      -> UPDATE:   the new message(s) are checked and the plan is updated.
Both entry points call process(), so a message is handled identically either way.

Model use: exactly 1 call per run (area "reading"). Everything else is plain code.
"""
import json
import os
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine import prompts, solver, state  # noqa: E402
from engine.llm import LLM, LLMError  # noqa: E402
from engine.trace import Trace, c  # noqa: E402
from ui import report  # noqa: E402

CHECK_AREA = {"figures": "reading", "venue": "venue", "food": "food", "judges": "judging",
              "schedule": "schedule", "budget": "budget", "areas": "budget"}


def _dicts(xs):
    return [x for x in (xs or []) if isinstance(x, dict)]


def explain_plan(trace, plan):
    for area, text in plan["decisions"]:
        trace.note(area, text)
    for a in plan["assumptions"]:
        trace.note("schedule", "Assumption: " + a)
    for ch in plan["checks"]:
        if not ch["ok"]:
            trace.note(CHECK_AREA[ch["id"]], f"CHECK FAILED - {ch['label']}: {ch['detail']}")
    ok = sum(ch["ok"] for ch in plan["checks"])
    trace.note("budget", f"Plan {'VALID' if plan['valid'] else 'NOT VALID'}: "
                         f"{ok}/{len(plan['checks'])} checks pass. "
                         f"Spend {solver.rs(plan['budget']['spent'])} of {solver.rs(plan['budget']['total'])}.")


def repair_missing(facts, text, trace, llm, time_budget):
    """Safety net: if a key figure was not read, ask the model for just those fields (1 small call)."""
    ev, bu = facts["event"], facts["budget"]
    want = {}
    if not solver.num(ev.get("students")):
        want["students"] = ("event", "students")
    if not solver.num(ev.get("team_size")) and not solver.num(ev.get("teams")):
        want["team_size"] = ("event", "team_size")
    if not (ev.get("duration_minutes") or ev.get("duration_hours") or (ev.get("start_time") and ev.get("end_time"))):
        want.update({"duration_hours": ("event", "duration_hours"),
                     "duration_minutes": ("event", "duration_minutes"),
                     "start_time": ("event", "start_time"), "end_time": ("event", "end_time")})
    if not solver.num(bu.get("total")):
        want["budget_total"] = ("budget", "total")
    if not want or time_budget < 15:
        return
    trace.note("reading", f"Key facts missing after reading ({', '.join(want)}); one small repair call for just those.")
    out = llm.call_json("reading", prompts.REPAIR_SYSTEM,
                        "KEYS: " + json.dumps({k: None for k in want}) + "\n\nMESSAGES:\n" + text,
                        max_tokens=1500, time_budget=time_budget)
    got = []
    for k, (sec, field) in want.items():
        if out.get(k) not in (None, "", 0):
            facts[sec][field] = out[k]
            got.append(f"{sec}.{field} = {out[k]}")
    trace.note("reading", "Repaired: " + ("; ".join(got) or "nothing found"))


def full_run(S, text, src, trace, llm):
    t_start = time.time()
    trace.note("reading", f"Read {len(text)} characters from '{src}' exactly as given; sent raw to the model.")
    data = llm.call_json("reading", prompts.READ_SYSTEM, "MESSAGES:\n" + text, schema=prompts.READ_SCHEMA)
    facts = solver.clean({k: data.get(k) for k in solver.SECTIONS})
    repair_missing(facts, text, trace, llm, time_budget=110 - (time.time() - t_start))
    msgs = _dicts(data.get("messages"))
    for m in msgs:
        st = str(m.get("status", "")).lower()
        label = f"Message {m.get('id')} ({m.get('from')}, {m.get('date')})"
        if st == "rejected":
            trace.reject("reading", f"{label}: {m.get('note')}")
        elif st in ("superseded", "irrelevant"):
            trace.note("reading", f"{label} {st}: {m.get('note')}")
    plan = solver.build_plan(facts)
    explain_plan(trace, plan)
    S["facts"], S["plan"] = facts, plan
    S["messages"] = [{**m, "run": trace.run, "source": src} for m in msgs]


def update_run(S, text, src, trace, llm):
    trace.note("reading", f"Read new message(s) from '{src}' exactly as given. "
                          "Existing plan kept; only this message is sent with the current facts.")
    user = ("CURRENT FACTS:\n" + json.dumps(S["facts"], separators=(",", ":"), ensure_ascii=False)
            + "\n\nPLAN NOW:\n" + solver.summary(S["plan"]) + "\n\nNEW MESSAGE(S):\n" + text)
    out = llm.call_json("reading", prompts.UPDATE_SYSTEM, user, schema=prompts.UPDATE_SCHEMA, time_budget=55)
    decisions = _dicts(out.get("decisions")) or [out]
    changes = _dicts(out.get("changes"))
    accepted = [d for d in decisions if str(d.get("decision", "")).lower() == "accept"]
    area_of = {"costs": "budget", "cost": "budget", "budget": "budget", "venues": "venue", "venue": "venue",
               "food": "food", "catering": "food", "judging": "judging", "judges": "judging",
               "schedule": "schedule", "schedule_blocks": "schedule", "event": "schedule"}
    areas = sorted({area_of.get(str(a).lower().strip(), str(a).lower().strip())
                    for d in decisions for a in (d.get("areas") or []) if isinstance(a, str)}
                   | {area_of.get(str(c.get("section", "")).split(".")[0].lower(), "budget") for c in changes})
    trace.note("reading", f"Areas the message touches: {', '.join(areas) or 'none'}. "
                          "Re-planning is plain code, so no further model calls.")
    old = S["plan"]
    result = "no change"

    if accepted and changes:
        new_facts, applied = solver.apply_changes(S["facts"], changes)
        trace.note("reading", "Fact changes applied by code: " + "; ".join(applied))
        new_plan = solver.build_plan(new_facts)
        was_ok = {ch["id"]: ch["ok"] for ch in old["checks"]}
        broken = [ch for ch in new_plan["checks"] if not ch["ok"] and was_ok.get(ch["id"], True)]
        if broken:
            why = "; ".join(f"{ch['label']} would fail ({ch['detail']})" for ch in broken)
            for d in accepted:
                d["decision"] = "reject"
                d["reason"] = f"Code check: {why}"
            trace.reject(CHECK_AREA[broken[0]["id"]],
                         f"Message would make the plan invalid -> rejected, plan unchanged. {why}")
            result = "rejected by code check"
        else:
            changes = solver.diff(old, new_plan)
            S["facts"], S["plan"] = new_facts, new_plan
            for area, t in changes or [("budget", "Facts updated; no plan figure changed.")]:
                trace.note(area, "Changed - " + t)
            explain_plan(trace, new_plan)
            result = "plan updated"
    elif accepted:
        trace.note("reading", "Message accepted but changes no planning fact.")

    k = len([m for m in S["messages"] if str(m.get("id", "")).startswith("N")])
    for i, d in enumerate(decisions, 1):
        dec = str(d.get("decision", "")).lower()
        if dec == "reject" and not str(d.get("reason", "")).startswith("Code check"):
            trace.reject("reading", f"New message from {d.get('from')}: {d.get('reason')}")
            result = "rejected by model"
        elif dec == "irrelevant":
            trace.note("reading", f"New message from {d.get('from')} irrelevant: {d.get('reason')}")
        S["messages"].append({"id": f"N{k + i}", "from": d.get("from"), "date": d.get("date"),
                              "status": {"accept": "used", "reject": "rejected"}.get(dec, "irrelevant"),
                              "note": d.get("reason"), "run": trace.run, "source": src,
                              "text": text.strip()})
    S["updates"].append({"run": trace.run, "source": src, "text": text.strip(),
                         "result": result, "areas": areas})


def process(text, src):
    """THE one pipeline. The command line and the web page both call this, so every
    message is handled the same way: full run if no plan yet, otherwise an update."""
    S = state.load()
    run = len(S["runs"]) + 1
    kind = "full" if S["facts"] is None else "update"
    trace = Trace(S["trace"], run)
    trace.header(f"{'FULL RUN' if kind == 'full' else 'UPDATE'} from '{src}'")
    t0 = time.time()
    try:
        llm = LLM(trace)
        (full_run if kind == "full" else update_run)(S, text, src, trace, llm)
    except LLMError as e:
        trace.reject("reading", f"Run stopped, plan unchanged: {e}")
    except Exception as e:  # never lose the trace or the existing plan
        trace.reject("reading", f"Run stopped by an error, plan unchanged: {type(e).__name__}: {e}")
    trace.footer()
    S["runs"].append({"run": run, "kind": kind, "source": src,
                      "seconds": round(time.time() - t0, 1),
                      "calls": len(trace.calls(run)), "tokens": trace.tokens(run)})
    state.save(S)
    paths = report.write_all(S)
    if S["plan"]:
        print()
        print(report.plan_text(S))
    print(c("dim", f"\nRun {run} ({kind}) took {S['runs'][-1]['seconds']}s."))
    print(c("b", f"Saved: {paths['final']}  |  UI: {paths['html']}"))
    return {"run": run, "kind": kind, "seconds": S["runs"][-1]["seconds"],
            "tokens": S["runs"][-1]["tokens"], "valid": bool(S["plan"] and S["plan"]["valid"]),
            "paths": paths}


def main():
    os.system("")  # enable ANSI colours on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    if args and args[0].lower() == "reset":
        state.reset()
        print("State cleared. The next run will be a full run.")
        return
    if not args:  # no file: start the web interface (paste messages in the browser)
        from ui import server
        server.serve(process)
        return
    with open(args[0], encoding="utf-8-sig") as fh:
        text, src = fh.read(), os.path.basename(args[0])
    if not text.strip():
        print("No message text found.")
        return
    res = process(text, src)
    if res["kind"] == "full" and os.getenv("OPEN_BROWSER", "1") != "0":
        webbrowser.open("file:///" + res["paths"]["html"].replace("\\", "/"))


if __name__ == "__main__":
    main()
