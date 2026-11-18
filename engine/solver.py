"""Plain-code planner.

The model only READS messages and returns facts. Every number in the plan
(headcount, venue choice, food cost, judges needed, schedule times, budget)
is computed here with ordinary arithmetic, so it is exact and costs 0 tokens.
"""
import copy
import math
import re

SECTIONS = ("event", "budget", "venues", "food", "judging", "costs", "schedule_blocks", "venue_rules")

# Planner policy: choices made by THIS planner when the messages say nothing.
# These are not facts from any message pack; every use is listed under
# "assumptions" in the plan so the reader can see it.
POLICY = {
    "default_start": "10:00",
    "opening_minutes": 10,
    "lunch_minutes": 30,
    "closing_minutes": 15,
    "min_build_minutes": 60,
    "first_build_share": 0.7,          # where lunch/breaks sit in the build time
    "include_optional_if_affordable": True,
}


# ---------------------------------------------------------------- helpers
def num(x, default=0):
    """Turn model output like 650000, "Rs 650,000", "1.5 lakh", "50k" into an int."""
    if x is None or x == "" or isinstance(x, bool):
        return default
    if isinstance(x, (int, float)):
        return int(round(x))
    s = str(x).lower().replace(",", "")
    mult = 1
    if "crore" in s:
        mult = 10_000_000
    elif "lakh" in s or "lac" in s:
        mult = 100_000
    elif re.search(r"\d\s*k\b", s):
        mult = 1000
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return default
    return int(round(float(m.group()) * mult))


def to_min(s):
    """'10:00', '1:30 pm', '13:15' -> minutes after midnight (None if unreadable)."""
    if s is None or isinstance(s, (int, float, bool)):
        return None
    t = str(s).strip().lower()
    m = re.match(r"^(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", t)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if h > 23 or mi > 59:
        return None
    if ap and ap.startswith("p") and h < 12:
        h += 12
    elif ap and ap.startswith("a") and h == 12:
        h = 0
    elif not ap and 1 <= h <= 7:      # "1:30" at an event means afternoon
        h += 12
    return h * 60 + mi


