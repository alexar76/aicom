=== AI-MARKET NATIVE AGENTS (this factory's ecosystem — non-negotiable when the product invokes mesh SKUs) ===

When the idea, charter, or spec mentions ATLAS, Hub, AI-market, capability ids (`*.*@v1`), sensor mesh,
or "paying participant" / receipts / evidence trail, you are building a **demand-side AI-market agent**,
not a localhost demo client.

**Highest level (preferred)**
- Use factory runtime `aimarket_participant.get_participant().invoke(capability_id, input)` (module is
  vendored beside `atlas_client`) **or** Python `aimarket-agent` / TS `@aimarket/agent`.
- The participant exposes **`.invoke()` only** — never `get_participant()._invoke()` (that helper is
  internal to the vendored module and will 500 on Vercel).
- Runtime session: visitor trial by default; when `AIMARKET_WALLET_KEY` and/or `AIMARKET_PAYMENT_CHANNEL`
  is set, open/reuse a Hub payment channel and send `X-Payment-Channel` (+ secret) on every invoke.
- Soft close via `channel/close` when the process shuts down or the daily budget window ends.

**Endpoint**
- `POST {AIMARKET_HUB_URL}/ai-market/v2/invoke` with body `{"capability_id","input"}` only.
- Default hub: `https://modelmarket.dev`. Never ship `http://localhost:8001` or legacy `/aimarket/invoke`.

**Payment facts**
- Trial: `X-AIMarket-Sandbox-Visitor` (`AIMARKET_SANDBOX_VISITOR`) — no wallet required.
- Paid: server-side wallet / channel only; never put a private key in the browser widget.
- Escrow on Base: **MIN_DEPOSIT = $1 USDC** (0.10 cannot open an escrow channel).
- `X-Agent-Key` / `demo-atlas-key` is **not** billing.

**Config:** `AIMARKET_HUB_URL`, `AIMARKET_SANDBOX_VISITOR`, optional `AIMARKET_WALLET_KEY`,
`AIMARKET_PAYMENT_CHANNEL`, `AIMARKET_PAYMENT_CHANNEL_SECRET`.
