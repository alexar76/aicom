# AI Market Protocol v1

## North Star

Every AI-Factory product is an **MCP-compatible server** that any model (Claude, GPT, Gemini, local) can discover via `.well-known`, read its schema, pay per-call through HTTP 402 with on-chain settlement, and invoke — **without human dashboards.**

This transforms the marketplace from a "catalog" into a **protocol** — at the level of OpenAPI / MCP, but with built-in economics.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   External AI Agent                    │
│  (Cursor, Devin, LangChain, Claude, GPT, CLI)         │
└─────┬────────────────────────────────────────────┬────┘
      │ ① GET /.well-known/ai-market.json           │
      │ ② GET /ai-market/manifest (MCP tools)       │
      │ ③ POST /ai-market/discover (NL → plan)      │
      │ ④ POST /ai-market/channel/open (deposit)    │
      │ ⑤ POST /capabilities/{pid}/{cid}/invoke     │
      │    ← 402 Payment Required                   │
      │    → X-Payment / X-Payment-Channel           │
      │    ← 200 { result, receipt, continuation }   │
      │ ⑥ POST /ai-market/channel/close (settle)    │
      ▼                                              ▼
┌──────────────────────────────────────────────────────┐
│              AI-Factory Protocol Gateway              │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Discovery │ │ Payment  │ │ Execution             │ │
│  │ .well-known│ │ 402 flow │ │ LLM-powered agents    │ │
│  │ manifest  │ │ channels │ │ JSON Schema validated │ │
│  │ MCP tools │ │ receipts │ │ DAG pipelines         │ │
│  └──────────┘ └──────────┘ └───────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Four Pillars

| Pillar | Purpose | Mechanism |
|--------|---------|-----------|
| **Discovery** | How agents find capabilities | `.well-known/ai-market.json` → MCP manifest → NL search |
| **Schema** | How agents agree on input/output shape | JSON Schema on every capability, Ed25519-signed manifest |
| **Payment** | How agents pay without humans | HTTP 402 + on-chain tx OR pre-funded payment channels |
| **Composition** | How agents build pipelines | DAG execution, continuation hints, signed bill of materials |

---

## Pillar 1 — Discovery

### Root manifest

```
GET /.well-known/ai-market.json
```

```json
{
  "name": "Magic AI-Factory AI Market",
  "mcp_endpoint": "https://magic-ai-factory.com/ai-market/mcp",
  "manifest_url": "https://magic-ai-factory.com/ai-market/manifest",
  "products_count": 12,
  "capabilities_count": 47,
  "supported_chains": ["base"],
  "supported_tokens": ["USDT"],
  "protocol_versions": ["v1", "mcp"],
  "signer_public_key": "AbCdEf1234..."
}
```

This is the entry point. Any AI agent starts here. The response is small, cacheable, and contains everything needed to navigate the full catalog.

### Full catalog in MCP tool format

```
GET /ai-market/manifest
```

Returns every capability as an MCP-compatible tool definition with:

```json
{
  "protocol_version": "v1",
  "generated_at": "2026-05-21T12:00:00Z",
  "products_count": 12,
  "capabilities_count": 47,
  "tools": [
    {
      "name": "prod-3c73f3d3.translate.multi@v2",
      "description": "Translate text to multiple locales in one call",
      "input_schema": {
        "type": "object",
        "properties": {
          "text": {"type": "string", "description": "Text to translate"},
          "locales": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["text"]
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "translations": {"type": "object", "additionalProperties": {"type": "string"}}
        }
      },
      "price_per_call_usd": 0.40,
      "p50_latency_ms": 8100,
      "success_rate_30d": 0.97
    }
  ],
  "signature": {
    "algorithm": "ed25519",
    "public_key": "...",
    "value": "..."
  }
}
```

**Key property:** the manifest is Ed25519-signed by the server. Clients verify the signature to ensure the catalog was not tampered with in transit.

### MCP tools list

```
GET /ai-market/mcp
```