def clock(m):
    h, mm = (m // 60) % 24, m % 60
    return f"{h % 12 or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def rs(x):
    return f"Rs {x:,}"


def _dicts(xs):
    return [x for x in (xs or []) if isinstance(x, dict)]


def _status(c):
    return str(c.get("status") or "required").lower()


def _block_kind(name):
    n = name.lower()
    if re.search(r"open|welcome|inaugur|brief|registration|check.?in", n):
        return "head"
    if re.search(r"clos|prize|award|ceremony|result|wrap", n):
        return "tail"
    return "middle"


LIST_SECTIONS = ("venues", "costs", "schedule_blocks", "venue_rules")


def _as_list(v, key_field=None):
    """Model slip: a list section given as an object, e.g. {"committed":[...]} -> flat list."""
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        out = []
        lists = {k: x for k, x in v.items() if isinstance(x, list)}
        if lists:
            for k, xs in lists.items():
                for x in xs:
                    if isinstance(x, dict):
                        if key_field and not x.get(key_field):
                            x = {**x, key_field: k}
                        out.append(x)
            return out
        return [v]
    return []


def normalize(f):
    """Repair common shape slips in the model's facts so the planner never crashes."""
    f = dict(f or {})
    for k in SECTIONS:
        v = f.get(k)
        if k in LIST_SECTIONS:
            f[k] = _as_list(v, "status" if k == "costs" else None)
        else:
            if isinstance(v, list):
                v = next((x for x in v if isinstance(x, dict)), {})
            f[k] = v if isinstance(v, dict) else {}
    food = dict(f["food"])
    food["options"] = _as_list(food.get("options"))
    food["special_needs"] = _as_list(food.get("special_needs"))
    f["food"] = food
    ev = dict(f["event"])
    ev["other_attendees"] = _as_list(ev.get("other_attendees"))
    f["event"] = ev
    return f


def split_costs(f):
    """Costs that duplicate venue/food/judge fees (planned separately) -> (kept, ignored)."""
    F0 = f.get("food") or {}
    planned = {str(x.get("name") or "").lower().strip()
               for x in _dicts(F0.get("options")) + _dicts(f.get("venues"))} - {""}
    dup = re.compile(r"judg|honorar|venue|hall (rent|hire|booking)|lunch box|meal box|catering|per head meal")
    kept, ignored = [], []
    for c in _dicts(f.get("costs")):
        item = str(c.get("item") or "").lower().strip()
        if dup.search(item) or any(n in item or item in n for n in planned) \
                or ("deliver" in item and num(F0.get("fixed_fee"))):
            ignored.append(c)
        else:
            kept.append(c)
    return kept, ignored


def clean(facts):
    """Normalize and drop duplicate costs, so stored facts hold each fee once."""
    f = normalize(facts)
    f["costs"] = split_costs(f)[0]
    return f


def _entry_name(x):
    if isinstance(x, dict):
        return str(x.get("name") or x.get("item") or x.get("diet") or x.get("who") or "").lower()
    return str(x).lower()


def apply_changes(facts, changes):
    """Apply field-level changes from an accepted message. Returns (new_facts, notes)."""
    f = normalize(copy.deepcopy(facts))
    notes = []
    for ch in _dicts(changes):
        sec = str(ch.get("section") or "").strip().lower()
        field = str(ch.get("field") or "").strip()
        match = str(ch.get("match") or "").strip().lower()
        val = ch.get("value")
        if sec in ("food.options", "food.special_needs"):
            lst = f["food"].setdefault(sec.split(".")[1], [])
        elif sec in LIST_SECTIONS:
            lst = f[sec]
        elif sec in SECTIONS:
            if field and not field.startswith("_"):
                f[sec][field] = val
                notes.append(f"{sec}.{field} = {val}")
            continue
        else:
            notes.append(f"ignored change to unknown section '{sec}'")
            continue
        if field == "_add":
            lst.append(val)
            notes.append(f"{sec}: added {_entry_name(val)}")
            continue
        hits = [x for x in lst if match and (match in _entry_name(x) or _entry_name(x) in match)]
        if field == "_remove":
            for x in hits:
                lst.remove(x)
            notes.append(f"{sec}: removed {match}")
        elif hits and isinstance(hits[0], dict):
            hits[0][field] = val
            notes.append(f"{sec}[{match}].{field} = {val}")
        elif field and val is not None and sec != "venue_rules":
            lst.append({("item" if sec == "costs" else "name"): ch.get("match"), field: val})
            notes.append(f"{sec}: added {match} with {field} = {val}")
    return clean(f), notes


def merge(facts, updates):
    """Apply an accepted update: dict sections are merged, list sections replaced."""
    new = copy.deepcopy(facts)

    def deep(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                deep(a[k], v)
            else:
                a[k] = v
        return a

    for k, v in (updates or {}).items():
        if k not in SECTIONS:
            continue
        if isinstance(v, dict) and isinstance(new.get(k), dict):
            deep(new[k], v)
        else:
            new[k] = v
    return normalize(new)


# ---------------------------------------------------------------- schedule
def build_schedule(f, start, duration, judging_min, judging_label, has_food, j_earliest=None, j_latest=None):
    S, E = start, start + duration
    head, mid, tail, anchored = [], [], [], []
    # Ignore blocks that are really the event itself / build time / judging (the planner makes those).
    req = [b for b in _dicts(f.get("schedule_blocks"))
           if 0 < num(b.get("minutes")) < duration * 0.5
           and not re.search(r"hack|build|coding|judg", str(b.get("name") or "").lower())]
    for b in req:
        item = {"name": str(b.get("name") or "Break"), "minutes": num(b.get("minutes")),
                "source": "message"}
        at = to_min(b.get("at"))
        if at is not None:
            item["at"] = at
            anchored.append(item)
        else:
            {"head": head, "middle": mid, "tail": tail}[_block_kind(item["name"])].append(item)

    names = " ".join(b["name"].lower() for b in req)
    if not any(_block_kind(b["name"]) == "head" for b in req):
        head.insert(0, {"name": "Opening & briefing", "minutes": POLICY["opening_minutes"],
                        "source": "planner"})
    if has_food and not re.search(r"lunch|meal|khana|dinner|food", names):
        mid.insert(0, {"name": "Meal break (food at tables)", "minutes": POLICY["lunch_minutes"],
                       "source": "planner"})
    if not any(_block_kind(b["name"]) == "tail" for b in req):
        tail.append({"name": "Closing & prizes", "minutes": POLICY["closing_minutes"],
                     "source": "planner"})
    tail_items = [{"name": judging_label, "minutes": judging_min, "source": "computed"}] + tail

    out = []
    t = S
    for b in head:
        out.append({**b, "start": t, "end": t + b["minutes"]})
        t += b["minutes"]
    head_end = t
    tail_start = E - sum(b["minutes"] for b in tail_items)

    placed = [{**a, "start": a["at"], "end": a["at"] + a["minutes"]} for a in anchored]
    mid_len = sum(b["minutes"] for b in mid)
    anch_len = sum(a["minutes"] for a in anchored if head_end <= a["at"] < tail_start)
    build = (tail_start - head_end) - mid_len - anch_len
    t = head_end + max(0, int(build * POLICY["first_build_share"]) // 5 * 5)
    for b in mid:
        moved = True
        while moved:
            moved = False
            for p in placed:
                if t < p["end"] and t + b["minutes"] > p["start"]:
                    t, moved = p["end"], True
        placed.append({**b, "start": t, "end": t + b["minutes"]})
        t += b["minutes"]
    placed.sort(key=lambda b: b["start"])

    t = head_end
    for p in placed:
        if p["start"] > t:
            out.append({"name": "Build time", "minutes": p["start"] - t, "start": t,
                        "end": p["start"], "source": "planner"})
        out.append(p)
        t = max(t, p["end"])
    if tail_start > t:
        out.append({"name": "Build time", "minutes": tail_start - t, "start": t,
                    "end": tail_start, "source": "planner"})
    t = tail_start
    for b in tail_items:
        out.append({**b, "start": t, "end": t + b["minutes"]})
        t += b["minutes"]

    issues = []
    srt = sorted(out, key=lambda b: (b["start"], b["end"]))
    for a, b in zip(srt, srt[1:]):
        if a["end"] > b["start"]:
            issues.append(f"'{a['name']}' overlaps '{b['name']}'")
    for b in out:
        if b["start"] < S or b["end"] > E:
            issues.append(f"'{b['name']}' falls outside {clock(S)}-{clock(E)}")
    build_total = sum(b["minutes"] for b in out if b["name"] == "Build time")
    if build_total < POLICY["min_build_minutes"]:
        issues.append(f"only {build_total} min of build time left")
    if judging_min <= 0:
        issues.append("judging window could not be computed")
    if j_earliest is not None and tail_start < j_earliest:
        issues.append(f"judging starts {clock(tail_start)}, before allowed {clock(j_earliest)}")
    if j_latest is not None and tail_start + judging_min > j_latest:
        issues.append(f"judging ends {clock(tail_start + judging_min)}, after allowed {clock(j_latest)}")
    for r in req:
        if not any(b["name"] == str(r.get("name") or "Break") for b in out):
            issues.append(f"required block '{r.get('name')}' missing")
    return {"start": S, "end": E, "blocks": srt, "build_minutes": build_total, "issues": issues}


# ---------------------------------------------------------------- the plan
def build_plan(f):
    f = normalize(copy.deepcopy(f))
    ev = f.get("event") or {}
    assumptions, decisions = [], []

    students = num(ev.get("students"))
    team_size = num(ev.get("team_size"))
    # Code does the arithmetic: teams from students / team size; the model's count only if that is impossible.
    teams = math.ceil(students / team_size) if students and team_size else num(ev.get("teams"))
    staff = num(ev.get("staff"))
    others = _dicts(ev.get("other_attendees"))
    others_onsite = sum(num(o.get("count")) for o in others)
    others_eat = sum(num(o.get("count")) for o in others if o.get("eats", True) is not False)

    duration = num(ev.get("duration_minutes")) or num(ev.get("duration_hours")) * 60
    start = to_min(ev.get("start_time"))
    end = to_min(ev.get("end_time"))
    if start is None and end is not None and duration:
        start = end - duration
    if duration == 0 and start is not None and end is not None:
        duration = end - start
    if start is None:
        start = to_min(POLICY["default_start"])
        assumptions.append(f"No start time in messages; planner default {clock(start)}.")

    # judging
    J = f.get("judging") or {}
    avail = num(J.get("judges_available"))
    hon = num(J.get("honorarium"))
    mpt = num(J.get("minutes_per_team"))
    maxt = num(J.get("max_teams_per_judge"))
    jpt = num(J.get("judges_per_team")) or 1
    need = math.ceil(teams * jpt / maxt) if (teams and maxt) else (jpt if teams else 0)

    # budget
    B = f.get("budget") or {}
    total_budget = num(B.get("total"))
    # Sanity guard: an honorarium that, paid to every judge needed, exceeds the whole budget
    # was almost certainly read as the total for all confirmed judges.
    if hon and avail > 1 and total_budget and hon * max(need, 1) > total_budget >= hon and hon % avail == 0:
        decisions.append(("judging", f"Honorarium {rs(hon)} read as a total for {avail} judges -> "
                                     f"{rs(hon // avail)} each (per-judge figure would exceed the whole budget)."))
        hon //= avail
    reserve = num(B.get("reserve"))
    cap = total_budget - reserve

    # Guard: venue, food and judge fees are planned separately; never count them twice.
    costs, ignored = split_costs(f)
    for c in ignored:
        decisions.append(("budget", f"Ignored cost '{c.get('item')}': already planned under venue/food/judging."))
    mandatory = [c for c in costs if _status(c) not in ("optional", "rejected")]
    optional = [c for c in costs if _status(c) == "optional"]

    guard_logged = set()

    def amount(c, fed):
        a, basis = num(c.get("amount")), str(c.get("basis") or "fixed").lower()
        n = (students if ("student" in basis or "participant" in basis) else
             fed if ("person" in basis or "head" in basis) else
             teams if "team" in basis else 1)
        # Sanity guard: a "per head" amount that alone breaks the whole budget when multiplied
        # was almost certainly already a total.
        if n > 1 and total_budget and a * n > total_budget >= a:
            if id(c) not in guard_logged:
                guard_logged.add(id(c))
                decisions.append(("budget", f"'{c.get('item')}' {rs(a)} read as a total, not per {basis}: "
                                            f"x{n} would exceed the whole budget."))
            return a
        return a * n

    # food
    F = f.get("food") or {}
    food_opts = [o for o in _dicts(F.get("options")) if not o.get("excluded_reason")]
    food_pref = sorted(food_opts, key=lambda o: (0 if o.get("standard") else 1,
                                                 -num(o.get("price_per_head"))))
    fee = num(F.get("fixed_fee"))
    order_q = num(F.get("order_quantity"), None) or None  # 0 / blank = not stated
    needs = [(str(d.get("diet") or "").lower(), num(d.get("count")))
             for d in _dicts(F.get("special_needs")) if d.get("diet") and num(d.get("count")) > 0]

    def suits(o, diet):
        d = diet.strip()
        for s in (o.get("suits") or []):
            s = str(s).lower().strip()
            if not s or re.match(r"non[\s-]?", s) and not re.match(r"non[\s-]?", d):
                continue  # "non-vegetarian" does not suit "vegetarian"
            if s == d or re.search(rf"\b{re.escape(d)}\b", s) or re.search(rf"\b{re.escape(s)}\b", d):
                return True
        return False

    def food_alloc(main, fed):
        """Main option for everyone, except people with a diet the main option doesn't meet."""
        items, unmet, rest = [], [], fed
        for diet, cnt in needs:
            if suits(main, diet):
                continue
            alt = next((o for o in food_pref if suits(o, diet)), None)
            if alt:
                items.append((alt, cnt, diet))
                rest -= cnt
            else:
                unmet.append(f"{cnt} {diet}")
        main_q = max(rest, (order_q or 0) - sum(i[1] for i in items))
        return [(main, main_q, None)] + items, unmet

    # venues. Code-level rule check: if a required feature is listed for SOME venues,
    # the venues that do not list it are excluded (the model may also have excluded them).
    all_venues = _dicts(f.get("venues"))
    for rule in [str(r).lower() for r in (f.get("venue_rules") or []) if r]:
        words = [w for w in re.findall(r"[a-z]+", rule) if len(w) >= 4] or re.findall(r"[a-z]+", rule)
        feats = {id(v): " ".join(map(str, v.get("features") or [])).lower() for v in all_venues}
        if words and any(any(w in feats[id(v)] for w in words) for v in all_venues):
            for v in all_venues:
                if not v.get("excluded_reason") and not any(w in feats[id(v)] for w in words):
                    v["excluded_reason"] = f"lacks required '{rule}'"
                    decisions.append(("venue", f"{v.get('name')} excluded by code rule check: no '{rule}' listed."))
    venues = sorted([v for v in all_venues if not v.get("excluded_reason")],
                    key=lambda v: num(v.get("cost")))

    # Book exactly the judges needed (they are paid and fed); if too few confirmed, use all.
    judge_opts = [need] if 0 < need <= avail else [avail]

    def candidate(food, jused, venue):
        onsite = students + staff + jused + others_onsite
        fed = students + staff + jused + others_eat
        lines = []
        if venue:
            lines.append({"area": "venue", "item": f"Venue: {venue.get('name')}",
                          "amount": num(venue.get("cost"))})
        if food:
            for o, q, diet in food_alloc(food, fed)[0]:
                lines.append({"area": "food", "item": f"Food: {o.get('name')} x {q} @ {rs(num(o.get('price_per_head')))}"
                                                      + (f" ({diet})" if diet else ""),
                              "amount": q * num(o.get("price_per_head"))})
            if fee:
                lines.append({"area": "food", "item": "Food: delivery / fixed fee", "amount": fee})
        lines.append({"area": "judging", "item": f"Judges: {jused} x {rs(hon)} honorarium",
                      "amount": jused * hon})
        for c in mandatory:
            lines.append({"area": "budget", "item": f"{c.get('item')} ({_status(c)})",
                          "amount": amount(c, fed)})
        return {"food": food, "jused": jused, "venue": venue, "onsite": onsite, "fed": fed,
                "lines": lines, "total": sum(l["amount"] for l in lines)}

    best, cheapest = None, None
    for food in (food_pref or [None]):
        for jused in judge_opts:
            onsite = students + staff + jused + others_onsite
            fits = [v for v in venues if num(v.get("capacity")) >= onsite] or [None]
            for v in fits:
                c = candidate(food, jused, v)
                if cheapest is None or c["total"] < cheapest["total"]:
                    cheapest = c
                if v and c["total"] <= cap:
                    best = c
                    break
            if best:
                break
        if best:
            break
    ch = best or cheapest

    # optional requests: add only if they still fit
    declined = []
    for c in optional:
        a = amount(c, ch["fed"])
        if POLICY["include_optional_if_affordable"] and ch["total"] + a <= cap:
            ch["lines"].append({"area": "budget", "item": f"{c.get('item')} (optional, fits budget)", "amount": a})
            ch["total"] += a
            decisions.append(("budget", f"Optional '{c.get('item')}' {rs(a)} included: still within budget."))
        else:
            declined.append({"item": c.get("item"), "amount": a,
                             "why": "would exceed budget" if ch["total"] + a > cap else "policy"})
            decisions.append(("budget", f"Optional '{c.get('item')}' {rs(a)} declined: would exceed budget."))

    venue, food, jused = ch["venue"], ch["food"], ch["jused"]
    onsite, fed = ch["onsite"], ch["fed"]

    # venue explanation
    alts = []
    for v in all_venues:
        if venue and v is venue:
            continue
        if v.get("excluded_reason"):
            why = f"excluded: {v['excluded_reason']}"
        elif num(v.get("capacity")) < onsite:
            why = f"too small ({num(v.get('capacity'))} < {onsite})"
        else:
            why = f"costlier ({rs(num(v.get('cost')))})"
        alts.append({"name": v.get("name"), "why": why})
    if venue:
        decisions.append(("venue", f"{venue.get('name')}: cheapest venue that seats all {onsite} on site and meets every stated requirement."))
    if food:
        decisions.append(("food", f"{food.get('name')} @ {rs(num(food.get('price_per_head')))} for {fed} people "
                                   f"({students} students + {staff} staff + {jused} judges + {others_eat} others)."))
    if need and jused == need:
        decisions.append(("judging", f"Booking {jused} of {avail} confirmed judges: ceil({teams} teams x {jpt} "
                                     f"/ max {maxt or '-'} per judge) = {need}. Only booked judges are paid and fed."))
    elif jused < need:
        decisions.append(("judging", f"Only {avail} judges confirmed but {need} are needed."))

    # judging numbers
    teams_per_judge = math.ceil(teams * jpt / jused) if jused else 0
    judging_min = teams_per_judge * mpt
    judging_label = f"Judging - {jused} judges in parallel, {teams_per_judge} teams each x {mpt} min"
    sched = build_schedule(f, start, duration, judging_min, judging_label, bool(food),
                           to_min(J.get("earliest_start")), to_min(J.get("latest_end")))
    alloc, unmet = food_alloc(food, fed) if food else ([], [])
    for o, qn, diet in alloc[1:]:
        decisions.append(("food", f"{qn} x {o.get('name')} for {diet} needs ({food.get('name')} does not suit)."))

    # ------------------------------------------------------------ checks
    checks = []

    def check(cid, label, ok, detail):
        checks.append({"id": cid, "label": label, "ok": bool(ok), "detail": detail})

    missing = [k for k, v in (("students", students), ("team size/teams", teams),
                              ("duration", duration), ("budget", total_budget)) if not v]
    check("figures", "Key figures read", not missing,
          "missing: " + ", ".join(missing) if missing else
          f"{students} students, {teams} teams, {onsite} on site, {fed} to feed")
    vcap = num(venue.get("capacity")) if venue else 0
    check("venue", "Venue fits", venue and vcap >= onsite,
          f"{venue.get('name')} seats {vcap} for {onsite} people" if venue else "no venue seats everyone")
    q = sum(i[1] for i in alloc)
    food_ok = food and (order_q is None or order_q >= fed) and not unmet
    check("food", "Food for everyone", food_ok,
          (f"order fixed at {order_q} but {fed} people need food" if food and order_q is not None and order_q < fed
           else f"no food option for {', '.join(unmet)}" if unmet
           else f"{q} meals for {fed} people" if food else "no usable food option"))
    j_ok = jused >= need > 0 and (not maxt or teams_per_judge <= maxt)
    check("judges", "Enough judges", j_ok,
          f"{jused} judges, {need} needed ({teams} teams x {jpt} / max {maxt or '-'} per judge)")
    check("schedule", "Schedule valid", not sched["issues"] and duration > 0,
          "; ".join(sched["issues"]) or f"{clock(sched['start'])}-{clock(sched['end'])}, {duration} min, "
                                         f"{sched['build_minutes']} min build time")
    check("budget", "Within budget", total_budget and ch["total"] <= cap,
          f"{rs(ch['total'])} of {rs(total_budget)}" + (f" (reserve {rs(reserve)})" if reserve else ""))
    covered = all([venue, sched["blocks"], food, jused, total_budget])
    check("areas", "All 5 areas covered", covered, "venue, schedule, food, judging, budget")

    return {
        "valid": all(c["ok"] for c in checks),
        "figures": {"students": students, "team_size": team_size, "teams": teams, "staff": staff,
                    "judges": jused, "others_onsite": others_onsite, "onsite": onsite, "fed": fed},
        "venue": {"name": venue.get("name") if venue else None, "capacity": vcap,
                  "cost": num(venue.get("cost")) if venue else 0,
                  "features": venue.get("features") or [] if venue else [],
                  "spare": vcap - onsite if venue else 0, "alternatives": alts},
        "food": {"name": food.get("name") if food else None,
                 "price": num(food.get("price_per_head")) if food else 0, "quantity": q,
                 "fixed_fee": fee, "cost": sum(l["amount"] for l in ch["lines"] if l["area"] == "food"),
                 "order_quantity": order_q,
                 "items": [{"name": o.get("name"), "qty": qn, "price": num(o.get("price_per_head")), "diet": d}
                           for o, qn, d in alloc]},
        "judging": {"available": avail, "used": jused, "needed": need, "honorarium": hon,
                    "cost": jused * hon, "teams_per_judge": teams_per_judge,
                    "max_teams_per_judge": maxt, "minutes_per_team": mpt,
                    "judges_per_team": jpt, "window_minutes": judging_min},
        "schedule": sched,
        "budget": {"total": total_budget, "reserve": reserve, "lines": ch["lines"],
                   "spent": ch["total"], "remaining": total_budget - ch["total"], "declined": declined},
        "checks": checks,
        "assumptions": assumptions,
        "decisions": decisions,
    }


# ---------------------------------------------------------------- helpers for updates
def summary(p):
    """Short plan summary given to the model when a new message arrives."""
    fg, v, fd, j, b = p["figures"], p["venue"], p["food"], p["judging"], p["budget"]
    return (f"{fg['students']} students, {fg['teams']} teams, {fg['staff']} staff, "
            f"{j['used']} judges (need {j['needed']}), {fg['onsite']} on site, {fg['fed']} to feed. "
            f"Venue {v['name']} seats {v['capacity']}. Food {fd['name']} x{fd['quantity']}. "
            f"Schedule {clock(p['schedule']['start'])}-{clock(p['schedule']['end'])}. "
            f"Budget {b['total']}, planned {b['spent']}, left {b['remaining']}. "
            f"Plan valid: {p['valid']}.")


def diff(old, new):
    """What changed between two plans, per area (for the trace)."""
    out = []

    def cmp(area, label, a, b):
        if a != b:
            out.append((area, f"{label}: {a} -> {b}"))

    cmp("venue", "Venue", old["venue"]["name"], new["venue"]["name"])
    cmp("food", "Food", f"{old['food']['name']} x{old['food']['quantity']} = {rs(old['food']['cost'])}",
        f"{new['food']['name']} x{new['food']['quantity']} = {rs(new['food']['cost'])}")
    cmp("judging", "Judges", f"{old['judging']['used']} (need {old['judging']['needed']})",
        f"{new['judging']['used']} (need {new['judging']['needed']})")
    so = [(b["name"], clock(b["start"])) for b in old["schedule"]["blocks"]]
    sn = [(b["name"], clock(b["start"])) for b in new["schedule"]["blocks"]]
    if so != sn:
        out.append(("schedule", "Schedule re-timed: " +
                    ", ".join(f"{n} {t}" for n, t in sn if (n, t) not in so)))
    ol = {l["item"]: l["amount"] for l in old["budget"]["lines"]}
    for l in new["budget"]["lines"]:
        if ol.get(l["item"]) != l["amount"]:
            out.append(("budget", f"{l['item']}: {rs(ol[l['item']]) if l['item'] in ol else 'new'} -> {rs(l['amount'])}"))
    nl = {l["item"] for l in new["budget"]["lines"]}
    for item, a in ol.items():
        if item not in nl:
            out.append(("budget", f"{item}: removed ({rs(a)})"))
    cmp("budget", "Total spend", rs(old["budget"]["spent"]), rs(new["budget"]["spent"]))
    return out
