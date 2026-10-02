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
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evals.scorer import results_match  # noqa: E402

DB_PATH = ROOT / "data" / "olist.db"
QUESTIONS = ROOT / "evals" / "questions.json"
RUNS = ROOT / "runs"


def run_query(sql: str) -> list[list]:
    """Run SQL on the real DB (read-only) and return rows as lists."""
    # TODO: same read-only connection as the server. Return [list(row) for row in rows].
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    start = time.monotonic()
    con.set_progress_handler(lambda: time.monotonic() - start > 10, 10000)
    rows = con.execute(sql).fetchall()
    con.close()
    return [list(row) for row in rows]


async def dummy_answerer(question: str, gold_sql: str) -> dict:
    """Cheats by returning the gold SQL. Only exists to test the harness: it must score 100%."""
    return {"sql": gold_sql, "llm_calls": 0}


def load_answerer(name: str):
    if name == "dummy":
        return dummy_answerer
    # TODO (milestone 3): if name == "single": import and return agent.single.answer
    if name == "single":
        from agent.single import answer
        return answer
    # TODO (milestone 4): if name == "crew":   import and return agent.crew.answer
    if name == "crew":
        from agent.crew import answer
        return answer
    raise SystemExit(f"Unknown agent '{name}'")


async def main(agent_name: str, limit: int | None):
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))[:limit]
    answer = load_answerer(agent_name)

    results = []
    for q in questions:
        # TODO 1: call the answerer (dummy needs gold_sql too; real agents only get the question).
        if agent_name == "dummy":
            result= await dummy_answerer(q["question"], q["gold_sql"])
        else:
            result = await answer(q["question"])
        # TODO 2: run gold SQL and agent SQL with run_query(). If the agent's SQL crashes -> wrong, not a crash of the eval.
        gold_rows = run_query(q["gold_sql"])
        error = None
        try:
            agent_rows = run_query(result["sql"])
            correct = results_match(gold_rows, agent_rows, ordered=q["ordered"])
        except Exception as e:
            error = str(e)
            correct = False
        # TODO 4: print one line per question: ✅/❌ id, question, llm_calls
        status = "✅" if correct else "❌"
        print(f"{status} {q['id']}: {q['question']} ({result.get("llm_calls", 0)} LLM calls)")
        # TODO 5: append a dict to `results` (id, correct, agent sql, error if any, llm_calls...)
        results.append({
            "id": q["id"],
            "correct": correct,
            "agent_sql": result["sql"],
            "error": error or result.get("error"),
            "llm_calls": result.get("llm_calls", 0),
            "steps": result.get("steps"),
            "answer": result.get("answer"),
        })
        RUNS.mkdir(exist_ok=True)
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_file = RUNS / f"{agent_name}-{timestamp}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)   

    # TODO 6: print the final score: X/N correct (Y%), total LLM calls.
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    total_llm_calls = sum(r["llm_calls"] for r in results)
    percentage = (correct_count / total) * 100 if total > 0 else 0
    print(f"\nFinal Score: {correct_count}/{total} correct ({percentage:.2f}%), Total LLM calls: {total_llm_calls}")

    # TODO 7: save `results` to runs/<agent_name>-<timestamp>.json, so you can compare runs later.
    RUNS.mkdir(exist_ok=True)
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = RUNS / f"{agent_name}-{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)     
    #         These files ARE your README's evidence. Don't skip this.


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agent", default="dummy")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    asyncio.run(main(args.agent, args.limit))