A simplified view for MCP-compatible model tool-calling:

```json
{
  "protocol": "mcp",
  "version": "1.0",
  "tools": [
    {"name": "...", "description": "...", "inputSchema": {...}}
  ]
}
```

Any Claude/GPT/Gemini model can read this and make tools available in their function-calling API without glue code.

### Intent-based discovery

```
POST /ai-market/discover
Content-Type: application/json

{
  "query": "translate spec to 5 langs and legal review",
  "budget_usd": 3.00,
  "constraints": {"max_latency_ms": 15000},
  "limit": 8
}
```

Response:

```json
{
  "query": "translate spec to 5 langs and legal review",
  "matches": [
    {
      "product_id": "prod-3c73f3d3",
      "capability_id": "translate.multi@v2",
      "score": 0.92,
      "price_per_call_usd": 0.40,
      "draft_input": {"text": "translate spec to 5 langs and legal review", "locales": ["ru", "en", "de", "fr", "ja"]},
      "why": ["LLM-ranked at position 1"]
    }
  ],
  "plan": [
    {
      "step": 1,
      "product_id": "prod-3c73f3d3",
      "capability_id": "translate.multi@v2",
      "draft_input": {"text": "...", "locales": ["ru", "en", "de", "fr", "ja"]}
    },
    {
      "step": 2,
      "product_id": "prod-3c73f3d3",
      "capability_id": "legal.review_localized@v1",
      "draft_input": {"documents": {"primary": "..."}, "jurisdiction": "US"}
    }
  ],
  "estimated_total_usd": 1.60,
  "protocol_version": "v1"
}
```

**Implementation:** when the LLM router is available, discovery uses semantic ranking (the LLM reads all capability descriptions and ranks them by intent match). When unavailable, falls back to keyword-based scoring. The response includes `draft_input` — a pre-filled input payload conforming to each capability's JSON Schema, so the agent can invoke immediately.

---

## Pillar 2 — Schema

### JSON Schema on every capability

Each capability declares **input_schema** and **output_schema** — full JSON Schema (draft-07). This is compatible with the tool-calling APIs of all major LLMs:

- **Claude:** tool_use blocks with `input_schema`
- **GPT:** function calling with `parameters`
- **Gemini:** function declarations with `parameters`

### Ed25519 signing

The manifest includes a cryptographic signature over canonical fields (`capabilities_count`, `generated_at`, `protocol_version`). The server's public key is available in:

1. The `.well-known/ai-market.json` response (`signer_public_key`)
2. The signature block itself (`public_key`)

Clients verify: `manifest.signature.value` over `{capabilities_count, generated_at, protocol_version}` using `manifest.signature.public_key`.

### Versioning

Capability IDs use the format `name@version`: `translate.multi@v2`, `legal.review@v1`. Old versions remain available for backward compatibility. The catalog lists all versions simultaneously.

---

## Pillar 3 — Payment

### HTTP 402 flow (single call)

This implements the **HTTP 402 Payment Required** pattern (aligned with Coinbase x402 / EIP-3009):

```
Step 1 — Invoke without payment:
  POST /capabilities/prod-xxx/translate.multi@v2/invoke
  {"input": {"text": "hello"}}

  → 402 Payment Required
  X-Payment-Required: {"amount":"0.40","token":"USDT","chain":"base",
                        "recipient":"0x...","nonce":"pay_...","expires_at":"...",
                        "receipt_url":"/ai-market/receipt/pay_..."}

Step 2 — Client signs and sends on-chain transaction, then retries:
  POST /capabilities/prod-xxx/translate.multi@v2/invoke
  X-Payment: {"tx_hash":"0x...","chain":"base"}
  {"input": {"text": "hello"}}

  → 200 OK
  {
    "success": true,
    "result": {"translations": {"ru": "...", "en": "..."}},
    "receipt": {"nonce": "rcpt_...", "signature": "..."},
    "price_usd": 0.40,
    "latency_ms": 8100,
    "continuation": {"suggested_next": [...]}
  }
```

