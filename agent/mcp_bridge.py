"""
MILESTONE 3a — The bridge between your agent and ANY MCP server.

This is the big idea of MCP: the agent does NOT import the tools. It asks the server
"what tools do you have?" and gets names + descriptions + JSON schemas back.
Swap the server for another one (a BigQuery server, a CRM server...) and the agent still works.

Usage (from an async function):

    async with McpTools("server/olist_server.py") as tools:
        decls = tools.gemini_declarations()          # give these to Gemini
        result = await tools.call("run_sql", {"sql": "SELECT 1"})

checks/check_m1.py already contains a working MCP client. Read it before starting.
"""
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class McpTools:
    def __init__(self, server_script: str):
        self.server_script = server_script
        self.session: ClientSession | None = None
        self.tools = []                   # filled in __aenter__: the list returned by session.list_tools()
        self._stack = AsyncExitStack()    # keeps the subprocess + session alive between calls

    async def __aenter__(self):
        # TODO 1: build StdioServerParameters (command = sys.executable, args = [self.server_script]).
        # TODO 2: read, write = await self._stack.enter_async_context(stdio_client(params))
        # TODO 3: self.session = await self._stack.enter_async_context(ClientSession(read, write))
        # TODO 4: await self.session.initialize(), then fill self.tools.
        #  WHY AsyncExitStack: `async with` blocks close when the block ends. The stack lets us keep
        #  them open for the whole agent run and close everything at once in __aexit__.
        raise NotImplementedError

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    def gemini_declarations(self) -> list:
        """Convert MCP tools into Gemini FunctionDeclarations.
        TODO: one types.FunctionDeclaration per tool: name, description, parameters_json_schema=tool.input_schema
        (CHEATSHEET.md, "MCP tools -> Gemini").
        """
        raise NotImplementedError

    async def call(self, name: str, args: dict) -> dict:
        """Call a tool and ALWAYS return a plain dict, even on error (the LLM must see errors, not crash on them).
        TODO: result = await self.session.call_tool(name, args)
              if result.is_error -> return {"error": <the text>}
              else -> return the data (structured_content, or json.loads of the text)
        """
        raise NotImplementedError
