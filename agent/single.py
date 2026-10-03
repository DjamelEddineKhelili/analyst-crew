"""
MILESTONE 3c — ONE agent, tools from MCP. This is your baseline: the crew must beat it later.

    python evals/run_eval.py --agent single --limit 5
"""
from pathlib import Path
import re
from agent.llm import GeminiLLM
from agent.mcp_bridge import McpTools
ROOT = Path(__file__).resolve().parent.parent
SERVER = str(ROOT / "server" / "olist_server.py")
MAX_STEPS = 10

SYSTEM_PROMPT = """You are an expert data analyst for an e-commerce company. Answer the question with SQL on the
database you can reach through your tools.

Rules:
- You can only use the tools provided by the MCP server. You cannot access the database directly
- You must explore the database before you can answer the question. Use the tools to find out what tables and columns exist, and what data is in them.
- You must not make up table or column names. If you try to query a table or column that does not exist, the server will return an error.
- You must not make up data. If you try to query for data that does not exist, the server will return an error.
- The tool to explore the database is `list_tables`. If you need to know what tables exist, call this tool. It returns a list of table names.
- The tool to explore a table is `describe_table`. If you need to know what columns exist in a table, call this tool. It returns a list of column names and their data types.
- The tool to run a SQL query is `run_sql`. If you need to run a SQL query, call this tool. It returns the result of the query.
- You must not run any destructive queries (DROP, DELETE, UPDATE, etc.). If you try to run a destructive query, the server will return an error.
- If a query returns an error,  you must revise your approach based on the error message and fix the query. You must not ignore errors or make up data to fix them.
- Return exactly the columns the question asks for, in that order, and no extra columns.
- When you are done, give your final query in a ```sql code block. Only the last ```sql block is used as your answer."""

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
    llm = GeminiLLM()
    async with McpTools(SERVER) as tools:
        dcls = tools.gemini_declarations()
        history = [{"role": "user", "text": question}]
        steps = []
        for step in range(1, MAX_STEPS + 1):
            reply = llm.chat(SYSTEM_PROMPT, history, dcls)
            history.append({"role": "assistant", "text": reply.text, "calls": reply.calls, "raw": reply.raw})
            
            #If there are no calls, you're done: break.
            if not reply.calls:
                break
            # Otherwise, for each call, result = await tools.call(call.name, call.args), collect the results, and append one tool_results message.
            results = []
            for call in reply.calls:
                result = await tools.call(call.name, call.args)
                steps.append({"tool": call.name, "args": call.args, "error": result.get("error")})
                results.append({"id": call.id, "name": call.name, "result": result})
            history.append({"role": "tool_results", "results": results})  
        blocks = re.findall(r"```sql(.*?)```", reply.text, re.DOTALL)
        sql = blocks[-1].strip() if blocks else ""
        if not sql:
            for s in reversed(steps):
                if s["tool"] == "run_sql" and not s.get("error"):
                    sql = s["args"].get("sql", "").strip()
                    break
    
    return {"sql": sql, "answer": reply.text, "llm_calls": llm.calls, "steps": steps}