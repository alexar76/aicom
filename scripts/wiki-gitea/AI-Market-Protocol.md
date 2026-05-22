# AI Market Protocol

**AI-to-AI commerce:** discoverable MCP-compatible capabilities, JSON Schema tool-calling, HTTP **402** payments, payment channels, and DAG pipelines — without human dashboards.

> **Tagline:** *Magic AI-Factory — первый marketplace, где AI продают AI: открытый протокол, on-chain платежи без человека, ваш продукт за час становится оплачиваемым tool'ом в Claude и GPT.*

## Versions

| Version | Doc | Status |
|---------|-----|--------|
| **v1** (current) | [`docs/ai-market-protocol-v1.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/ai-market-protocol-v1.md) | Discovery, 402, channels, pipelines, signed receipts |
| v0 (pilot) | [`docs/ai-market-protocol-v0.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/ai-market-protocol-v0.md) | Product catalog, on-chain settlement confirm, license invoke |

Base path: **`/ai-market`** (no `/api` prefix). Root crawl: **`GET /.well-known/ai-market.json`**.

## v1 endpoints (cheat sheet)

| Endpoint | Purpose |
|----------|---------|
| `GET /.well-known/ai-market.json` | Root manifest (`mcp_endpoint`, chains, tokens) |
| `GET /ai-market/manifest` | Full catalog in MCP tool format (Ed25519 signed) |
| `GET /ai-market/mcp` | MCP `tools` list |
| `POST /ai-market/discover` | Natural language → ranked plan + draft inputs |
| `GET\|POST /ai-market/pricing/{product_id}/{capability_id}` | Quote price for input size |
| `POST /ai-market/channel/open` · `close` | Pre-funded payment channel |
| `POST /capabilities/{product_id}/{capability_id}/invoke` | Invoke; **402** without payment |
| `POST /ai-market/pipelines` | DAG execution + signed bill of materials |
| `GET /ai-market/receipt/{nonce}` | Signed receipt |
| `GET /ai-market/stats` | Live feed (Factory Floor) |

## Payment flow (402)

1. `POST /capabilities/{pid}/{cid}/invoke` → **402** + header `X-Payment-Required` (amount, token, chain, recipient, nonce).
2. Client signs on-chain tx **or** opens a channel: `POST /ai-market/channel/open`.
3. Retry with `X-Payment: {"tx_hash":"0x…"}` or `X-Payment-Channel: ch_…` → **200** + `result`, `receipt`, `continuation`.

## Reference agent (hello world)

```bash
python cli/ai_market_agent.py "translate spec to 5 langs + legal review" --budget 3.0 \
  --base-url https://magic-ai-factory.com
```

Python SDK: `cli/ai_market_sdk.py` — `well_known()`, `manifest_v1()`, `discover()`, `open_channel()`, `invoke_capability_v1()`.

## Environment

| Variable | Meaning |
|----------|---------|
| `AIFACTORY_AI_MARKET_CHAIN` | e.g. `base` |
| `AIFACTORY_AI_MARKET_TOKEN` | e.g. `USDT` |
| `AIFACTORY_AI_MARKET_CONTRACT` | Pilot contract (optional) |
| `AIFACTORY_AI_MARKET_DEMO_PAYMENT` | `1` = accept `demo-*` tx (dev/demo) |
| `AIFACTORY_PUBLIC_URL` | Canonical URLs in manifests |

## Admin: Factory Floor

**Admin → Factory Floor** shows node **🤖 External AI** and recent AI Market spend when external agents invoke capabilities (`/ai-market/stats`).

## Roadmap

| Phase | Content |
|-------|---------|
| 0 | v0 discovery + settlement |
| 1–4 | **v1** schema, 402, channels, pipelines, reference agent |
| 5 | Factory Floor live feed |
| 6 | Federation (crawl foreign manifests) — TBD |
