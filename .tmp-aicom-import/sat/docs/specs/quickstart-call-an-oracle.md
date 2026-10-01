# Quick-start — call a verifiable oracle (for AI agents & devs)

Get **verifiable randomness** (or any oracle capability) into your agent in ~5 lines. Three steps:
**discover → call → verify**. Pay-per-call over the AIMarket protocol; every result is checkable.

## 1. Discover (any one)
- **Glama** — browse `glama.ai` for `aimarket-oracle-gateway`, add it to your MCP client.
- **Hub well-known** (signed) — `GET https://modelmarket.dev/.well-known/ai-market.json` → read
  `mcp_servers` (the gateway + its tools) and `prices_url`.
- **Prices** — `GET https://modelmarket.dev/ai-market/v2/prices` → signed list of `{capability_id,
  price_usd}`.

## 2. Call

### Via MCP (the 5-line path — for an agent host like Claude Desktop / Cursor)
Add the gateway to your MCP config, then just ask the agent ("give me verifiable randomness"):
```json
{ "mcpServers": { "aimarket-oracle-gateway": {
  "command": "python", "args": ["mcp_stdio_server.py"],
  "env": { "AIMARKET_HUB_URL": "https://modelmarket.dev",
           "AIMARKET_MAX_SPEND_USD": "1.0" } } } }
```
The agent now sees tools `get_random`, `compute_vdf`, `verify_vdf`, `get_reputation_scores`, … and
calls them directly. Spend is hard-capped by `AIMARKET_MAX_SPEND_USD` (the gateway refuses past it).

### Via raw HTTP (any language)
```bash
curl -s https://modelmarket.dev/ai-market/v2/invoke \
  -H 'content-type: application/json' \
  -d '{"capability_id":"platon.random@v1","input":{"num_bytes":32}}'
# → { "output": { "random_hex": "...", "proof": {...}, "signature": {...} }, "price_usd": 0.004, "receipt": {...} }
```

## 3. Verify (trust the math, not the service)
- **Randomness** — call `verify_random` (MCP) or `platon.verify@v1` (HTTP) with the
  `{random_hex, proof, signature}`; it checks the Ed25519 signature against the signer key in the
  signed `/.well-known`.
- **VDF** — `verify_vdf` / `chronos.verify@v1` confirms `y = g^(2^T) mod N` in one exponentiation
  (the result also carries `modulus_hex` for a fully explicit check).
- **Reputation** — `verify_reputation` / `lumen.verify@v1` re-derives PageRank over your graph and
  confirms the scores (+ `graph_commitment`).

## 4. Pay & stay safe
- Open a USDC payment channel (escrow on Base) and the hub debits per call; settle/refund on close.
  See [03-mcp-payment-and-security.md](03-mcp-payment-and-security.md).
- The gateway enforces **hard spending caps** (`AIMARKET_MAX_PER_CALL_USD`, `AIMARKET_MAX_SPEND_USD`)
  and **rejects overcharge** vs the advertised price — a prompt-injected agent can't drain you.

## Catalog
| Capability | Tool | Price |
|---|---|---|
| `platon.random@v1` / `platon.beacon@v1` | `get_random` / `get_randomness_beacon` | ~$0.004 |
| `platon.ask@v1` | `ask_oracle` | ~$0.003 |
| `platon.verify@v1` | `verify_random` | ~$0.001 |
| `chronos.eval@v1` / `chronos.verify@v1` | `compute_vdf` / `verify_vdf` | ~$0.01 / $0.001 |
| `lumen.reputation@v1` / `lumen.score@v1` / `lumen.verify@v1` | `get_reputation_scores` / `get_agent_trust` / `verify_reputation` | ~$0.005 / $0.003 / $0.002 |

Full program + per-oracle specs: [docs/specs/README.md](README.md).
