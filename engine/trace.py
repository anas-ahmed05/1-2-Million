"""The trace: every model call (numbered, model, area, input, output, tokens) plus
every code decision and every rejected message. Printed live and saved."""
import os

AREAS = ("reading", "venue", "schedule", "food", "judging", "budget")
_COLOR = os.getenv("NO_COLOR") is None
C = {"dim": "\033[2m", "b": "\033[1m", "cyan": "\033[36m", "green": "\033[32m",
     "red": "\033[31m", "yellow": "\033[33m", "x": "\033[0m"}


def c(name, s):
    return f"{C[name]}{s}{C['x']}" if _COLOR else s


def _indent(s, n=4):
    return "\n".join(" " * n + line for line in str(s).splitlines())


def format_event(e, color=False):
    k = (lambda n, s: c(n, s)) if color else (lambda n, s: s)
    if e["type"] == "call":
        head = (f"#{e['n']}  MODEL CALL  model={e['model']}  area={e['area']}  "
                f"({e['seconds']}s, run {e['run']})")
        return "\n".join([
            k("cyan", "=" * 78), k("b", k("cyan", head)), k("cyan", "-" * 78),
            k("b", "  INPUT [system]:"), k("dim", _indent(e["input"]["system"])),
            k("b", "  INPUT [user]:"), _indent(e["input"]["user"]),
            k("b", "  OUTPUT:"), _indent(e["output"]),
            k("b", f"  TOKENS (as reported by model): prompt={e['prompt_tokens']}  "
                   f"completion={e['completion_tokens']}  total={e['total_tokens']}"),
        ])
    if e["type"] == "reject":
        return k("red", f"  [REJECTED - {e['area']}] {e['text']}")
    if e["type"] == "run":
        return k("b", k("yellow", f"\n##### RUN {e['run']}: {e['text']}"))
    if e["type"] == "total":
        return k("b", f"  {e['text']}")
    return k("green", f"  [code - {e['area']}] ") + e["text"]


class Trace:
    def __init__(self, events, run_no):
        self.events, self.run = events, run_no

    def _add(self, e):
        e["run"] = self.run
        self.events.append(e)
        print(format_event(e, color=True), flush=True)

    def call(self, model, area, system, user, output, prompt_tokens, completion_tokens,
             total_tokens, seconds):
        assert area in AREAS
        n = 1 + sum(1 for e in self.events if e["type"] == "call")
        self._add({"type": "call", "n": n, "model": model, "area": area,
                   "input": {"system": system, "user": user}, "output": output,
                   "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                   "total_tokens": total_tokens, "seconds": seconds})

    def note(self, area, text):
        self._add({"type": "note", "area": area, "text": text})

    def reject(self, area, text):
        self._add({"type": "reject", "area": area, "text": text})

    def header(self, text):
        self._add({"type": "run", "text": text})

    def calls(self, run=None):
        return [e for e in self.events if e["type"] == "call" and (run is None or e["run"] == run)]

    def tokens(self, run=None):
        return sum(e["total_tokens"] or 0 for e in self.calls(run))

    def footer(self):
        n = len(self.calls(self.run))
        self._add({"type": "total", "text":
                   f"TOTAL TOKENS this run: {self.tokens(self.run)} ({n} model call{'s' * (n != 1)})"
                   f"   |   all runs: {self.tokens()} ({len(self.calls())} calls)"})
