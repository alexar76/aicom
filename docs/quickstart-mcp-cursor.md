# Try MCP in Cursor

Paste-ready setup for [aimarket-mcp](https://github.com/alexar76/aimarket-mcp) in Cursor. No Docker, no clone.

## 1. Install

```bash
pip install aimarket-mcp
```

Python 3.10+. Or skip the install and let Cursor run `uvx` (below).

## 2. Cursor `mcp.json` (stdio)

Project: `.cursor/mcp.json`. User-wide: Cursor Settings → MCP.

With `uvx` (fetches the published package):

```json
{
  "mcpServers": {
    "aimarket-mcp": {
      "command": "uvx",
      "args": ["aimarket-mcp"]
    }
  }
}
```

With a local install:

```json
{
  "mcpServers": {
    "aimarket-mcp": {
      "command": "aimarket-mcp"
    }
  }
}
```

Reload the Cursor window after saving.

## 3. Smoke

In chat, ask the model to call `web_search` with:

```text
site:modelmarket.dev
```

You should get live snippets. Then try `web_fetch` on a public HTTPS page, or `metis_verify` on a short factual question (optional `AIMARKET_METIS_KEY` if the live Metis node returns 401).

## Optional: Hub oracles via aimarket-oracle-gateway

Same Cursor file, second server — points at the live Hub:

```json
{
  "mcpServers": {
    "aimarket-mcp": {
      "command": "uvx",
      "args": ["aimarket-mcp"]
    },
    "aimarket-oracle-gateway": {
      "command": "uvx",
      "args": ["--from", "aimarket-oracle-gateway", "aimarket-oracle-gateway"],
      "env": {
        "AIMARKET_HUB_URL": "https://modelmarket.dev"
      }
    }
  }
}
```

Hosted Hub MCP (no local process): paste `https://modelmarket.dev/mcp` as a Streamable HTTP server in Cursor MCP settings.

More detail: [aimarket-mcp README](https://github.com/alexar76/aimarket-mcp#readme) · [agent install](agent-install/README.md).
