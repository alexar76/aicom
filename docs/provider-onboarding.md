# Provider onboarding — sell your first capability

Minimal path to list a paid capability on AIMarket Hub (modelmarket.dev) without waiting for full marketplace UI.

**Publish with your own account.** Start at [the provider account page](https://modelmarket.dev/start?role=provider), create an API key and keep it in `AIMARKET_API_KEY` in your local terminal. No operator publish token is needed for this path. Admission and collateral requirements still apply; read the current policy below rather than assuming a fixed dollar amount. Alternatively, [run your own Hub](join-the-federation.md) and join as a federation peer. The [publication guide](https://play.modelmarket.dev/publish) follows the same account → collateral → register → discovery path in five languages.

## 1. Prepare a manifest

Before production admission, test your own endpoint through the Playground's
`/connect` route or the local `aimarket-provider-check` CLI. The provider invoke
profile checks one real response, its schema and request-bound Ed25519 signature
without a Hub token, stake or payment. See
[provider check setup and limits](https://play.modelmarket.dev/connect/guide).
This does not register the provider or certify the complete protocol.

Each capability needs:

- `capability_id` — stable ID, e.g. `mytool.summarize@v1`
- `product_id` — slug, e.g. `prod-mytool`
- `publisher_id` — stable publisher identity bound to your stake / token
- `provider_pubkey` — Ed25519 public key for invoke response signatures
- `invoke_url` — HTTPS endpoint your server controls
- `price_per_call_usd` — per-invoke list price
- JSON Schemas for `input` / `output`
- Ed25519-signed invoke responses matching the declared public key

Read `account_id` and use it as `publisher_id` in `capability.json` (the starter's filename):

```bash
curl --fail-with-body https://modelmarket.dev/ai-market/v2/account \
  -H "X-API-Key: ${AIMARKET_API_KEY:?Set your own API key locally}"
```

## 2. Stake (supply security)

Read the actual requirements and your current stake before funding:

```bash
curl --fail-with-body https://modelmarket.dev/ai-market/v2/supply/policy \
  -H "X-API-Key: ${AIMARKET_API_KEY:?Set your own API key locally}"
```

Check `min_stake_usd`, `stake_usd`, `additional_stake_usd`, `balance_usd`,
`product_allowlist`, and `admission_mode`. If `requires_mandate` is true, the API key
cannot post collateral: resolve the account policy before funding. If needed, top up
the difference between `additional_stake_usd` and your available `balance_usd` on the
[provider account page](https://modelmarket.dev/start?role=provider#topup), then return here.
**A top-up is spendable credit, not posted collateral.**

If `additional_stake_usd` is zero, skip the following command. Otherwise set
`AIMARKET_STAKE_USD` to that missing amount and execute once:

```bash
curl --fail-with-body https://modelmarket.dev/ai-market/v2/supply/stake \
  -H "X-API-Key: ${AIMARKET_API_KEY:?Set your own API key locally}" \
  -H "Content-Type: application/json" \
  -d "{\"amount_usd\":\"${AIMARKET_STAKE_USD:?Set additional_stake_usd from policy}\"}"
```

This locks credit as slashable collateral. Re-read the policy and account afterwards;
`balance_usd` is available credit and `collateral_usd` is locked. Collateral return
requires the operator. The stake command is **not idempotent**: after a timeout, inspect
the account, policy and `GET /ai-market/v2/account/ledger` with the same key before retrying.

## 3. Publish to the hub

```bash
curl --fail-with-body "https://modelmarket.dev/ai-market/v2/supply/register" \
  -H "X-API-Key: ${AIMARKET_API_KEY:?Set your own API key locally}" \
  -H "Content-Type: application/json" \
  --data-binary @capability.json
```

Self-hosted hub: same route on your `AIMARKET_HUB_URL`.

Errors: **400** includes insufficient stake or an invalid manifest; read `detail`.
**401/403** means credentials, publisher identity, account policy or admission need
attention. **402** from `/supply/stake` means insufficient available credit.
**503** means admission is unavailable. Do not retry payments to fix a policy rejection.

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
curl --fail-with-body --get "https://modelmarket.dev/ai-market/v2/search" \
  --data-urlencode "intent=YOUR_CAPABILITY_ID" \
  --data-urlencode "limit=5"
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
