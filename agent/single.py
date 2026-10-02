"""
MILESTONE 3c — ONE agent, tools from MCP. This is your baseline: the crew must beat it later.

    python evals/run_eval.py --agent single --limit 5
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = str(ROOT / "server" / "olist_server.py")
MAX_STEPS = 10

SYSTEM_PROMPT = """You are a data analyst for an e-commerce company. Answer the question with SQL on the
database you can reach through your tools.
TODO: write the rest yourself. Things that matter (you'll discover more while testing):
- explore before querying (which tools first?)
- what to do when a query returns an error
- how to finish: your FINAL message must contain the final SQL, in a format your code can extract
  (HINT: ask for a ```sql ... ``` block, or better: give the agent a `submit_answer` tool... but then
  it's a tool that lives in your code, not in MCP. Both are fine; pick one and explain why in the README).
"""


async def answer(question: str) -> dict:
    """Return {"sql": final_sql, "answer": final_text, "llm_calls": n, "steps": [...]}.

    The loop, in words (same as retail-agents, but async and with MCP):
      1. open McpTools(SERVER), get the Gemini declarations
      2. history = [the question]
      3. repeat up to MAX_STEPS:
           reply = llm.chat(SYSTEM_PROMPT, history, declarations)
           no tool calls?  -> done, extract the SQL from reply.text
           tool calls?     -> await tools.call(...) for each, append results to history
      4. return the dict
    """
    # TODO
    raise NotImplementedError
