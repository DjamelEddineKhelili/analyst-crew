"""
MILESTONE 1b — An MCP server that exposes the Olist database to any agent.

Run directly to check it starts:   python server/olist_server.py   (it waits silently; Ctrl+C to stop)
Real test:                          python checks/check_m1.py

THE CONTRACT (checks/check_m1.py tests exactly this):
  list_tables()          -> {"tables": ["customers", "orders", ...]}
  describe_table(table)  -> {"table": ..., "row_count": int,
                             "columns": [{"name": ..., "type": ...}, ...],
                             "sample": [[...], [...], [...]]}          # 3 example rows
  run_sql(sql)           -> {"columns": [...], "rows": [[...], ...], "truncated": bool}

  Bad input (unknown table, non-SELECT, two statements, SQL error) -> raise ToolError("clear message").
  The agent reads that message, so make it useful: say what was wrong AND what is allowed.

Why return dicts and not lists? See CHEATSHEET.md, "MCP gotchas".
"""
import sqlite3
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "olist.db"
MAX_ROWS = 100

mcp = MCPServer("olist")


def _connect():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)  # read-only
    return con


@mcp.tool()
def list_tables() -> dict:
    """List the tables you can query in the Olist e-commerce database."""
    con = _connect()
    
    tables = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    
    con.close()
    return {"tables": [table[0] for table in tables]}


@mcp.tool()
def describe_table(table: str) -> dict:
    """Show a table's columns, types, row count and 3 sample rows. Call this before writing SQL on a table."""
    
    if table not in list_tables()["tables"]:
        raise ToolError(f"Unknown table: {table}. Use list_tables() to see available tables.")
    # TODO 1: refuse names that are not real tables (compare with list_tables()["tables"]).
    #         Why: `table` ends up inside an f-string -> SQL injection if you don't check it.
    con = _connect()
    # TODO 2: columns from PRAGMA table_info, row_count from COUNT(*), sample from LIMIT 3.
    columns = con.execute(f"PRAGMA table_info({table})").fetchall()
    row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    sample = con.execute(f"SELECT * FROM {table} LIMIT 3").fetchall()

    con.close()
    return {"table": table, "row_count": row_count, "columns": [{"name": col[1], "type": col[2]} for col in columns], "sample": sample}


@mcp.tool()
def run_sql(sql: str) -> dict:
    """Run ONE read-only SQLite SELECT (or WITH ... SELECT) query. Returns at most 100 rows."""
    # Accept one SELECT/WITH statement only; reject any extra SQL statements.
    sql = sql.strip()
    if not sql:
        raise ToolError("SQL is empty. Send a SELECT or WITH ... SELECT query.")
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    if ";" in sql:
        raise ToolError("Only one SQL statement is allowed. Remove any extra semicolons.")
    if not sql.lower().startswith(("select", "with")):
        raise ToolError("Only SELECT and WITH ... SELECT queries are allowed.")

    con = _connect()
    try:
        cursor = con.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        if truncated:
            rows = rows[:MAX_ROWS]
    except sqlite3.Error as e:
        raise ToolError(f"Database error: {e}")
    finally:
        con.close()

    return {"columns": columns, "rows": rows, "truncated": truncated}


if __name__ == "__main__":
    mcp.run()  # stdio by default: the client starts this file as a subprocess and talks through stdin/stdout
