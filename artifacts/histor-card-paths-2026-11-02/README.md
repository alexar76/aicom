# Where MCP servers put their cards: a count on 2026-11-02

HISTOR reads `<endpoint>/server-card` and `/.well-known/mcp/server-card.json` (`histor/histor/cards.py`).
After five hourly passes (15,000 endpoints) 8,388 endpoints on 7,330 hosts had neither (`absent`).

`cards_absent.py` (run inside `histor-histor-1`, read-only) lists them; `alt_cards.py` fetched three other paths on a
random 400 of those hosts (seed 20261102, one GET per path, own User-Agent, no redirects followed off-host).

| Path | 200 with a card | with a tool list |
|---|---:|---:|
| `/.well-known/mcp.json` | 34 | 16 (4 complete: every tool has an `inputSchema`) |
| `/.well-known/mcp/server-cards.json` | 1 | 0 |
| `/.well-known/mcp-server-card.json` | 0 | 0 |

The rest were 404 (356 of 400 on the first two paths, 318 on `mcp.json`), 401/403/402, or HTML.
Scaled to 7,330 hosts: about 620 `mcp.json` documents and about 70 complete tool lists (the only ones HISTOR declares),
against 783 declared sets so far. A later look at the 34 documents (same day) found the other 12 tool lists carry
names, descriptions or prices without schemas.
`mcp.json` documents seen name the endpoint as `transport.url` or `mcpUrl` (mart402.com), which
`cards.named_endpoints` does not read yet.

The sample checked only these paths' HTTP answers; robots.txt was not consulted for them (the hosts' standard card
paths had been allowed). A HISTOR change must read `mcp.json` through its robots policy like the other paths.
