"""
MILESTONE 2b / 3 / 4 — Run every question through an "answerer" and print a score.

    python evals/run_eval.py --agent dummy           # milestone 2: proves the harness works (score should be 100%)
    python evals/run_eval.py --agent single --limit 5  # milestone 3
    python evals/run_eval.py --agent crew   --limit 5  # milestone 4

An "answerer" is any async function:   async def answer(question: str) -> dict
returning at least {"sql": "..."}  (plus whatever you want to log: "answer", "steps", "llm_calls"...).
We run the returned SQL ourselves and compare its result with the gold SQL's result.
Why not trust the agent's own result? Same lesson as retail-agents: verify, don't believe.
"""
import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evals.scorer import results_match  # noqa: E402

DB_PATH = ROOT / "data" / "olist.db"
QUESTIONS = ROOT / "evals" / "questions.json"
RUNS = ROOT / "runs"


def run_query(sql: str) -> list[list]:
    """Run SQL on the real DB (read-only) and return rows as lists."""
    # TODO: same read-only connection as the server. Return [list(row) for row in rows].
    raise NotImplementedError


async def dummy_answerer(question: str, gold_sql: str) -> dict:
    """Cheats by returning the gold SQL. Only exists to test the harness: it must score 100%."""
    return {"sql": gold_sql, "llm_calls": 0}


def load_answerer(name: str):
    if name == "dummy":
        return dummy_answerer
    # TODO (milestone 3): if name == "single": import and return agent.single.answer
    # TODO (milestone 4): if name == "crew":   import and return agent.crew.answer
    raise SystemExit(f"Unknown agent '{name}'")


async def main(agent_name: str, limit: int | None):
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))[:limit]
    answer = load_answerer(agent_name)

    results = []
    for q in questions:
        # TODO 1: call the answerer (dummy needs gold_sql too; real agents only get the question).
        # TODO 2: run gold SQL and agent SQL with run_query(). If the agent's SQL crashes -> wrong, not a crash of the eval.
        # TODO 3: correct = results_match(gold_rows, agent_rows, ordered=q["ordered"])
        # TODO 4: print one line per question: ✅/❌ id, question, llm_calls
        # TODO 5: append a dict to `results` (id, correct, agent sql, error if any, llm_calls...)
        raise NotImplementedError

    # TODO 6: print the final score: X/N correct (Y%), total LLM calls.
    # TODO 7: save `results` to runs/<agent_name>-<timestamp>.json, so you can compare runs later.
    #         These files ARE your README's evidence. Don't skip this.


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agent", default="dummy")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    asyncio.run(main(args.agent, args.limit))
