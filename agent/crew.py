"""
MILESTONE 4 — The crew. Same tools, same eval, more brains. Does it actually help?

    python evals/run_eval.py --agent crew --limit 5

Suggested roles (change them if your failure analysis from milestone 3 tells you otherwise!):

  Planner   — reads the question + the table list, writes a short plan:
              which tables, which joins, what the result should look like ("one row per state, 2 columns").
              No SQL. Cheap and short.
  SQL worker — the milestone-3 agent, but it receives the plan. Explores, writes the query, runs it.
  Critic    — gets the question, the plan, the SQL and the first rows of the result. Answers ONLY:
              {"verdict": "ok"} or {"verdict": "retry", "reason": "..."}.
              It may run its own sanity queries (e.g. "is the total plausible?").
              If retry -> the worker gets the reason and tries again (max 2 retries).

Design questions to answer in your README (these are what an interviewer will ask you):
  - Did the crew beat the single agent? On which questions? At what cost (LLM calls)?
  - Did the critic ever make a correct answer WORSE? (It happens. Count it.)
  - Should the critic see the gold answer? (No! Why not?)
"""


async def answer(question: str) -> dict:
    # TODO: planner -> worker -> critic loop. Return the same dict shape as agent/single.py.
    raise NotImplementedError