### Payment channels (pre-funded, off-chain)

For multi-step workflows, opening a channel avoids per-call on-chain transactions:

```
1. Open channel:
   POST /ai-market/channel/open
   {"deposit_usd": 3.00, "tx_hash": "0x..."}
   → {"channel": {"channel_id": "ch_a8f3...", "balance_usd": 3.00, ...}}

2. Invoke with channel (off-chain debit, no on-chain tx):
   POST /capabilities/.../invoke
   X-Payment-Channel: ch_a8f3...
   → 200 (balance deducted from channel ledger)

3. Close channel (single on-chain settlement):
   POST /ai-market/channel/close
   {"channel_id": "ch_a8f3...", "settle_tx_hash": "0x..."}
   → {"settlement": {"used_usd": 1.60, "refund_usd": 1.40, ...}}
```

**Channel properties:**
- Pre-funded: client deposits $X → gets `channel_id`
- Off-chain debit: each invoke deducts from channel balance atomically
- Single settlement: one on-chain tx at close for the total used
- Refund on failure: if `invoke` returns `success: false` with a typed error, channel balance is refunded atomically

### Pricing oracle

```
GET  /ai-market/pricing/{pid}/{cid}?input_size=4200
POST /ai-market/pricing/{pid}/{cid}  {"input": {...}}
```

Returns the exact price for a specific input before invocation. Useful when cost depends on input size or complexity.

### Signed receipts

```
GET /ai-market/receipt/{nonce}
```

Every successful invocation produces a signed receipt. Receipts are Ed25519-signed by the server and can be verified independently.

---

## Pillar 4 — Composition

### Continuation hints

Every invoke response includes:

```json
{
  "continuation": {
    "suggested_next": [
      {
        "capability_id": "legal.review_localized@v1",
        "product_id": "prod-xxx",
        "why": "commonly follows translate.multi@v2",
        "est_price_usd": 1.20
      }
    ]
  }
}
```

This lets the calling model plan multi-step workflows: "after translate, I should call legal review."

### DAG pipelines

```
POST /ai-market/pipelines
{
  "channel_id": "ch_a8f3...",
  "nodes": [
    {
      "id": "a",
      "product_id": "prod-xxx",
      "capability_id": "translate.multi@v2",
      "input": {"text": "spec", "locales": ["ru", "en"]},
      "depends_on": []
    },
    {
      "id": "b",
      "product_id": "prod-xxx",
      "capability_id": "legal.review_localized@v1",
      "input_from": "a",
      "depends_on": ["a"]
    }
  ]
}
```

The server:
1. Resolves topological order from `depends_on`
2. Executes each step sequentially, feeding outputs as inputs
3. Settles all charges against a single channel
4. Returns `trace_id` + signed `bill_of_materials`

Response:

```json
{
  "trace_id": "tr_abc123...",
  "bill_of_materials": {
    "trace_id": "tr_abc123...",
    "steps": [
      {"capability_id": "translate.multi@v2", "price_usd": 0.40, "success": true},
      {"capability_id": "legal.review_localized@v1", "price_usd": 1.20, "success": true}
    ],
    "total_usd": 1.60,
    "signature": "..."
  },
  "final_result": {...},
  "protocol_version": "v1"
}
```

The **bill of materials** is an enterprise compliance feature: a signed receipt proving exactly what was called, who got paid, and how much — satisfying auditors and regulators.

---

## Full Autonomous Cycle

An external agent (Cursor, Devin, CLI, LangChain) receives the task "translate spec to 5 languages + legal review":

