"""
MILESTONE 4 — The crew: Planner -> SQL Worker -> Critic (-> Worker again if the Critic says retry).

    python evals/run_eval.py --agent crew

THE BIG IDEA (read this first):
  A "crew" is NOT a new kind of AI. It is the SAME agent loop you already wrote in single.py,
  run several times with DIFFERENT system prompts (= different jobs), where the TEXT written
  by one agent becomes part of the INPUT of the next one. That hand-off of text is the whole trick.

      question ──► Planner ──plan──► Worker ──SQL──► Critic ──"ok"──► final answer
                                       ▲                │
                                       └──"retry: why"──┘   (at most MAX_RETRIES times)

  Why these 3 roles? Because our failure analysis (single agent, 11/15) showed that 3 of 4
  errors were "grain" errors: the agent counted the wrong unit (payment rows instead of orders,
  items instead of reviews). The Planner forces "what are we counting?" to be decided BEFORE
  any SQL is written, and the Critic checks that the final SQL really counts that unit.
"""

import re                                   # regular expressions: to pull the SQL and the verdict out of text
from pathlib import Path                    # clean, OS-independent file paths (works on Windows and Linux)

from agent.llm import GeminiLLM             # our Gemini adapter (retries, pacing, call counter)
from agent.mcp_bridge import McpTools       # our plug to the MCP server (list_tables, describe_table, run_sql)

ROOT = Path(__file__).resolve().parent.parent           # project root folder (analyst-crew/)
SERVER = str(ROOT / "server" / "olist_server.py")       # the MCP server script the agents will talk to

MAX_RETRIES = 1        # how many times the Critic may send the Worker back. 1 = at most 2 Worker runs.
PLANNER_STEPS = 4      # the Planner may explore a little (list/describe tables) but must stay cheap
WORKER_STEPS = 10      # same budget as the single agent, so the comparison is fair
CRITIC_STEPS = 3       # the Critic gets the result already; it may run 1-2 sanity queries at most
PREVIEW_ROWS = 10      # how many result rows we show the Critic (enough to judge, small enough to be cheap)


# ──────────────────────────────────────────────────────────────────────────────
# 1. THE THREE JOB DESCRIPTIONS (system prompts)
#    Same model, same tools. The ONLY thing that makes a "Planner" a planner is this text.
# ──────────────────────────────────────────────────────────────────────────────

PLANNER_PROMPT = """You are the Planner in a team of data analysts. You do NOT write the final SQL.
Your job: read the business question, look at the database schema with your tools if needed,
and write a short plan that another analyst will follow.

Your plan MUST contain exactly these 4 lines:
UNIT: what one counted thing is (e.g. "one order", "one unique customer (customer_unique_id)", "one review").
       Watch out for tables with several rows per order (order_items, order_payments): say if they must be deduplicated.
TABLES: which tables and how they join.
DEFINITIONS: how vague words in the question are defined (e.g. "late", "repeat customer", "relative").
RESULT SHAPE: the exact columns and number of rows expected (e.g. "1 row, 1 column: a percentage").

Do not run the final query. Keep it short."""

WORKER_PROMPT = """You are the SQL Worker in a team of data analysts. Answer the question with SQL on the
database you reach through your tools. A Planner already wrote a plan: FOLLOW IT, especially the UNIT.
If a Critic gave feedback on a previous attempt, fix exactly what it points out.

Rules:
- Explore with describe_table if you need column names. Never invent tables or columns.
- If a query returns an error, read the error and fix the query.
- Return exactly the columns described in RESULT SHAPE, in that order, no extra columns.
- When you are done, give your final query in a ```sql code block. Only the last ```sql block is used."""

