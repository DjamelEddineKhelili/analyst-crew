# Analyst Crew — data analyst agents over MCP

> Skeleton. Rewrite this README in your own words as you build. Keep the sections, fill them with real results.

Business questions in plain language → agents that explore a real e-commerce database through **MCP**,
write SQL, check each other, and get **scored** on questions with known answers.

```
question ─► Planner ─► SQL worker ⇄ Critic ─► SQL + answer
                           │
                    MCP server (olist_server.py)
                           │
                     SQLite: 100k real orders (Olist)
```

## Milestones

| # | What | Files | Done when |
|---|---|---|---|
| 1 | Load data + MCP server | `data/load.py`, `server/olist_server.py` | `python checks/check_m1.py` all green |
| 2 | Scorer + eval harness + 20–30 questions you write | `evals/scorer.py`, `evals/run_eval.py`, `evals/questions.json` | `python checks/check_m2.py` green, `python evals/run_eval.py --agent dummy` = 100% |
| 3 | One agent, tools from MCP | `agent/mcp_bridge.py`, `agent/llm.py`, `agent/single.py` | baseline score saved in `runs/` |
| 4 | The crew | `agent/crew.py` | crew vs baseline: score, cost, regressions |
| 5 | Failure analysis | this README | "what worked, what failed" with real examples |

## Setup

1. Download the Olist dataset (Kaggle: "Brazilian E-Commerce Public Dataset by Olist") and put the 9 CSVs in `data/raw/`.
2. See `CHEATSHEET.md` section 0.

## Writing questions (milestone 2)

Mix of difficulties, written **before** you build the agents (so you don't unconsciously pick questions your agent already handles):
- easy: one table, one filter (`How many orders were canceled?`)
- medium: a join or a GROUP BY (`Average review score per product category`)
- hard: dates, several joins, tricky definitions (`Which sellers deliver late most often?` — what does "late" mean? Write it in the question!)

Ambiguous questions make unfair evals. If two people could read the question differently, make it more precise.

## Results

*(milestone 3–4: table of baseline vs crew, score, LLM calls)*

## What worked, what failed

*(milestone 5)*
