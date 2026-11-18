"""Model access. Any OpenAI-compatible endpoint works (Groq, OpenRouter, Ollama on your laptop...).
Settings come from .env: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL."""
import json
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# override=True: the .env file always wins over stale values a terminal may still hold
load_dotenv(os.path.join(ROOT, ".env"), override=True)


def key_hint():
    k = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or ""
    return f"...{k[-4:]}" if len(k) > 8 else "(none)"


class LLMError(Exception):
    pass


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


class LLM:
    def __init__(self, trace):
        self.trace = trace
        self.model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
        base = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        key = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")
        if not key:
            raise LLMError("No API key. Put LLM_API_KEY=... in the .env file (see .env.example).")
        self.client = OpenAI(api_key=key, base_url=base, timeout=45, max_retries=1)

    def call_json(self, area, system, user, schema=None, max_tokens=3500, attempts=3):
        extra = {}
        effort = os.getenv("LLM_REASONING_EFFORT", "medium")  # gpt-oss: low = fewer tokens, medium = more reliable
        if effort:
            extra["reasoning_effort"] = effort
        # Default: plain JSON mode with the exact shape in the prompt (one call, no provider-side
        # rejection). LLM_STRICT_SCHEMA=1 uses the provider's strict schema check instead.
        strict = schema is not None and os.getenv("LLM_STRICT_SCHEMA", "0") == "1"
        fmt = ({"type": "json_schema", "json_schema": {"name": "facts", "strict": True, "schema": schema}}
               if strict else {"type": "json_object"})
        if schema and not strict:
            from engine.prompts import example
            system += ("\nOutput ONLY one JSON object of exactly this shape:\n"
                       + json.dumps(example(schema), separators=(",", ":")))
        fallback = os.getenv("LLM_FALLBACK_MODEL", "")
        model = self.model
        for attempt in range(1, attempts + 1):
            t0 = time.time()
            try:
                r = self.client.chat.completions.create(
                    model=model, temperature=0, max_tokens=max_tokens,
                    response_format=fmt, extra_body=extra or None,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}])
                break
            except Exception as e:
                msg = str(e)
                last = attempt >= attempts
                # Daily quota used up / model gone: switch to the fallback model (named in the trace).
                if not last and fallback and model != fallback and (
                        ("429" in msg and ("per day" in msg or "TPD" in msg)) or "404" in msg):
                    self.trace.note(area, f"Model {model} unavailable ({msg[:90]}...); "
                                          f"switching to fallback model {fallback}.")
                    model = fallback
                    if "gpt-oss" not in fallback:
                        extra = {}
                    continue
                if not last and "429" in msg:  # per-minute rate limit: wait as told (max 20s), retry
                    m = re.search(r"try again in ([\d.]+)(ms|s)\b", msg)
                    wait = min(20.0, (float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)) + 0.5) if m else 5.0
                    self.trace.note(area, f"Rate limited by provider; waiting {wait:.1f}s and retrying.")
                    time.sleep(wait)
                    continue
                # The provider refused the reply (invalid JSON / schema): retry in plain JSON mode.
                if not last and "json" in msg.lower():
                    detail = msg.split("Error: ")[-1][:300]
                    self.trace.note(area, f"Provider rejected the reply as invalid JSON ({detail}); "
                                          "retrying in plain JSON mode.")
                    if fmt.get("type") != "json_object" and schema:
                        from engine.prompts import example
                        system += ("\nOutput ONLY one JSON object of exactly this shape:\n"
                                   + json.dumps(example(schema), separators=(",", ":")))
                    fmt = {"type": "json_object"}
                    continue
                raise LLMError(f"Model call failed: {e}") from e
        out = r.choices[0].message.content or ""
        u = r.usage
        self.trace.call(model=r.model or model, area=area, system=system, user=user,
                        output=out,
                        prompt_tokens=getattr(u, "prompt_tokens", None),
                        completion_tokens=getattr(u, "completion_tokens", None),
                        total_tokens=getattr(u, "total_tokens", None),
                        seconds=round(time.time() - t0, 2))
        try:
            data = parse_json(out)
        except Exception as e:
            raise LLMError(f"Model did not return valid JSON: {e}") from e
        if isinstance(data, list):  # some models wrap the object in a list
            data = next((d for d in data if isinstance(d, dict)), {})
        if not isinstance(data, dict):
            raise LLMError("Model returned JSON that is not an object.")
        if isinstance(data.get("facts"), dict):  # tolerate {"messages":..., "facts":{...}}
            data = {**data, **data["facts"]}
        return data
