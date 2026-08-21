# aimarket-mcp v0.2.0

Marketplace tools on stdio (not only Streamable-HTTP), and one version string instead of four.

## Highlights
- **`market_search` / `market_invoke`** now registered on the stdio entry point (`mcp_stdio_server.py`) so Claude Desktop, Cursor, and Glama see five tools — not three
- Single source of truth: `__init__.__version__` = **0.2.0**; `serverInfo`, User-Agent, `pyproject.toml`, and `server.json` agree
- Trial-tier `market_invoke` against live `modelmarket.dev` (signed receipt; `402` when allowance is spent — no invented results)
- README documents both tools, `AIMARKET_HUB_URL`, and `AIMARKET_SANDBOX_VISITOR`

## Notes
- PyPI still had **0.1.4**; this GitHub tag/release is **0.2.0** so Glama / MCP Registry track the feature release. Re-publish to PyPI separately when ready.

Source: monorepo path `aimarket-mcp` · https://github.com/alexar76/aimarket-mcp
