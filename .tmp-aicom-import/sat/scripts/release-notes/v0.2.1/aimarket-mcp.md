# aimarket-mcp v0.2.1

Fix stdio `serverInfo.version`: FastMCP was advertising the MCP SDK version (`1.28.x`) instead of ours. Glama / Claude Desktop / Cursor now see `0.2.1`.

## Changes
- Set `mcp._mcp_server.version = __version__` on the stdio entry point
- Bump pyproject / server.json / `__version__` to **0.2.1**

Source: monorepo path `aimarket-mcp` · https://github.com/alexar76/aimarket-mcp