CRITIC_PROMPT = """You are the Critic in a team of data analysts. You receive a question, a plan, a SQL query
and the first rows of its result. Your main check is the GRAIN: does each counted row really match the
UNIT in the plan? (Typical bug: counting payment rows or item rows when the question is about orders.)
Also check: the definitions from the plan are used, and the result has the shape the plan describes.
Before your verdict you MUST run one grain check with run_sql: compare COUNT(*) with COUNT(DISTINCT <key of the UNIT>)
on the joined tables of the query. If they differ, rows are duplicated and the query is probably counting the wrong unit.
If you could not verify the grain, answer retry.

Answer with exactly two lines:
VERDICT: ok      or      VERDICT: retry
REASON: one sentence, citing the numbers from your check. If retry, say precisely what to change."""


# ──────────────────────────────────────────────────────────────────────────────
# 2. ONE GENERIC AGENT LOOP, reused by all three roles
#    This is your single.py loop, made into a function that takes the role as a parameter.
# ──────────────────────────────────────────────────────────────────────────────

async def run_agent(llm, tools, decls, system_prompt, user_message, max_steps, role, steps):
    """Run ONE agent (one role) until it stops calling tools. Returns its final text.

    llm           : the shared GeminiLLM (shared so llm.calls counts the cost of the WHOLE crew)
    tools, decls  : the shared MCP connection and its tool declarations
    system_prompt : the job description (PLANNER_PROMPT, WORKER_PROMPT or CRITIC_PROMPT)
    user_message  : what this agent is asked (the hand-off from the previous agent goes in here)
    max_steps     : safety brake so one role can't loop forever
    role          : "planner" / "worker" / "critic", only used to label the log
    steps         : a list we append every tool call to (for the eval file and failure analysis)
    """
    history = [{"role": "user", "text": user_message}]            # each agent starts with a FRESH memory: only its input
    reply = None                                                    # will hold the last reply from the model
    for _ in range(max_steps):                                      # at most max_steps model calls for this role
        reply = llm.chat(system_prompt, history, decls)            # ask the model what to do next
        history.append({"role": "assistant", "text": reply.text,   # remember what the model said...
                        "calls": reply.calls, "raw": reply.raw})   # ...including raw, which llm.chat sends back untouched
        if not reply.calls:                                         # no tool requested = the agent has finished
            break                                                   # leave the loop
        results = []                                                # collect the results of every tool call of this turn
        for call in reply.calls:                                    # the model may ask for several tools at once
            result = await tools.call(call.name, call.args)        # run the tool through MCP (returns a dict, never crashes)
            steps.append({"role": role, "tool": call.name,         # log it: who called what...
                          "args": call.args, "error": result.get("error")})   # ...and whether it failed
            results.append({"id": call.id, "name": call.name, "result": result})  # format expected by llm.chat
        history.append({"role": "tool_results", "results": results})  # give all results back to the model
    if reply and reply.calls:                                       # loop ended while the agent still wanted tools
      history.append({"role": "user", "text": "Stop using tools now. Give your final answer."})
      reply = llm.chat(system_prompt, history, decls)            # one last call to force a written answer
    return reply.text if reply else ""                              # the agent's final words (plan, SQL, or verdict)


# ──────────────────────────────────────────────────────────────────────────────
# 3. SMALL HELPERS: turning free text into things code can use
# ──────────────────────────────────────────────────────────────────────────────

def extract_sql(text):
    """Return the last ```sql block in the text, or "" if there is none."""
    blocks = re.findall(r"```sql(.*?)```", text or "", re.DOTALL)  # every ```sql ... ``` block, as a list of strings
    return blocks[-1].strip() if blocks else ""                     # the last one is the final answer


def last_executed_sql(steps):
    """Code fallback (no LLM): the last run_sql the Worker executed WITHOUT error.
    Fixes the h05 failure, where the agent ran a good query but forgot to write the final ```sql block."""
    for s in reversed(steps):                                       # walk the log backwards, newest first
        if s["role"] == "worker" and s["tool"] == "run_sql" and not s["error"]:   # a Worker query that worked
            return s["args"].get("sql", "").strip()                 # that's our best guess of its answer
    return ""                                                       # the Worker never ran a successful query


