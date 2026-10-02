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

# TODO: paste and adapt GeminiLLM + Reply + ToolCall from retail-agents.
