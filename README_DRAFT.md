# analyst-crew

**Does a team of AI agents answer business questions better than one agent, and how much more does it cost?**

This project tests that question on a real e-commerce database (Olist, about 100k Brazilian orders). It compares two set-ups that use the same model and the same tools:

- **Single agent**: one LLM in a loop with SQL tools.
- **Crew**: a Planner, a SQL Worker and a Critic, three roles that hand text to each other.

Both talk to the database **only through an MCP server**. Both are scored by the **same eval harness**, which runs gold SQL and compares results.

> Built with Claude as a coding assistant (pair-programming mode: I wrote most of the server, bridge, loader, scorer and single agent; the crew orchestration was written with Claude and commented line by line).

---

## TL;DR results

All runs use the 15 "hard" questions, one run per configuration.

| Model | Single agent | Crew | Cost (LLM calls) single → crew |
|---|---|---|---|
| gemini-3.5-flash-lite | **10/15** (67%) | **12/15** (80%) | 87 → 173 (×2.0) |
| gemini-3.1-flash-lite | **8/15** (53%) | **12/15** (80%) | 92 → 226 (×2.5) |

- On both models the crew beats the single agent, at roughly twice the cost.
- The gain is larger on the weaker model (+4 on 3.1 vs +2 on 3.5). With one run each, this is a hypothesis, not a proven result.
- Caveat: the single agent was run **without** the "empty answer" fallback that the crew has (see [Honest caveats](#honest-caveats)), so part of the gap is unfair.

---

## Architecture

```
                 ┌──────────────── evals/run_eval.py ────────────────┐
                 │  for each question: ask agent → run its SQL →     │
                 │  run gold SQL → compare results → save JSON       │
                 └───────────────┬───────────────────────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │                                     │
      agent/single.py                        agent/crew.py
      (1 loop)                    Planner ─plan─► Worker ─SQL─► Critic
                                                    ▲             │
                                                    └──"retry"────┘ (max 1)
              │                                     │
              └────────── agent/mcp_bridge.py ──────┘   (MCP client, stdio)
                                 │
                       server/olist_server.py           (MCP server)
                    list_tables · describe_table · run_sql
                                 │
                        data/olist.db (SQLite, read-only)
```

`agent/llm.py` is a small Gemini adapter: tool declarations, retries on 503/429, pacing for free-tier limits, a fallback model list, a 60 s timeout, and a call counter used to measure cost.

---

## 1. Data: `data/load.py`

- Loads the 9 Olist CSVs (orders, order_items, order_payments, reviews, customers, sellers, products, geolocation, category_translation) into SQLite with pandas.
- Creates **indexes on every join key** (`order_id`, `customer_id`, `product_id`, `seller_id`, …).
  - Without them, one bad agent join made a run hang for minutes, and Ctrl+C did nothing.

## 2. MCP server: `server/olist_server.py`

The server exposes three tools (MCP Python SDK v2, `MCPServer`):

| Tool | What it returns |
|---|---|
| `list_tables()` | `{"tables": [...]}` |
| `describe_table(table)` | name, row count, columns (name + type), 3 sample rows |
| `run_sql(sql)` | columns, rows (max 100), `truncated` flag |

**Guardrails** (the agent can't break or freeze anything):

- The database is opened **read-only** (`file:...?mode=ro`).
- Only `SELECT` / `WITH`, and only a single statement.
- The table name is checked against the real list *before* it is used.
- **10-second query timeout** via `set_progress_handler`.
- Errors are raised as `ToolError`, so the agent sees the real SQLite message ("no such column: s.seller_state") and can fix its query. A plain exception's message is hidden by MCP.

Tested by `checks/check_m1.py` (23/23).

**MCP lessons learned:**

- Never `print()` in a stdio server, because it corrupts the protocol.
- Return dicts, not lists.
- A generic "Error executing tool" means a Python crash. Debug by calling the function directly.

## 3. The bridge: `agent/mcp_bridge.py`

`McpTools` is an async context manager:

- It starts the server as a subprocess and keeps one session open (`AsyncExitStack`).
- It turns the MCP tool schemas into Gemini `FunctionDeclaration`s automatically, in a comprehension with no hand-written schemas.
- `call()` always returns a dict, `{"error": ...}` on failure, so the agent loop never crashes.

Because the agents only know "MCP tools", the same agents could plug into any other MCP server (BigQuery, for example) without code changes.

## 4. Eval harness: `evals/`

- `questions.json`: each question has a **gold SQL** query written by hand.
- **Execution accuracy**: the harness compares the *results* of the agent's SQL and the gold SQL, not the SQL text, because two different queries can be equally correct.
- `scorer.py` rules (tested by `checks/check_m2.py`, 10/10):
  - floats are rounded to 2 decimals; strings are lowercased and stripped;
  - row order is ignored unless the question is marked `ordered`;
  - mixed `None`/string values are sorted safely.
- Each run saves `runs/<agent>-<timestamp>.json` with, per question: correct or not, agent SQL, error, LLM calls, tool steps, the final answer, and (for the crew) the plan and the critic's verdicts. The file is written inside the loop, so a crash doesn't lose finished questions.

**First lesson: the easy set was useless.** The first 20 questions scored 20/20 because they hinted at the columns to use. They are kept in `questions_easy.json`. They were replaced by **15 hard questions** (h01–h15) that look like real business questions: "repeat customers", "late deliveries", "per order", with no column hints.

## 5. Single agent: `agent/single.py`

This is a classic tool loop:

1. Send the question, the system prompt and the tool declarations to Gemini.
2. If the model asks for tools, run them through MCP and send the results back.
3. Repeat, up to 10 steps.
4. Take the last ```` ```sql ```` block in the answer as the final query.

### Failure analysis (what actually goes wrong)

Reading the run JSONs question by question showed four families of errors:

| Type | Example | Explanation |
|---|---|---|
| **Grain error** | h04: a review counted once per *item* instead of once per *order* | Joining `order_items` duplicates rows; averages and counts get skewed |
| **Empty answer** | h09, h15: no final SQL block | The agent found the right query, then ran out of steps or forgot the final block |
| **Definition** | h05: "late" by timestamp vs by calendar day | The question is vague and the agent picks a different reasonable meaning |
| **Semantics** | h10: `COUNT(*) > 1` instead of `COUNT(DISTINCT payment_type) > 1` | It counts payment rows, not payment *methods* |

The most common was the **grain error**, so the crew was designed around it.

## 6. The crew: `agent/crew.py`

A crew is **not a new kind of AI**. It is the same loop, run three times with three different system prompts. The text one agent writes becomes the input of the next.

- **Planner** (max 4 steps) writes four lines before any SQL exists:
  - `UNIT` (what one counted thing is)
  - `TABLES`
  - `DEFINITIONS`
  - `RESULT SHAPE`
- **Worker** (max 10 steps, the same budget as the single agent) follows the plan and writes the SQL.
- **Critic** (max 3 steps) judges the query and answers `VERDICT: ok` or `VERDICT: retry` plus a reason. On retry, the reason goes back to the Worker, at most once.

Design choices:

- **Verify, don't believe.** The orchestration code itself runs the Worker's SQL and shows the Critic the *real* first rows, not the Worker's description of them.
- **Code fallback.** If the Worker gives no SQL block, the code takes the last `run_sql` that succeeded.
- **Forced final answer.** If an agent is still calling tools when its steps run out, it is told "Stop using tools now. Give your final answer." This fixed empty plans on h01 and h08.
- **One shared LLM object**, so `llm_calls` counts the cost of the whole crew.
- The plan and the critiques are saved, so every failure can be explained afterwards.

### Critic v1 → v2

- **v1** rubber-stamped everything: 0 retries in 15 questions, and the same score as the single agent.
- **v2** must do a measurable grain check: compare `COUNT(*)` with `COUNT(DISTINCT key)`, cite the numbers, and default to retry when unsure.
  - On the same 11 questions, v2 scored **9/11 vs 7/11** for v1 and the single agent.
  - Example: on h04 the critic found 110,750 joined rows for 96,320 reviews and sent the Worker back.

### Remaining crew failures (latest run, 3.5-flash-lite)

- **h04: the critic was fooled by its own check.** Its first retry was correct (duplicated reviews). The Worker's "fix" still duplicated them. The critic then checked `COUNT(DISTINCT category)`, the wrong key, and approved. A grain check is only as good as the key chosen.
- **h05: definition ambiguity.** "Late" is ambiguous, and neither role can know which meaning the gold SQL uses.
- **h10: the planner hedged.** It wrote `MAX(payment_sequential) > 1 OR COUNT(DISTINCT payment_type) > 1`. The grain is right, but the meaning is wrong, so a grain check can't catch it.

**Conclusion:** the crew fixes *structural* errors (grain, empty answers) but not *semantic* ones (what a word means). For those, a human or a business glossary is still needed.

---

## All runs (chronological)

| # | Model | Questions | Single | Crew |
|---|---|---|---|---|
| 0 | 3.5-flash-lite | 20 easy | 20/20 | (none; the set was too easy and was replaced) |
| 1 | 3.5-flash-lite | 15 hard | 11/15, 81 calls | v1: 11/15, 146 calls |
| 2 | 3.5-flash-lite | 11 hard (subset) | 7/11, ~60 calls | v1: 7/11 · v2: **9/11**, 132 calls |
| 3 | 3.1-flash-lite | 15 hard | 8/15, 92 calls | 12/15, 226 calls |
| 4 | 3.5-flash-lite | 15 hard | 10/15, 87 calls | 12/15, 173 calls |

Note: the single agent scored 11/15 in run 1 and 10/15 in run 4 with the same code and model. That is the size of the run-to-run noise.

---

## Honest caveats

- **One run per configuration.** LLMs are not deterministic: the same single agent scored 11 and 10 on two runs. A gap of 1–2 questions is within that noise.
- **Unfair fallback.** The crew has the "last successful SQL" fallback and the single agent doesn't. h09 and h15 failed on the single agent for that reason alone.
- **Small question set** (15 questions), written by one person, with gold SQL that encodes one interpretation of vague words.
- **Mixed models.** The free tier sometimes falls back to another model on 503/429 errors, and the model used for each question wasn't recorded.
- **h11 scorer strictness.** `strftime('%w')` returns text (`'1'`) while the gold returns an integer. I chose **not** to change the scorer after seeing results, so that the scorer isn't tuned to make one agent win.
- Run 2 used a subset of 11 questions, so it isn't directly comparable with the 15-question runs.

## Next steps

1. Add the same fallback to `single.py` and re-run, for a fair comparison.
2. Run each configuration 3–5 times and report mean ± spread.
3. Record the model used for every question.
4. **Human in the loop.** If the Critic still says "retry" after the last attempt, flag the answer for human review instead of returning it silently.
5. Pass the Planner's schema notes to the Worker, so it doesn't re-explore tables (wasted calls).
6. Make the critic's key explicit: the Planner names the dedup key in `UNIT`, and code (not the LLM) runs the `COUNT` vs `COUNT DISTINCT` check.
7. A business glossary ("late = delivered after estimated date") given to all roles, for definition errors.
8. Swap the SQLite MCP server for a BigQuery one: the agents don't change.

---

## How to run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# put the Olist CSVs in data/raw/, then
python data/load.py

python -m checks.check_m1          # server tests
python -m checks.check_m2          # scorer tests

$env:GEMINI_API_KEY="your-key"     # never commit it (.env is gitignored)
python evals/run_eval.py --agent single
python evals/run_eval.py --agent crew
```

## Project layout

```
data/load.py              CSV -> SQLite + indexes
server/olist_server.py    MCP server (3 tools, guardrails)
agent/mcp_bridge.py       MCP client -> Gemini tool declarations
agent/llm.py              Gemini adapter (retries, pacing, fallback, call counter)
agent/single.py           single agent loop
agent/crew.py             planner / worker / critic orchestration
evals/questions.json      15 hard questions + gold SQL
evals/scorer.py           result comparison rules
evals/run_eval.py         runs an agent on all questions, saves runs/*.json
checks/                   small test scripts
runs/                     every run's raw output (kept on purpose, for transparency)
```
