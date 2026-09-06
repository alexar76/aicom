# Provider onboarding — sell your first capability

Minimal path to list a paid capability on AIMarket Hub (modelmarket.dev) without waiting for full marketplace UI.

**Not open signup.** Anyone can **consume** listed capabilities (ARGUS / `aimarket-mcp` / SDKs). **Selling** into the public catalogue needs operator publish credentials, stake, a valid signed manifest, and — when enabled — THEMIS. Full current-state table + numbered GitHub→listed path: [`docs/ecosystem/supply-chain-admission.md`](ecosystem/supply-chain-admission.md).

## 1. Prepare a manifest

Each capability needs:

- `capability_id` — stable ID, e.g. `mytool.summarize@v1`
- `product_id` — slug, e.g. `prod-mytool`
- `publisher_id` — stable publisher identity bound to your stake / token
- `provider_pubkey` — Ed25519 public key for invoke response signatures
- `invoke_url` — HTTPS endpoint your server controls
- `price_per_call_usd` — per-invoke list price
- JSON Schemas for `input` / `output`
- Ed25519-signed manifest (see `aimarket-hub/docs/` and `aimarket_hub/publish.py`)

## 2. Stake (supply security)

Paid invokes require publisher stake in prod. Configure `publisher_id`, `stake_usd`, and response signing (`X-Provider-Signature`) per `aimarket-hub/docs/supply-security.md`. Prod default minimum ≈ **$25** USD unless supply-security is relaxed.

## 3. Publish to the hub

```bash
export AIMARKET_PUBLISH_TOKEN=...   # operator-issued bearer token — not self-service
curl -X POST "https://modelmarket.dev/ai-market/v2/publish" \
  -H "Authorization: Bearer $AIMARKET_PUBLISH_TOKEN" \
  -H "Content-Type: application/json" \
  -d @manifest.json
```

Self-hosted hub: same route on your `AIMARKET_HUB_URL`.

## 3b. Publish admission (THEMIS)

When the Hub runs with `AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE=advisory|enforce`, publish
also goes through the **THEMIS** before the capability enters the
public catalogue (`approve` / `review` / `reject`). This is **not** checked on every
invoke — runtime stays WARDEN + Hub trust floors.

Full role split (Auditor · WARDEN · Metis · MOMUS · Alien Monitor · Hub) and mermaid
diagrams: [`docs/ecosystem/supply-chain-admission.md`](ecosystem/supply-chain-admission.md)
([RU](ecosystem/supply-chain-admission-ru.md) ·
[ES](ecosystem/supply-chain-admission-es.md) ·
[FR](ecosystem/supply-chain-admission-fr.md) ·
[ZH](ecosystem/supply-chain-admission-zh.md)).

Reference agent + tutorial:
[alexar76/themis](https://github.com/alexar76/themis) ·
[create-aimarket-agent tutorial](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.en.md).

## 4. Verify discovery

```bash
curl -s "https://modelmarket.dev/ai-market/v2/search" \
  -H "Content-Type: application/json" \
  -d '{"intent":"mytool summarize","limit":5}' | jq .
```

## 5. Test invoke (sandbox)

Use `X-AIMarket-Sandbox-Visitor` for trial invokes without a payment channel (hub rate-limited).

## 6. Oracle-family shortcut

Oracle products (Platon, Sortes, …) ship via the [oracles](https://github.com/alexar76/oracles) repo and the federated family manifest. After deploy, run on the hub host:

```bash
PYTHONPATH=.:aimarket-hub python3 scripts/sync_oracle_family_to_hub.py
```

## Landing wedge (AI-Factory operators)

For **marketing_landing** products only, enable auto-publish after DevOps:

```yaml
# config/fragments/10-general.yaml
general:
  auto_publish_enabled: true
  auto_publish_landing_only: true
  auto_publish_provider: vercel   # or netlify / cloudflare_pages
```

Set `VERCEL_TOKEN` (or Netlify/Cloudflare equivalent) in the environment. Full-stack apps still require manual deploy review.

## Support

- Protocol: [aimarket-protocol](https://github.com/alexar76/aimarket-protocol)
- Hub source: [aimarket-hub](https://github.com/alexar76/aimarket-hub)
- Launch checklist: [docs/launch-kit.md](launch-kit.md)
