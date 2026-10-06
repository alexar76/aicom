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

Search this hub's catalogue of live data and computation by what you need, in plain words. Each match gives the product_id, capability_id and source_hub to pass to market_invoke, its price, and `input`: the fields its input object takes.

| Field | Required | Notes |
|-------|----------|-------|
| `intent` | yes | What you want done, in plain language. |
| `category` | no | e.g. `security` |
| `budget` | no | Cap on price per call, USD |
| `limit` | no | Default 10, max 50 |

### `market_invoke`

Invoke a capability found via market_search. A few trial invokes are granted per caller with no wallet, key or channel, and each returns the hub's signed receipt; when the allowance is spent the hub answers 402 and this reports that rather than inventing a result, with next_steps saying how to pay. Paid access uses the prepaid balance of an API key sent as this connection's X-API-Key header, payment_channel (+ secret), or an on-chain x402 payment (x_payment + x_payment_nonce + x_payment_secret).

| Field | Required | Notes |
|-------|----------|-------|
| `product_id` | yes | From search |
| `capability_id` | yes | Exact id from search |
| `source_hub` | federated | From search. Required for most of the catalogue. |
| `input` | no | Object; `{}` if the capability takes none |
| `max_price_usd` | no | Copy the search result's price |

### Pipelines and refunds

- `pipeline_prepare` — Validate a graph and return a signed quote and payment offers. No work or payment. Free steps require no wallet; paid steps require buyer wallet address. Use gas_mode=required to demand gas sponsorship or auto to prefer it. Inspect ready/blockers and gas_sponsorship. Sign offers LOCALLY, never provide a private key. Then call pipeline_invoke.
- `pipeline_invoke` — Execute or continue the SAME prepared graph. Submit authorizations when the signed quote enables gas_sponsorship, otherwise buyer-signed transactions; none for free steps. Never submit both payment modes. Retain run_id/access_token and the exact bundle. Pending is not failure; repeat the same run or read pipeline_status. Never create a replacement purchase after a lost response.
- `pipeline_status` — Read an existing pipeline, including cached signed result, without broadcasting payments or invoking providers. No wallet signer or blockchain RPC required. Inspect recovery.action for unresolved work.
- `pipeline_refund_prepare` — Prepare a cash refund for a verified paid step of a finished pipeline. This moves no money. The original seller must approve the exact EIP-3009 authorization locally; never send a private key. Refunds require seller cooperation and a configured gas sponsor.
- `pipeline_refund` — Submit the original seller's refund authorization or resume the SAME refund. The recipient is the original buyer, amount is the paid step price, and the sponsor pays gas. Preserve the exact authorization after a lost response. Returns a separately signed credit note; the original bill is unchanged.
- `pipeline_refund_status` — Read the saved cash-refund status and signed credit note without broadcasting a transaction. No private key or RPC is required. Pending means resume the same refund, never send a replacement transfer.

### `account_status` (only on a connection that carries a key)

Balance of the prepaid API key this connection carries (X-API-Key): what is left, what it has spent, and where to top it up. Call it when a priced call says the balance is short, or before a costly run.

## Federated `source_hub` failure mode

Most of the catalogue is federated. `market_invoke` without `source_hub` looks **locally** and the hub answers **404**. Always pass `source_hub` from the matching `market_search` hit, verbatim. Do not invent or guess a hub URL.

## Trial, then 402

A few trial invokes per caller, then **402**. Trust the live number: `free_trial.max_invokes_per_visitor` in https://modelmarket.dev/.well-known/ai-market.json — do not invent a count. Each successful invoke returns a signed receipt. Free capabilities do not spend the allowance. After 402 the simplest paid path is one API key from https://modelmarket.dev/start (no email; USDC top-up on the same page), added to the MCP server config as the `X-API-Key` header — priced calls are then paid from its balance, and a keyed connection also lists `account_status`. Do not lead with wallets or tokens.

## Crypto off

First-screen and skill copy stay install/URL/tools. Trial then paid is fine. Do not lead with USDC, Base, ACEX, or lottery.

## Do not

- Clone aicom / aimarket-hub just to try the marketplace
- Paraphrase tool descriptions so they drop `source_hub` or the 402
- Call `market_invoke` on a federated hit without `source_hub`
