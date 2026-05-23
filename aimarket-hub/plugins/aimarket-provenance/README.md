# aimarket-provenance

**Cryptographic provenance receipts for every AI output — Ed25519 + W3C Verifiable Credentials.**

Infrastructure-layer plugin for [AIMarket Hub](../README.md). Auto-attaches a tamper-evident receipt to every successful `/invoke`, and exposes public verify endpoints for auditors and end users.

## Value in plain words

Every AI answer gets a cryptographic receipt — who, when, what model — verifiable later for compliance, disputes, and user trust. Like a fiscal receipt for AI output.

**Простыми словами:** Каждый ответ AI получает криптографический чек — кто, когда, какая модель — можно проверить позже для compliance, споров и доверия. Как фискальный чек для результата AI.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure signing key, verify receipts |
| [User cases](docs/user-cases.md) | Compliance, consumer apps, multi-step chains |
| [SDK integration](docs/sdk-integration.md) | HTTP API, Python, invoke hook behavior |

---

## Why this exists

Regulated and high-trust AI workflows need proof of **what model ran, on what input hash, at what time, signed by whom** — without storing full prompts on a public ledger. Provenance is the **infrastructure abstract layer** between raw invoke results and external audit systems.

## Features

- **Auto-receipt on invoke** — `provenance_receipt` field on every invoke response
- **W3C Verifiable Credential** format with Ed25519 hub signature
- **Provenance chains** — `parent_receipts` link multi-step pipelines
- **TEE + ZK metadata** — optional attestation fields embedded in receipt
- **Public verify** — anyone can verify without API token
- **Protected attest** — optional Bearer token for manual receipt creation

## Installation

```bash
cd aimarket-hub
pip install -e plugins/aimarket-provenance
aimarket serve
```

Verify:

```bash
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="provenance")'
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.provenance'
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/ai-market/v2/p/provenance/attest` | Bearer (optional) | Create receipt manually |
| `GET` | `/ai-market/v2/p/provenance/receipt/{id}` | Public | Fetch stored receipt |
| `GET` | `/ai-market/v2/p/provenance/verify/{id}` | Public | Full cryptographic verification |

## Auto-receipt on invoke

```bash
curl -X POST http://localhost:9080/ai-market/v2/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "prod-demo",
    "capability_id": "translate@v1",
    "source_hub": "local",
    "input": {"text": "Hello"}
  }' | jq '.provenance_receipt'
```

```json
{
  "receipt_id": "urn:aimarket:receipt:abc123...",
  "verify_url": "https://verify.aimarket.org/r/abc123"
}
```

## Manual attest

```bash
curl -X POST http://localhost:9080/ai-market/v2/p/provenance/attest \
  -H "Authorization: Bearer $AIMARKET_PROVENANCE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "legal.review@v1@prod-legal",
    "provider_hub": "https://provider.example.com",
    "input": {"documents": {"hash": "sha256:..."}},
    "output": {"risk": "low", "issues": 0},
    "parent_receipts": ["urn:aimarket:receipt:parent-id"],
    "latency_ms": 4200,
    "price_usd": 0.15
  }'
```

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `AIMARKET_PROVENANCE_KEY_PATH` | `data/provenance_signing_key` | Ed25519 signing key (created on first run) |
| `AIMARKET_PROVENANCE_API_TOKEN` | *(empty)* | Bearer token for `/attest`; empty = open |
| `AIMARKET_VERIFY_DOMAIN` | `https://verify.aimarket.org` | Base URL in `verify_url` links |
| `DATABASE_URL` | SQLite | Optional PostgreSQL for receipt storage |

**Back up `provenance_signing_key`** — losing it invalidates verification of historical receipts.

## Storage

Receipts persist in `provenance.db` (SQLite) or PostgreSQL when `DATABASE_URL` is set. Migration `005_provenance_receipts` in hub schema.

## Combine with

| Plugin | Pattern |
|--------|---------|
| `aimarket-tee` | Embed TEE attestation in receipt |
| `aimarket-zk` | Attach ZK proof references without revealing payloads |
| `aimarket-reputation` | Include `reputation_score` field on attest |
| `aimarket-channels` | Receipt lists `price_usd` debited from channel |

## License

Apache-2.0 · Part of AIMarket Hub
