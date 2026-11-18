"""The only two prompts the system uses, plus the JSON schemas the model must follow.
Both ask the model to READ, never to do arithmetic."""

S = {"type": "string"}
N = {"type": ["integer", "null"]}
SN = {"type": ["string", "null"]}
B = {"type": "boolean"}


def obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def arr(item):
    return {"type": "array", "items": item}


def enum(*vals):
    # Plain string (the provider validates enums strictly and fails the whole call on a near-miss);
    # code reads these fields tolerantly. The allowed values are listed in the description.
    return {"type": "string", "description": "|".join(vals)}


def example(schema):
    """Compact example of the shape, used when falling back to plain JSON mode."""
    if "anyOf" in schema:
        return example(schema["anyOf"][0])
    t = schema.get("type")
    t = t[0] if isinstance(t, list) else t
    if t == "object":
        return {k: example(v) for k, v in schema["properties"].items()}
    if t == "array":
        return [example(schema["items"])]
    if t == "string":
        return schema.get("description", "")
    return {"integer": 0, "boolean": True}.get(t)


SECTION_SCHEMAS = {
    "event": obj({"students": N, "team_size": N, "teams": N, "duration_minutes": N, "start_time": SN,
                  "end_time": SN, "staff": N,
                  "other_attendees": arr(obj({"who": S, "count": N, "eats": B}))}),
    "budget": obj({"total": N, "reserve": N}),
    "venues": arr(obj({"name": S, "capacity": N, "cost": N, "features": arr(S), "excluded_reason": SN})),
    "food": obj({"options": arr(obj({"name": S, "price_per_head": N, "standard": B, "suits": arr(S),
                                     "excluded_reason": SN})),
                 "fixed_fee": N, "order_quantity": N,
                 "special_needs": arr(obj({"diet": S, "count": N}))}),
    "judging": obj({"judges_available": N, "honorarium": N, "minutes_per_team": N, "max_teams_per_judge": N,
                    "judges_per_team": N, "earliest_start": SN, "latest_end": SN}),
    "costs": arr(obj({"item": S, "amount": N, "basis": enum("fixed", "per_student", "per_person", "per_team"),
                      "status": enum("committed", "required", "optional")})),
    "schedule_blocks": arr(obj({"name": S, "minutes": N, "at": SN})),
    "venue_rules": arr(S),
}

READ_SCHEMA = obj({
    "messages": arr(obj({"id": {"type": "integer"}, "from": S, "date": S,
                         "status": enum("used", "superseded", "irrelevant", "rejected"), "note": S})),
    **SECTION_SCHEMAS,
})

ANY = {"type": ["string", "integer", "boolean", "null", "object"]}
UPDATE_SCHEMA = obj({
    "decisions": arr(obj({"from": S, "date": S, "decision": enum("accept", "reject", "irrelevant"),
                          "reason": S, "areas": arr(S)})),
    "changes": arr(obj({"section": S, "match": SN, "field": S, "value": ANY})),
})

AUTHORITY = ("Authority: the approving office (dean, VC, registrar, principal) sets headcount, duration and budget; "
             "finance reports spending; each supplier speaks only for its own prices and availability; "
             "students, societies and individual judges can only request.")

READ_SYSTEM = f"""You turn a pack of event-planning messages (emails, WhatsApp, notices; English or Roman Urdu) into facts for ONE student hackathon, in the given JSON schema.
Rules:
- First judge each message: "used", "superseded" (a newer message on the same topic replaces it), "irrelevant" (no planning impact), or "rejected" (contradicts an approved rule or newer/more authoritative facts, or sender lacks authority). note = short reason.
- {AUTHORITY}
- Fill every fact ONLY from "used" messages. Numbers from rejected or superseded messages must not appear.
- Numbers are plain integers (rupees, minutes; 1.5 lakh = 150000). Unknown = null. Never invent facts.
- Copy every price exactly as written: per-head, per-judge and per-item prices stay UNIT prices. Never multiply or add numbers; code does all arithmetic.
- costs: already spent/ordered from the event budget = committed; other mandatory spend = required; requests/wishes = optional. Venue, food and judge fees are NOT costs. basis per_student = per participant; per_person = everyone on site. For per_* basis, amount = the unit price exactly as written (never multiplied).
- excluded_reason: set when a venue or food option is unavailable or breaks a stated requirement (accessibility, power backup, dietary, location, date...); else null.
- food: standard = the normal/default option; suits = diets it meets; special_needs = people needing a diet. order_quantity = null unless a supplier states how many meals they will deliver. A food supplier's delivery/service charge goes in food.fixed_fee, not costs; food options never go in costs.
- Every request with a price (e.g. extra services, entertainment) goes in costs as optional, even if not yet approved.
- other_attendees: people on site besides students, staff and judges (volunteers, guests...).
- venue_rules: short features every venue must have (e.g. "projector", "step-free", "generator"); list venue features with the same words.
- schedule_blocks: only extra blocks the messages require (prayer, breaks, ceremonies, talks), never the hackathon/build time or judging; "at" = fixed clock time "13:15" if stated. Judging time limits go in judging.earliest_start/latest_end."""

UPDATE_SYSTEM = f"""You maintain the facts of a student hackathon plan. Input: CURRENT FACTS (JSON), PLAN NOW (summary) and NEW MESSAGE(S). For each new message decide:
- accept: a credible change from someone with authority over that fact.
- reject: plausible but wrong: contradicts established facts or an approved rule, sender lacks authority, or it would break the plan (fewer meals or seats than people, over budget, too few judges, schedule overrun).
- irrelevant: no planning impact.
{AUTHORITY}
"changes": ONLY the exact facts an ACCEPTED message changes, one entry each (empty list otherwise):
- section: event | budget | food | judging (single objects) or venues | costs | schedule_blocks | food.options | food.special_needs | venue_rules (lists).
- match: for lists, the name/item/diet of the entry to change (null for single objects).
- field: the field to set (e.g. "students", "amount", "fixed_fee", "excluded_reason"), or "_add" (value = full new entry) or "_remove".
- value: the new value exactly as the message states it (unit prices, never multiplied).
Example: printing now costs 15000 -> {{"section":"costs","match":"printing","field":"amount","value":15000}}.
Never do arithmetic for the plan; code recomputes everything."""
