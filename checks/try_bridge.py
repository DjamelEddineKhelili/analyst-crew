

import asyncio
from agent.mcp_bridge import McpTools


async def main():
    async with McpTools("server/olist_server.py") as tools:
        print("Tools:", [t.name for t in tools.tools])
        print(await tools.call("run_sql", {"sql": "SELECT COUNT(*) FROM orders"}))
        print(await tools.call("run_sql", {"sql": "DROP TABLE orders"}))

asyncio.run(main())