"""
MILESTONE 3b — Talking to Gemini.

You already solved this in retail-agents (pilot/agent.py): GeminiLLM with retries, pacing and model fallback.
Reusing your own code is fine and expected. Copy GeminiLLM here and change ONE thing:

  In retail-agents, chat() received your own Tool objects and built FunctionDeclarations itself.
  Here, the declarations come from MCP (McpTools.gemini_declarations()). So make chat() accept
  a ready-made list of declarations instead.

Keep the same simple message format as before:
  {"role": "user", "text": ...}
  {"role": "assistant", "raw": <Gemini Content>}          # sent back untouched
  {"role": "tool_results", "results": [{"id", "name", "result"}, ...]}

And keep a counter of calls (self.calls) — the eval prints it, it's your "cost" metric.
"""
import os
import re
import time
from dataclasses import dataclass, field
# TODO: paste and adapt GeminiLLM + Reply + ToolCall from retail-agents.
@dataclass
class ToolCall:
    name: str
    args: dict
    id: str | None = None


@dataclass
class Reply:
    text: str
    calls: list[ToolCall] = field(default_factory=list)
    raw: object = None   # provider-specific message, kept so we can send it back untouched


class GeminiLLM:
    """Thin adapter around Google's Gemini API (google-genai SDK).

    Built for the FREE tier, which allows only a few requests per minute per model:
      - Pacing: calls are spaced out to stay under the per-minute limit (15/min for Lite models,
        5/min otherwise; override with GEMINI_RPM) so we don't hit it in the first place.
      - 429 (quota) -> wait as long as Google tells us to ("retry in 6s"), then retry.
      - 503 (overloaded) -> wait 2s, 4s, 8s... then retry.
      - Per-day quota used up, model missing (404) or still failing -> switch to the next model,
        which has its own separate quota.
    """
    # Free tier (Oct 2026): "Lite" models get 15 req/min and 500 req/day; "Flash" models only 5/min and 20/day.
    # Each model has its OWN quota, so falling back to another model gives a fresh budget.
    # A model name that doesn't exist for your key (404) is simply skipped.
    FALLBACK_MODELS = [
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest",
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
    ]
    RETRYABLE = {429, 500, 503, 504}

    def __init__(self, model: str | None = None, retries: int = 5, rpm: float | None = None,
                 sleep=time.sleep, clock=time.monotonic, log=print):
        from google import genai
        self.genai = genai
        self.types = genai.types
        self.client = genai.Client(http_options=genai.types.HttpOptions(timeout=60_000))        
        first = model or os.getenv("GEMINI_MODEL") or self.FALLBACK_MODELS[0]
        self.models = [first] + [m for m in self.FALLBACK_MODELS if m != first]
        self.retries = retries
        self.rpm_override = rpm or (float(os.getenv("GEMINI_RPM")) if os.getenv("GEMINI_RPM") else None)
        self.sleep, self.clock, self.log = sleep, clock, log
        self._last_call = None
        self.calls = 0

    @property
    def model(self) -> str:
        return self.models[0]

    @property
    def min_interval(self) -> float:
        rpm = self.rpm_override or (15 if "lite" in self.model else 5)
        return 60.0 / rpm * 1.1   # 10% safety margin

    def _pace(self):
        if self._last_call is not None:
            wait = self.min_interval - (self.clock() - self._last_call)
            if wait > 0:
                self.sleep(wait)
        self._last_call = self.clock()

    def _next_model(self, why: str):
        if len(self.models) == 1:
            raise RuntimeError(f"No Gemini model available ({why}). Free-tier quota is probably used up: "
                               "wait a few minutes (or until tomorrow for the daily quota), or enable billing.")
        self.log(f"  ↪ {self.model}: {why} — switching to {self.models[1]}")
        self.models.pop(0)

    def _generate_with_retry(self, contents, config):
        from google.genai import errors
        while True:
            for attempt in range(self.retries):
                self._pace()
                try:
                    self.calls += 1
                    return self.client.models.generate_content(model=self.model, contents=contents, config=config)
                except errors.APIError as e:
                    last_error = f"{e.code} {e.status}"
                    text = str(e.details)
                    if e.code == 404:
                        break                                  # model doesn't exist for this key -> next model
                    if e.code == 429 and "PerDay" in text:
                        break                                  # daily quota gone -> waiting won't help today
                    if e.code not in self.RETRYABLE:
                        raise                                  # bad key, bad request... retrying won't help
                    hinted = re.search(r"retry in ([\d.]+)s", text)
                    wait = float(hinted.group(1)) + 1 if hinted else 2 ** (attempt + 1)
                    self.log(f"  ⏳ {self.model}: {e.code} {e.status} — waiting {wait:.0f}s")
                    self.sleep(wait)
            self._next_model(last_error)

    def chat(self, system: str, history: list[dict], declarations: list) -> Reply:
        t = self.types
        contents = []
        for msg in history:
            if msg["role"] == "user":
                contents.append(t.Content(role="user", parts=[t.Part(text=msg["text"])]))
            elif msg["role"] == "assistant":
                contents.append(msg["raw"])  # send the model's own turn back exactly (keeps thought signatures)
            elif msg["role"] == "tool_results":
                parts = [t.Part(function_response=t.FunctionResponse(id=r["id"], name=r["name"],
                                                                     response={"result": r["result"]}))
                         for r in msg["results"]]
                contents.append(t.Content(role="user", parts=parts))

        config = t.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            tools=[t.Tool(function_declarations=declarations)],
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),  # we run the loop ourselves
        )
        resp = self._generate_with_retry(contents, config)
        content = resp.candidates[0].content
        calls = [ToolCall(name=fc.name, args=dict(fc.args or {}), id=fc.id) for fc in (resp.function_calls or [])]
        text = "".join(p.text for p in (content.parts or []) if getattr(p, "text", None) and not getattr(p, "thought", False))
        return Reply(text=text, calls=calls, raw=content)
