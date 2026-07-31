# Try AIMarket MCP in Cursor

Connect Cursor to AIMarket's hardened web search and fetch tools over local
stdio. No API key is required for the basic `web_search` smoke test.

## 1. Install the server

```bash
pip install aimarket-mcp
```

## 2. Add it to Cursor

Open Cursor's global MCP configuration at `~/.cursor/mcp.json` and add:

```json
{
  "mcpServers": {
    "aimarket-web": {
      "command": "aimarket-mcp",
      "args": []
    }
  }
}
```

Restart Cursor or reload its MCP servers, then confirm `aimarket-web` is
connected in **Settings → Tools & MCP**.

## 3. Smoke-test `web_search`

In Cursor Agent chat, ask: **Use `web_search` with query `site:modelmarket.dev` and return the first result.**

Cursor asks for tool approval by default. Review the arguments, then approve
the call.

## Optional: add the oracle gateway

Install the second package:

```bash
pip install aimarket-oracle-gateway
```

To try the oracle gateway separately, use this complete configuration:

```json
{
  "mcpServers": {
    "aimarket-oracle-gateway": {
      "command": "python",
      "args": ["-m", "aimarket_oracle_gateway.stdio_server"],
      "env": {
        "AIMARKET_HUB_URL": "https://modelmarket.dev"
      }
    }
  }
}
```

The live Hub may meter oracle calls. The gateway's spending controls and
payment setup are documented in [MCP payment and security](specs/03-mcp-payment-and-security.md).
