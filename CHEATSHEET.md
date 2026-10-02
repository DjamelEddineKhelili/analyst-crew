# Cheat sheet — the commands you'll actually use

Every snippet here was run against the real libraries (mcp 2.2, google-genai, pandas, sqlite3).
Small on purpose: the shape of the call, not the solution.

---

## 0. Setup (Windows cmd)

```bat
python -m venv .venv            :: a private Python just for this project
.venv\Scripts\activate          :: turn it on (your prompt starts with (.venv))
pip install -r requirements.txt
set GEMINI_API_KEY=your_key     :: only lasts for this window
```

---

## 1. pandas → SQLite

```python
import sqlite3, pandas as pd

con = sqlite3.connect("data/olist.db")
df = pd.read_csv("data/raw/olist_orders_dataset.csv")
df.to_sql("orders", con, index=False)        # creates the table and inserts every row
len(df)                                      # number of rows
con.close()
```
`index=False`: otherwise pandas adds a useless column called `index`.

---

## 2. sqlite3 essentials

**Read-only connection** (cannot modify anything, whatever the SQL says):
```python
con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
```

**Run a query:**
```python
cur = con.execute("SELECT order_status, COUNT(*) FROM orders GROUP BY 1")
cur.description          # column info: [("order_status", None, ...), ("COUNT(*)", None, ...)]
[d[0] for d in cur.description]   # -> column names
cur.fetchmany(101)       # at most 101 rows, as tuples
cur.fetchall()           # all rows (careful on big tables)
```

**Parameters** (never build values into SQL with f-strings):
```python
con.execute("SELECT * FROM orders WHERE order_status = ?", ("delivered",))
```
Table names can't be `?` parameters. That's why `describe_table` must check the name against the real list first.

**Introspection:**
```python
con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
con.execute(f"PRAGMA table_info({table})").fetchall()
#   -> rows of (cid, name, type, notnull, default, pk). You want index 1 (name) and 2 (type).
```

**Errors:** everything SQLite raises inherits from `sqlite3.Error`.
```python
try:
    con.execute(sql)
except sqlite3.Error as e:
    str(e)               # "no such column: nope" — give this to the agent
```

---

## 3. MCP server (mcp 2.x)

⚠️ Most tutorials online use the OLD API (`from mcp.server.fastmcp import FastMCP`). In 2.x it crashes. Use:

```python
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("olist")

@mcp.tool()
def add(a: int, b: int) -> dict:
    """This docstring becomes the tool description the LLM reads. Write it for the LLM."""
    if a < 0:
        raise ToolError("a must be positive")   # the LLM sees this message
    return {"sum": a + b}

if __name__ == "__main__":
    mcp.run()          # stdio: talks through stdin/stdout
```
The type hints (`a: int`) become the JSON schema automatically. The docstring becomes the description.

### MCP gotchas (found while testing, save yourself an hour)

| Gotcha | What happens | Do this |
|---|---|---|
| `raise ValueError("...")` | The client only sees `Error executing tool run_sql`, **your message is hidden** | `raise ToolError("...")` |
| Returning a `list` | It is split into several content items; `content[0].text` is only the first element | Return a `dict` |
| `print()` in the server | stdout **is** the protocol channel; a print corrupts it and the client hangs or crashes | `print(..., file=sys.stderr)` |
| `tool.inputSchema` | AttributeError in 2.x | `tool.input_schema` |

---

## 4. MCP client

```python
import asyncio, sys
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def main():
    params = StdioServerParameters(command=sys.executable, args=["server/olist_server.py"])
    async with stdio_client(params) as (read, write):          # starts the server as a subprocess
        async with ClientSession(read, write) as session:
            await session.initialize()                          # handshake, always first

            tools = (await session.list_tools()).tools
            tools[0].name, tools[0].description, tools[0].input_schema

            result = await session.call_tool("run_sql", {"sql": "SELECT 1"})
            result.is_error              # True if the tool raised
            result.structured_content    # the dict you returned (or None)
            result.content[0].text       # same thing as text (JSON string), or the error message

asyncio.run(main())
```

---

## 5. async in 60 seconds

- `async def f()` defines a function that must be **awaited**: `await f()`.
- You can only write `await` inside another `async def`.
- The very top of the program starts it with `asyncio.run(main())`.
- `async with X as y:` is a `with` block whose opening/closing are async (MCP connections are).
- The Gemini call (`client.models.generate_content`) is normal, not async: just call it inside your async function. That's fine here.

---

## 6. MCP tools → Gemini

```python
from google import genai
from google.genai import types

decl = types.FunctionDeclaration(
    name=tool.name,
    description=tool.description,
    parameters_json_schema=tool.input_schema,     # the MCP schema plugs in directly
)
config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=[decl, ...])],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # YOU run the loop
)
resp = client.models.generate_content(model=..., contents=..., config=config)
resp.function_calls          # list of calls (name, args, id), or None if the model just talked
resp.candidates[0].content   # the model's message: append it to history UNCHANGED
```

Sending a tool result back:
```python
types.Part(function_response=types.FunctionResponse(id=call.id, name=call.name, response={"result": data}))
```
All of this is already in your retail-agents `pilot/agent.py`. Reuse it.

---

## 7. Eval vocabulary (for your README and your interviews)

- **Gold SQL**: the correct query, written by you.
- **Execution accuracy**: compare query *results*, not query *text*. That's what `scorer.py` does.
- **Baseline**: the single agent. Every improvement is measured against it.
- **Cost**: LLM calls per question. A crew that's 5% better but 3× more expensive is a trade-off, not a win.
- **Regression**: a question the baseline got right and the crew got wrong. Always look at these.

---

## 8. Git, the loop you'll repeat

```bat
git init                       :: once
git status                     :: what changed?
git add .
git commit -m "M1: MCP server with read-only guards"
gh repo create analyst-crew --public --source=. --remote=origin --push   :: once
git push                       :: after each milestone
```
One commit per milestone (at least). Your commit history becomes the story of how you built it.
