# Hackathon Planner

Reads a pack of messages (English / Roman Urdu) and plans a 4-hour hackathon:
**venue, schedule, food, judging, budget**. New messages update the plan; wrong ones are rejected with a reason.

## Run it

```
pip install -r requirements.txt
copy .env.example .env          # then put your API key in .env

python plan.py data\sample_pack.txt      # full run (first time)
python plan.py tests\new_1_printing.txt  # update: accepted change
python plan.py tests\new_2_wrong_boxes.txt  # update: rejected (100 boxes < 177 people)
python plan.py reset                     # start a new event
```
Same pipeline for every message.

**Web interface:** `python plan.py` (no file) starts a local page at http://127.0.0.1:8000 — paste the pack or a
new message (or load a .txt), click Run. It calls the exact same `process()` function as the command line;
the trace still prints in the terminal and is saved to `output/`. The API key stays in Python, never in the browser.

Outputs in `output/`: **report.html** (the UI: Plan / Messages / Trace tabs),
**final_report.txt** (plan + full trace, the file to upload), trace.txt, plan.json.

## How it works (what every member should be able to explain)

```
messages.txt ──► [1 model call: READ] ──► facts (JSON) ──► [plain Python: PLAN + CHECK] ──► plan + report
new message ───► [1 model call: READ + accept/reject + exact field changes] ──► code applies changes ──► re-plan ──► code checks ──► keep or reject
```

| Part | File | What it does | What breaks without it |
|---|---|---|---|
| Entry / one command | `plan.py` | Full run if no saved plan, otherwise update. Prints trace + plan. | No single command; no update mode. |
| Reader (model) | `engine/prompts.py`, `engine/llm.py` | Turns messy text into facts: numbers, which message is newer/superseded/irrelevant/wrong. **Only language work.** | Can't understand Roman Urdu, superseded prices, irrelevant chat. |
| Planner (code) | `engine/solver.py` | All arithmetic: headcount, cheapest venue that fits, food cost, judges needed = ceil(teams / max per judge), schedule times, budget. | Model would do maths → wrong numbers, many more tokens. |
| Checks (code) | `engine/solver.py` `checks` | 7 checks: figures, venue fits, food for everyone, enough judges, schedule valid, within budget, all areas covered. | Wrong messages would silently break the plan. |
| Wrong-message guard | `plan.py` `update_run` | Two layers: (1) model judges authority/consistency; (2) code applies the change on a copy and rejects it if any passing check would fail. Plan stays valid, reason in trace. | A plausible-but-wrong message gets applied. |
| Trace | `engine/trace.py` | Every model call numbered: model, area tag, input, output, tokens **as reported by the API**; code decisions; rejections; totals. | No proof of what happened; disqualification. |
| State | `engine/state.py` | Saves facts + plan + trace to `output/state.json` so updates change the existing plan. | Each message would need a full re-run. |
| UI | `ui/report.py` | HTML report + terminal text. | — |

### Key decisions
- **1 model call per run** (area `reading`), both full run and update. Arithmetic in code → fewest tokens, exact numbers.
  *Prediction slip:* every update makes exactly **1 model call, area: reading**; planning areas are recomputed by code (0 calls).
- **Judges:** book exactly the number needed, ceil(teams × judges_per_team / max teams per judge); only booked judges are paid and fed (sample: ceil(50/3)=17 → 150+10+17 = 177 meals).
- **Venue:** cheapest venue that seats everyone on site and meets every stated requirement.
- **Food:** the standard option if the budget allows, otherwise the cheaper one. Newest price wins.
- **Optional requests** (e.g. DJ) are included only if they still fit the budget.
- **Schedule:** opening → build → lunch + required breaks → build → judging (computed length) → closing. Fixed-time blocks are placed at their time. Planner defaults (start 10:00, opening 10, lunch 30, closing 15) are listed as assumptions in the plan.
- **No facts in code:** every number comes from the message file through the model.

## Model
Any OpenAI-compatible API, set in `.env`. Default: Groq `openai/gpt-oss-120b` (reasoning effort `medium`),
fallback `openai/gpt-oss-20b` if the main model's daily quota runs out (the switch is printed in the trace and
the trace shows the model that actually answered).

Reliability guards in code (each one logs its decision in the trace):
- JSON shape repair (`solver.normalize`): a list given as an object, etc.
- Costs that duplicate venue/food/judge fees are ignored.
- A per-head or per-judge price that alone exceeds the whole budget when multiplied is read as a total.
- Any update that would break a passing check is rejected and the old plan is kept.
- Venue rules ("must have a projector"): if some venues list the feature, the others are excluded by code.
- Teams are always computed by code (students / team size), never taken from the model.
- Updates: the model returns only field-level changes (e.g. `event.students = 132`), which code applies
  (`solver.apply_changes`), so unrelated facts can't be corrupted by re-writing whole sections.
