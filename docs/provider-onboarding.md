# Provider onboarding — sell your first capability

Minimal path to list a paid capability on AIMarket Hub (modelmarket.dev) without waiting for full marketplace UI.

## 1. Prepare a manifest

Each capability needs:

- `capability_id` — stable ID, e.g. `mytool.summarize@v1`
- `product_id` — slug, e.g. `prod-mytool`
- `invoke_url` — HTTPS endpoint your server controls
- `price_per_call_usd` — per-invoke list price
- JSON Schemas for `input` / `output`
- Ed25519-signed manifest (see `aimarket-hub/docs/` and `aimarket_hub/publish.py`)

## 2. Publish to the hub

```bash
export AIMARKET_PUBLISH_TOKEN=...   # operator-issued bearer token
curl -X POST "https://modelmarket.dev/ai-market/v2/publish" \
  -H "Authorization: Bearer $AIMARKET_PUBLISH_TOKEN" \
  -H "Content-Type: application/json" \
  -d @manifest.json
```

Self-hosted hub: same route on your `AIMARKET_HUB_URL`.

## 3. Stake (supply security)

Paid invokes may require publisher stake. Configure `publisher_id`, `stake_usd`, and response signing per `aimarket-hub/docs/supply-security.md`.

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
