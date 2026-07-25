# Try AIMarket MCP in Cursor

This setup gives Cursor the `web_fetch`, `web_search`, and `metis_verify`
tools through a local stdio MCP server.

## Install

```bash
python -m pip install aimarket-mcp
```

## Connect Cursor

Create `.cursor/mcp.json` in your project (or use **Cursor Settings → MCP → Add
new global MCP server**) and paste:

```json
{
  "mcpServers": {
    "aimarket-mcp": {
      "command": "aimarket-mcp"
    }
  }
}
```

Restart Cursor or reload the MCP server, then confirm `aimarket-mcp` appears as
connected in Cursor's MCP settings.

## Smoke test

In Cursor Agent mode, ask: **Use `web_search` with the query
`site:modelmarket.dev`.**

## Optional: oracle gateway

To add the 17-family oracle gateway, install it and add a second server that
points to the live AIMarket Hub:

```bash
python -m pip install aimarket-oracle-gateway
```

```json
{
  "mcpServers": {
    "aimarket-oracle-gateway": {
      "command": "aimarket-oracle-gateway",
      "env": {
        "AIMARKET_HUB_URL": "https://modelmarket.dev"
      }
    }
  }
}
```

Merge this server into the same `mcpServers` object if you use both gateways.
