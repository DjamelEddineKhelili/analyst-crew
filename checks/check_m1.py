"""
Milestone 1 acceptance check. You don't need to edit this file.

    python checks/check_m1.py

It starts your server exactly like an agent would (as an MCP subprocess) and tests the contract.
Read it: it's also a working example of an MCP client.
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server" / "olist_server.py"
passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}  {detail}")


def refused(result, tool):
    """A deliberate refusal: is_error AND a real message. A crash (or a TODO) only gives the generic text."""
    text = result.content[0].text.strip() if result.content else ""
    return result.is_error and text != f"Error executing tool {tool}"


def data(result):
    """Turn an MCP CallToolResult back into a Python dict."""
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def main():
    if not (ROOT / "data" / "olist.db").exists():
        sys.exit("data/olist.db not found. Finish data/load.py first.")

    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Tools")
            tools = {t.name: t for t in (await session.list_tools()).tools}
            for name in ("list_tables", "describe_table", "run_sql"):
                check(f"tool '{name}' exists", name in tools)
                if name in tools:
                    check(f"tool '{name}' has a description", bool(tools[name].description))

            print("list_tables")
            r = await session.call_tool("list_tables", {})
            tables = data(r).get("tables", []) if not r.is_error else []
            check("returns {'tables': [...]}", isinstance(tables, list) and tables, str(r.content)[:200])
            check("has 'orders'", "orders" in tables)
            check("has all 9 Olist tables", len(tables) >= 9, f"found {len(tables)}: {tables}")

            print("describe_table")
            r = await session.call_tool("describe_table", {"table": "orders"})
            d = {} if r.is_error else data(r)
            check("orders: has columns", any(c.get("name") == "order_id" for c in d.get("columns", [])), str(d)[:200])
            check("orders: row_count ~99k", 90_000 < d.get("row_count", 0) < 110_000, f"got {d.get('row_count')}")
            check("orders: 3 sample rows", len(d.get("sample", [])) == 3)
            r = await session.call_tool("describe_table", {"table": "orders; DROP TABLE orders"})
            check("unknown/malicious table name -> clear ToolError", refused(r, "describe_table"),
                  "(raise ToolError with a message, not a plain exception)")

            print("run_sql")
            r = await session.call_tool("run_sql", {"sql": "SELECT order_status, COUNT(*) FROM orders GROUP BY 1"})
            d = {} if r.is_error else data(r)
            check("SELECT works", len(d.get("rows", [])) > 0 and len(d.get("columns", [])) == 2, str(r.content)[:200])
            r = await session.call_tool("run_sql", {"sql": "select order_id from orders"})
            d = {} if r.is_error else data(r)
            check("row cap: at most 100 rows", len(d.get("rows", [])) <= 100, f"got {len(d.get('rows', []))}")
            check("row cap: truncated=True", d.get("truncated") is True)
            r = await session.call_tool("run_sql", {"sql": "WITH x AS (SELECT 1 AS n) SELECT n FROM x;"})
            check("WITH ... SELECT and trailing ';' accepted", not r.is_error, r.content[0].text[:200] if r.content else "")

            for bad, why in [("DELETE FROM orders", "DELETE"),
                             ("DROP TABLE orders", "DROP"),
                             ("SELECT 1; DROP TABLE orders", "two statements"),
                             ("UPDATE orders SET order_status = 'x'", "UPDATE")]:
                r = await session.call_tool("run_sql", {"sql": bad})
                check(f"refuses {why} with a clear ToolError", refused(r, "run_sql"),
                      "(raise ToolError with a message, not a plain exception)")

            r = await session.call_tool("run_sql", {"sql": "SELECT nope FROM orders"})
            msg = r.content[0].text if r.content else ""
            check("SQL error comes back as a readable error", r.is_error and "nope" in msg, msg[:200])

            r = await session.call_tool("run_sql", {"sql": "SELECT COUNT(*) FROM orders"})
            d = {} if r.is_error else data(r)
            check("database still intact after the attacks", d.get("rows", [[0]])[0][0] > 90_000)

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
