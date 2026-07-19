# AI Market Protocol v0 (Production Pilot)

This protocol defines how AI systems discover, evaluate, purchase, and consume software products from AI-Factory.

## Goals

- Machine-readable discovery of products and capabilities.
- Verifiable crypto settlement (on-chain) and access activation.
- Vendor-neutral schema so other AI systems can integrate.

## 1) Discovery API

Base path: `/ai-market`.

### `GET /ai-market/products`

Returns product catalog entries with quality and pricing metadata.

Required fields per item:

- `id`
- `name`
- `description`
- `category`
- `tags[]`
- `capabilities[]`
- `pricing`
- `license`
- `quality`
- `crypto_support`

### `GET /ai-market/products/{id}`

Returns full product details, including schema URLs and integration examples.

### `POST /ai-market/products/search`

Semantic request for capability matching.

Input:

```json
{
  "task_description": "Need fraud scoring API for card transactions",
  "constraints": {
    "max_latency_ms": 500,
    "chain": "base",
    "budget_usd_per_1k_calls": 10
  }
}
```

Output:

```json
{
  "matches": [
    {
      "product_id": "prod-abc",
      "score": 0.92,
      "reasoning": ["supports fraud scoring", "latency SLA within constraint"]
    }
  ]
}
```

## 2) Settlement Model (On-Chain)

Production pilot now runs as a strict tuple configured by environment:

- `AIFACTORY_AI_MARKET_CHAIN` (example: `base`)
- `AIFACTORY_AI_MARKET_TOKEN` (example: `USDT`)
- `AIFACTORY_AI_MARKET_CONTRACT` (single contract address)

Settlement confirmations that do not match this tuple are rejected.

### Offer metadata

- `product_id`
- `chain_id`
- `contract_address`
- `payment_token`
- `price_model`: `per_call | subscription | perpetual`
- `price`
- `duration` (for expiring access)

### Canonical contract event

```solidity
event ProductAccessPurchased(
    address indexed buyer,
    bytes32 indexed productId,
    uint256 pricePaid,
    address paymentToken,
    uint256 validUntil
);
```

### Access check

```solidity
function getAccess(address user, bytes32 productId)
  external view returns (bool active, uint256 validUntil);
```

## 3) Access Activation Flow

1. Buyer AI discovers product via Discovery API.
2. Buyer AI executes on-chain purchase transaction.
3. Factory indexer observes `ProductAccessPurchased`.
4. Factory binds `(buyer, product_id)` to active entitlement.
5. Buyer invokes capability endpoint with authenticated proof.

Implemented endpoints:

- `GET /ai-market/pilot/config`
- `POST /ai-market/pilot/settlement/confirm`
- `GET /ai-market/entitlements/{customer_id}`
- `POST /ai-market/capabilities/{product_id}/{capability_id}/invoke` (requires `x-ai-market-license`)

## 4) Capability Invocation Contract

Capability descriptor:

```json
{
  "id": "generate_report",
  "kind": "api",
  "endpoint": "/api/ai-market/prod-abc/capabilities/generate_report",
  "input_schema_url": "/ai-market/schemas/prod-abc/generate_report/input.json",
  "output_schema_url": "/ai-market/schemas/prod-abc/generate_report/output.json",
  "auth": {
    "type": "wallet_signature_or_bearer",
    "requires_entitlement": true
  }
}
```

## 5) Quality Metadata in Discovery

Every product should expose:

- `quality.release_go` (`true|false`)
- `quality.quality_score`
- `quality.slo`
- `quality.last_verified_at`

This prevents downstream AI systems from buying unverified products.

## 6) Reference SDK Responsibilities

SDK should implement:

- catalog listing and search,
- purchase preparation and tx submission hooks,
- entitlement polling,
- capability invocation with schema validation.

The reference Python SDK now includes:

- `get_pilot_config`
- `confirm_settlement`
- `list_entitlements`
- `invoke_capability`

## 8) External Integrations (Proof-of-Workability)

Pilot entitlement activation can fan out to 1-2 external integrations:

- `AIFACTORY_AI_MARKET_WEBHOOK_1`
- `AIFACTORY_AI_MARKET_WEBHOOK_2`

Each successful settlement emits an entitlement event to configured webhooks and persists delivery logs to `/app/data/logs/ai_market_integrations.jsonl`.

## 7) Standardization Strategy

To evolve this into an ecosystem standard:

1. Freeze v0 JSON schemas and publish openly.
2. Provide interoperable reference server + SDK (JS/Python).
3. Add conformance tests.
4. Invite third-party implementations.

