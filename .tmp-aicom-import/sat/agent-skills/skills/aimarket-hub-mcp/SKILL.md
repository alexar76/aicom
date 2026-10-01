---
name: aimarket-hub-mcp
description: Adds the live AIMarket Hub MCP by URL and runs market_search then market_invoke, always passing source_hub. Use when the user mentions MCP, marketplace, aimarket, modelmarket, market_search, capability, or pasting a Hub MCP URL.
---

# AIMarket Hub MCP

Install nothing. Paste the hosted URL. Two tools. Do not clone the monorepo to try this.

## Add the server

Cursor `.cursor/mcp.json` and Claude Desktop `claude_desktop_config.json` — same shape:

```json
{
  "mcpServers": {
    "aimarket": {
      "type": "streamable-http",
      "url": "https://modelmarket.dev/mcp"
    }
  }
}
```

Transport is Streamable-HTTP (JSON-RPC 2.0 POST). GET `/mcp` returns an info document. Official registry listing: `io.github.alexar76/aimarket-hub` (same URL). Docs: https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md

## Workflow

1. `market_search` with a plain-language `intent`.
2. Copy `product_id`, `capability_id`, `source_hub`, and price from a result.
3. `market_invoke` with those fields plus `input` (`{}` if none). Set `max_price_usd` to the search result's price.

Never invoke without `source_hub` when search returned one.

## Tool contracts (live `tools/list` text)

### `market_search`

Search this hub's capability catalogue by intent. Optional category (e.g. security) and budget filter. Returns matching capability ids, prices and the source_hub to pass back to market_invoke.

| Field | Required | Notes |
|-------|----------|-------|
| `intent` | yes | What you want done, in plain language. |
| `category` | no | e.g. `security` |
| `budget` | no | Cap on price per call, USD |
| `limit` | no | Default 10, max 50 |

### `market_invoke`

Invoke a capability found via market_search. A few trial invokes are granted per caller with no wallet, key or channel, and each returns the hub's signed receipt; when the allowance is spent the hub answers 402 and this reports that rather than inventing a result. Paid access uses payment_channel (+ secret) and, for escrow channels, a payment_authorization object.

| Field | Required | Notes |
|-------|----------|-------|
| `product_id` | yes | From search |
| `capability_id` | yes | Exact id from search |
| `source_hub` | federated | From search. Required for most of the catalogue. |
| `input` | no | Object; `{}` if the capability takes none |
| `max_price_usd` | no | Copy the search result's price |

## Federated `source_hub` failure mode

Most of the catalogue is federated. `market_invoke` without `source_hub` looks **locally** and the hub answers **404**. Always pass `source_hub` from the matching `market_search` hit, verbatim. Do not invent or guess a hub URL.

## Trial, then 402

A few trial invokes per caller, then **402**. Trust the live number: `free_trial.max_invokes_per_visitor` in https://modelmarket.dev/.well-known/ai-market.json — do not invent a count. Each successful invoke returns a signed receipt. Free capabilities do not spend the allowance. After 402, paid access is a separate path; do not lead with wallets or tokens.

## Crypto off

First-screen and skill copy stay install/URL/tools. Trial then paid is fine. Do not lead with USDC, Base, ACEX, or lottery.

## Do not

- Clone aicom / aimarket-hub just to try the marketplace
- Paraphrase tool descriptions so they drop `source_hub` or the 402
- Call `market_invoke` on a federated hit without `source_hub`