def parse_verdict(text):
    """Turn the Critic's text into (ok: bool, reason: str). Anything unclear counts as ok:
    a confused Critic should not destroy an answer (we will measure if that was a good choice)."""
    retry = re.search(r"VERDICT:\s*retry", text or "", re.IGNORECASE)   # did it say retry?
    reason = re.search(r"REASON:\s*(.+)", text or "")                   # grab the reason sentence if present
    return (retry is None), (reason.group(1).strip() if reason else (text or "").strip())


# ──────────────────────────────────────────────────────────────────────────────
# 4. THE CREW: who talks to whom, in which order. This is the "orchestration".
# ──────────────────────────────────────────────────────────────────────────────

async def answer(question: str) -> dict:
    """Same contract as agent/single.py: returns {"sql", "answer", "llm_calls", "steps", ...}."""
    llm = GeminiLLM(model="gemini-3.1-flash-lite")                                   # ONE llm for the whole crew -> llm.calls = total cost of the crew
    steps = []                                          # one shared log for all roles (each entry says which role)
    critiques = []                                      # every Critic verdict, kept for the failure analysis

    async with McpTools(SERVER) as tools:               # ONE MCP connection shared by everyone (no need to restart the server)
        decls = tools.gemini_declarations()             # same tools for every role; the PROMPT decides how they use them

        # ── Step A: the Planner thinks before anyone writes SQL ──
        plan = await run_agent(llm, tools, decls, PLANNER_PROMPT,
                               f"Question: {question}",          # the Planner only sees the question
                               PLANNER_STEPS, "planner", steps)

        feedback = ""                                   # empty on the first attempt; filled if the Critic says retry
        sql, worker_text = "", ""                       # will hold the Worker's final answer
        for attempt in range(MAX_RETRIES + 1):          # attempt 0 = first try, attempt 1 = one retry, etc.

            # ── Step B: the Worker writes SQL, guided by the plan (and the Critic's feedback, if any) ──
            worker_input = f"Question: {question}\n\nPlan from the Planner:\n{plan}"   # HAND-OFF #1: plan -> worker
            if feedback:                                                               # only on a retry
                worker_input += (f"\n\nYour previous query was:\n{sql}\n"
                                 f"The Critic rejected it: {feedback}\nFix it.")      # HAND-OFF #3: critic -> worker
            worker_text = await run_agent(llm, tools, decls, WORKER_PROMPT, worker_input,
                                          WORKER_STEPS, "worker", steps)
            sql = extract_sql(worker_text) or last_executed_sql(steps)   # the LLM's answer, or the code fallback

            if not sql:                                 # nothing usable at all: no point asking the Critic
                break                                   # give up; the eval will score it as wrong

            # ── Step C: we (code, not an LLM) run the SQL so the Critic sees REAL results, not the Worker's claims ──
            preview = await tools.call("run_sql", {"sql": sql})          # same tool, called directly by our code
            if "rows" in preview:                                        # success: keep only a few rows
                preview = {"columns": preview["columns"], "rows": preview["rows"][:PREVIEW_ROWS]}

            # ── Step D: the Critic judges ──
            critic_input = (f"Question: {question}\n\nPlan:\n{plan}\n\n"           # HAND-OFF #2: everything -> critic
                            f"SQL:\n{sql}\n\nFirst rows of the result:\n{preview}")
            verdict_text = await run_agent(llm, tools, decls, CRITIC_PROMPT, critic_input,
                                           CRITIC_STEPS, "critic", steps)
            ok, reason = parse_verdict(verdict_text)    # free text -> (True/False, "why")
            critiques.append({"attempt": attempt, "ok": ok, "reason": reason})

            if ok:                                      # the Critic is satisfied
                break                                   # stop: this SQL is the crew's answer
            feedback = reason                           # otherwise loop again; the reason becomes the Worker's feedback

    return {
        "sql": sql,                                     # what the eval will execute and score
        "answer": worker_text,                          # the Worker's last message
        "llm_calls": llm.calls,                         # total cost: planner + worker(s) + critic(s)
        "steps": steps,                                 # every tool call, labelled by role
        "plan": plan,                                   # keep the plan: it explains most failures
        "critiques": critiques,                         # keep the verdicts: did the critic help or hurt?
    }