```
① GET  /.well-known/ai-market.json
② GET  /ai-market/manifest  → 47 capabilities in tool format
③ Agent → LLM: "here are 47 tools, solve with budget $3"
④ LLM plans: [translate.multi(5lang) → legal.review_localized]
⑤ POST /ai-market/pricing/translate@v2?text_len=4200 → {price: $0.40}
⑥ POST /ai-market/channel/open {deposit: 3.0}
   → signs tx on Base → channel_id
⑦ POST /capabilities/translate@v2/invoke
   X-Payment-Channel: ch_...
   → 200 {result: {ru,en,de,fr,ja}, receipt, continuation}
⑧ POST /capabilities/legal.review_localized/invoke
   → 200 {result: {...}, receipt}
⑨ POST /ai-market/channel/close → settle ($1.60 used, $1.40 refund)
⑩ Returns result + signed bill_of_materials.json
```

No human. No dashboard. Just HTTP + on-chain.

---

## API Reference

### Endpoints

| Method | Path | Description | Complexity |
|--------|------|-------------|------------|
| GET | `/.well-known/ai-market.json` | Root crawl manifest | XS |
| GET | `/ai-market/manifest` | Full catalog in MCP tool format (signed) | S |
| GET | `/ai-market/mcp` | MCP `tools` list | XS |
| POST | `/ai-market/discover` | NL intent → ranked capabilities + plan | M |
| GET | `/ai-market/pricing/{pid}/{cid}` | Price quote by input size | S |
| POST | `/ai-market/pricing/{pid}/{cid}` | Price quote by input payload | S |
| POST | `/ai-market/channel/open` | Open pre-funded payment channel | M |
| POST | `/ai-market/channel/close` | Close channel, settle, refund | M |
| POST | `/ai-market/pipelines` | DAG pipeline execution | L |
| GET | `/ai-market/receipt/{nonce}` | Signed payment receipt | XS |
| GET | `/ai-market/stats` | Live invocation feed (Factory Floor) | S |
| POST | `/capabilities/{pid}/{cid}/invoke` | Invoke capability (402 if unpaid) | S |
| POST | `/ai-market/capabilities/{pid}/{cid}/invoke` | Same, under `/ai-market/` prefix | S |

### Payment headers

| Header | Value | Use |
|--------|-------|-----|
| `X-Payment` | `{"tx_hash":"0x...","chain":"base"}` | Single on-chain payment |
| `X-Payment-Channel` | `ch_a8f3...` | Pre-funded channel debit |
| `x-ai-market-license` | `<license_key>` | Legacy v0 license key |

### HTTP status codes

| Status | Meaning |
|--------|---------|
| 200 | Invocation successful |
| 400 | Bad request (invalid params, unverified payment) |
| 402 | Payment required (see `X-Payment-Required` header) |
| 404 | Capability not found |

---

## Reference Consumer

### CLI agent

```bash
pip install ai-market-agent

ai-market run "translate spec to 5 langs + legal review" --budget 3.00
```

```
[discover] 47 capabilities across 12 products
[plan]     translate.multi@v2 → legal.review_localized@v1  (est $1.60)
[channel]  opened ch_a8f3 with $3.00 deposit
[call]     translate.multi@v2 ........... $0.40 ✓ 8.1s
[call]     legal.review_localized@v1 .... $1.20 ✓ 11.4s
[settle]   used $1.60 of $3.00, refund $1.40
[saved]    bill_of_materials.json (signed)
```

### Python SDK

```python
from cli.ai_market_agent import AIMarketAgent

agent = AIMarketAgent(base_url="https://magic-ai-factory.com", budget=3.00)
result = agent.run("translate spec to 5 langs + legal review")
# result["settlement"]["used_usd"] → 1.60
```

---

## Product Capability Declaration

Products in `pipeline.json` can declare capabilities explicitly:

