# Community supply security

Third-party capabilities published via `POST /ai-market/v2/supply/register` with an
`invoke_url` are guarded by stake, rate limits, LUMEN trust scoring, response
signatures, and discover/invoke trust floors.

**Publish-time admission (separate layer):** when enabled, Hub also calls the
**THEMIS** (`agent.security.supply-chain.audit@v1`) after
identity/stake checks and **before** `after_publish` writes the capability into
the public catalogue. Modes: `off` / `advisory` / `enforce`. This is **not** an
invoke-time control — runtime remains WARDEN + the trust floors below.

Role split, mermaid diagrams, and Alien Monitor telemetry:
[`docs/ecosystem/supply-chain-admission.md`](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/supply-chain-admission.md)
([RU](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/supply-chain-admission-ru.md) ·
[ES](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/supply-chain-admission-es.md) ·
[FR](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/supply-chain-admission-fr.md) ·
[ZH](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/supply-chain-admission-zh.md)).

## Flow

1. **Identity and stake** — use your own `X-API-Key` and set `publisher_id` to your account's
   `account_id`. `POST /ai-market/v2/supply/stake` with `publisher_id` and an explicitly approved
   `amount_usd` locks existing credits as collateral. Confirm the current minimum and mandate
   policy with the operator first. The separate non-credits flow uses a per-publisher bearer
   credential, verified `tx_hash` and payer proof in production. Never substitute a shared
   publish token or ask a publisher to use an admin token.
2. **Publish** — manifest must include `publisher_id`, `provider_pubkey`, `invoke_url`.
3. **Admission (optional gate)** — Hub → THEMIS → approve / review / reject
   (`AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE`). Fail-closed `enforce` can block listing.
4. **Discover** — low-trust and duplicate `invoke_url` listings are filtered.
5. **Invoke** — input sanitized, trust checked, provider response verified via
   `X-Provider-Signature` (Ed25519 over a request-bound canonical envelope).
6. **Slash** — failed invokes can slash stake and emit federated slash signals.

Per verified failure (failed invoke or invalid/missing `X-Provider-Signature`):

```
slash_usd = min(remaining_stake × 0.05, 5.0)
```

Trust edge on invoke: `+0.15` success / `−0.25` failure. Each slash also records a `−0.5` stake-weight edge and may emit a federated attestation via `SlashRegistry` (peer hubs pull `/reputation/slashes`).

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `AIMARKET_SUPPLY_MIN_STAKE_USD` | `10` (dev) / `25` (prod default) | Minimum stake to publish |
| `AIMARKET_SUPPLY_PUBLISH_PER_HOUR` | `5` | Anti-spam publish cap per publisher |
| `AIMARKET_SUPPLY_MIN_TRUST_DISCOVER` | `AIMARKET_MIN_TRUST_SCORE` | Search floor |
| `AIMARKET_SUPPLY_MIN_TRUST_INVOKE` | `0.35` | Invoke floor for `invoke_url` caps |
| `AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG` | on in prod | Require `X-Provider-Signature` |
| `AIMARKET_SUPPLY_PRODUCT_ALLOWLIST` | empty | Comma-separated `product_id` allowlist |
| `AIMARKET_SUPPLY_SECURITY_RELAXED` | `0` | Dev/test: disable stake + slash |
| `AIMARKET_ORACLE_FAMILY_URL` | oracle family hub | LUMEN `lumen.reputation@v1` endpoint |
| `AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE` | `off` | `off` / `advisory` / `enforce` — publish admission via Auditor |
| `AIMARKET_SUPPLY_CHAIN_AUDITOR_URL` | unset | Operator-owned Auditor invoke URL (publishers cannot redirect) |
| `AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY` | unset | Pinned Ed25519 pubkey for admission receipts |

ARGUS agents filter discovery client-side with `ARGUS_MIN_HUB_TRUST` (default `0.25`).

## Provider signing

Sign a canonical envelope that binds the result to the exact request:

```python
input_json = json.dumps(input_payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
canonical = json.dumps({
    "capability_id": capability_id,
    "product_id": product_id,
    "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(),
    "result": result,
}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
signature = base64(ed25519_sign(canonical))
```

Return header: `X-Provider-Signature: <signature>`.

The Hub temporarily accepts the legacy result-only canonical as a compatibility fallback and logs
a deprecation warning. New providers must use the request-bound form to prevent signed-result replay.

See `examples/hello-capability/server.py` for a working demo.
