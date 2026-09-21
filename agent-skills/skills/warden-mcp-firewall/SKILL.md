---
name: warden-mcp-firewall
description: Vets advertised MCP tool definitions with the WARDEN firewall (npx -y @aimarket/warden). Use when the user wants an MCP security scan, tool-definition firewall, vet_mcp_server, static_scan_tools, or to check a tools/list dump before it reaches the model.
---

# WARDEN MCP firewall

WARDEN vets a server **before any of its tools reach the model**. It does not start, proxy, or sandbox another MCP server — you pass a `tools/list` dump in, you get a verdict out.

```bash
npx -y @aimarket/warden
```

## Add the server

Cursor / Claude Desktop `mcpServers` entry (stdio):

```json
{
  "mcpServers": {
    "warden": {
      "command": "npx",
      "args": ["-y", "@aimarket/warden"]
    }
  }
}
```

No API keys. Node >= 20. Package: `@aimarket/warden`. Docs: https://github.com/alexar76/warden

## Tools

| Tool | When to use |
|------|-------------|
| `vet_mcp_server` | Full gate chain on a server identity + advertised tools |
| `static_scan_tools` | Injection / exfil scan only (no origin / pinning / threat feed) |
| `classify_sensitive_tools` | Operator glob split — not an injection scan |
| `check_egress_url` | Hostname allowlist (empty list denies every host) |
| `canonicalize_json` | RFC 8785 bytes for feeds and pins |
| `list_scan_rules` | Published rule table + digest |

Typical flow: obtain the other server's `tools/list` → `vet_mcp_server` (or `static_scan_tools` for a defs-only pass) → record allow/block, score, findings, `allowedTools` / `blockedTools`.

## What it is not

- Not a proxy in front of other MCP servers
- Not a marketplace client (`market_search` / `market_invoke` live on https://modelmarket.dev/mcp — see `aimarket-hub-mcp`)
- First-screen copy stays firewall / `tools/list`. Do not lead with wallets or tokens.

## Crypto off

Do not lead with USDC, Base, ACEX, or lottery.
