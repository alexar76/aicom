First stable release of **aimarket-oracle-gateway** — passthrough MCP server for verifiable oracle services over the AIMarket protocol.

## MCP tools (11)
- **Platon:** `get_random`, `get_randomness_beacon`, `ask_oracle`, `verify_random`
- **Chronos:** `compute_vdf`, `verify_vdf`
- **LUMEN:** `get_reputation_scores`, `get_agent_trust`, `verify_reputation`
- **Discovery:** `list_oracle_capabilities`

## Run locally
```bash
pip install -r requirements-mcp.txt && pip install --no-deps -e .
AIMARKET_HUB_URL=https://modelmarket.dev python mcp_stdio_server.py
```

## Glama
- Listing: https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway
- Hosted release: `1.0.0` (`registry.glama.ai/mcp-yks6euxy28:vriem9c9cd`)
