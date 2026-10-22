# aimarket-mcp 0.6.0 — the stdio server uses the tool names its descriptions use

- **Tool names over stdio match everything else.** `uvx aimarket-mcp` used to list `web_fetch_tool`, `web_search_tool`, `metis_verify_tool`, `market_search_tool`, `market_invoke_tool` and `market_status_tool`, while the HTTP gateway, the README and the tool descriptions themselves say `web_fetch`, `market_search`, `market_invoke`. An agent that followed a description ("call market_search first") asked for a tool the stdio server did not have. Both transports now list `web_fetch`, `web_search`, `metis_verify`, `market_search`, `market_invoke` and `market_status`.
- **Breaking for stdio callers that hard-coded the old names.** Clients that read `tools/list` (every MCP host) pick up the new names on their next start.
- **The PyPI page shows its badges.** README images and links are absolute, so they resolve on pypi.org as well as on GitHub.

Since 0.4.1 (in 0.5.0): one description per tool shared by stdio and HTTP, tool annotations (title, read-only except `market_invoke`, never destructive), and `market_status` — free trial left, balance, hub health, without printing the key.

```bash
uvx aimarket-mcp
```
