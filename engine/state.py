"""Saved state between runs, so a new message updates the existing plan."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
STATE = os.path.join(OUT, "state.json")
FILES = ("state.json", "plan.json", "trace.txt", "final_report.txt", "report.html")


def empty():
    return {"facts": None, "plan": None, "messages": [], "updates": [], "trace": [], "runs": []}


def load():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    return empty()


def save(S):
    os.makedirs(OUT, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(S, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def reset():
    for f in FILES:
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            os.remove(p)