```json
{
  "products": {
    "prod-3c73f3d3": {
      "state": "COMPLETED",
      "name": "Legal Translator",
      "capabilities": [
        {
          "id": "translate.multi@v2",
          "name": "translate.multi",
          "version": "v2",
          "description": "Translate text to multiple locales in one call",
          "input_schema": {
            "type": "object",
            "properties": {
              "text": {"type": "string", "description": "Text to translate"},
              "locales": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["text"]
          },
          "output_schema": {
            "type": "object",
            "properties": {
              "translations": {"type": "object", "additionalProperties": {"type": "string"}}
            }
          },
          "price_per_call_usd": 0.40,
          "p50_latency_ms": 8100,
          "agent": "developer",
          "prompt_template": "Translate this text to {locales}:\n\n{text}",
          "suggested_next": ["prod-xxx/legal.review_localized@v1"]
        }
      ]
    }
  }
}
```

When a product does **not** declare capabilities, the catalog synthesizes a reasonable set from the product name and description (backward-compatible fallback).

---

## Security Model

1. **Manifest integrity:** Ed25519 signatures prevent catalog tampering
2. **Receipt non-repudiation:** Every receipt is signed, verifiable independently
3. **Payment verification:** On-chain tx verification (EVM + Solana) before execution
4. **Channel isolation:** Payment channels are bound to a single session, auto-expire after 24h
5. **Refund on failure:** Typed execution errors trigger atomic channel refund
6. **No custody:** The protocol never holds funds — channels are on-chain constructs

### Threat model

| Threat | Mitigation |
|--------|------------|
| Manifest tampering in transit | Ed25519 signature verified by client |
| Fake payment claim | On-chain tx verification against RPC node |
| Double-spend of channel | Ledger is single-writer (server), sequential |
| Replay of old invocation | Nonce in payment_required, channel ledger |
| Capability description mismatch | Schema is in manifest, signed; actual execution validates input |

---

## Configuration

| Env variable | Default | Description |
|-------------|---------|-------------|
| `AIFACTORY_AI_MARKET_CHAIN` | `base` | Chain for on-chain settlement |
| `AIFACTORY_AI_MARKET_TOKEN` | `USDT` | Settlement token |
| `AIFACTORY_AI_MARKET_CONTRACT` | — | Settlement contract address |
| `AIFACTORY_AI_MARKET_DEMO_PAYMENT` | `1` | Accept `demo-*` tx hashes (dev) |
| `AIFACTORY_AI_MARKET_ENTITLEMENT_DAYS` | `30` | License TTL |
| `AIFACTORY_PUBLIC_URL` | — | Canonical URL in manifests |
| `AIFACTORY_PAYMENT_TESTNET` | `1` | Use testnet RPC endpoints |
| `AIFACTORY_PAYMENT_VERIFY_STUB` | `1` | Stub verification in dev |

---

## Roadmap

| Phase | Status | Content |
|-------|--------|---------|
| 0 — v0 pilot | Done | Discovery list, settlement, license invoke |
| 1 — Schema + 402 | Done | Manifest in MCP format, JSON Schema, 402 flow, signed receipts |
| 2 — Channels | Done | Payment channels (off-chain ledger, on-chain settle) |
| 3 — Composition | Done | Pipelines endpoint, continuation hints, BOM |
| 4 — Reference agent | Done | `cli/ai_market_agent.py`, PyPI packaging |
| 5 — Live Factory Floor | Done | `/ai-market/stats` feed |
| 6 — Federation | TBD | Crawl external `.well-known/ai-market.json` → unified catalog |

---

## Why This Matters

1. **Open standard, not lock-in.** All stakeholders (Anthropic, OpenAI, Google) are building tool-discovery infrastructure. HTTP 402 payments are entering standards track via Coinbase x402. AI-Factory is the first working reference implementation at the intersection of these two tracks.

2. **AI agents are the real target customer.** Today: LangChain / AutoGPT / Cursor agents. Tomorrow: Claude / Gemini directly through MCP registry. Whoever builds payable tools first captures default traffic.

3. **On-chain settlement gives atomicity** between business logic and payment — impossible with Stripe (async webhooks). AI agents need deterministic "received → paid."

4. **Bill of materials** is an enterprise compliance feature: "prove how you arrived at this answer, and who got paid for what." Auditors and regulators will pay separately for this.
