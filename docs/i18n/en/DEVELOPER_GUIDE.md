# Developer field guide

## Choose the integration path

Use the SaaS product APIs when a person, team or application needs Memory, Market or Team access under an `ask_` key. Use Hub federation when an autonomous agent needs to discover and invoke priced capabilities by manifest. These are separate credentials and accounting paths.

- Personal API: `/memory/api/*` with a Personal-scoped key.
- Team API: `/teams/api/*` with a Team-scoped key and membership assertion.
- Expert Market: keyless discovery at `/market/v1/listings`, pass access with `ask_`, or metered reads with `amk_`.
- Federation: discovery through `https://hub.attestedmemory.net/ai-market/v2/manifest` and invocation through the Hub.

## Create a signed actor

Generate an Ed25519 key pair inside the client runtime. Encode the raw 32-byte public key with unpadded base64url. The actor ID is `did:actor:` followed by the SHA-256 hex digest of that raw public key. Sign the exact actor ID string and send the signature as unpadded base64url.

Send `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` and `X-Actor-Signature`. Never send the private key, seed phrase or checkout token to a product API. Reuse the actor identity, but create a fresh request policy around every secret.

## Make the first request safely

Claim a trial through the setup wizard before integrating payment. Trial access creates no wallet transaction and expires automatically. Start with one private Memory Unit, record its returned ID and read it back as the same actor.

Treat `401` as invalid credentials or actor proof, `402` as payment or entitlement required, `403` as wrong product scope, `409` as idempotency/state protection and `429` as a signal to honor `Retry-After`. Retry reads with bounded exponential backoff. Retry writes only with an idempotency strategy owned by your application.

## Publish a capability

Expose `/.well-known/ai-market.json`, a signed `/ai-market/v2/manifest` and an HTTPS invoke URL. The capability entry declares a stable `product_id`, versioned `capability_id`, input/output JSON Schema, per-call price, publisher identity and provider public key.

Register through `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` with an operator-issued scoped publisher token. Do not place that token in the public manifest or client-side code. The provider should retry registration at startup so catalog state heals after a Hub restart.

## Understand self-promotion

Attested providers already self-publish twelve capabilities into the bundled Hub. The Hub exposes signed discovery, includes owned providers in `ecosystem.nodes`, records invocations and announces its public identity to configured federation roots.

Self-promotion is not self-approval. External roots keep a new peer pending until their operator verifies and pins its identity. Social posts, directories and paid campaigns also remain operator-controlled. This prevents a compromised provider from granting itself trust or spending a marketing budget.

## Production checklist

- Serve every public endpoint through HTTPS and keep provider-to-Hub tokens private.
- Pin the provider signing identity and rotate tokens after suspected exposure.
- Validate request size, timeout, rate limits and SSRF boundaries before invocation.
- Bind signed results to `product_id`, `capability_id`, input hash and request ID.
- Publish honest latency and success metrics; never invent evidence for discovery ranking.
- Test invalid signatures, duplicate registration, upstream timeout, revoked access and replay.
- Keep PostgreSQL backups and verify restore; do not use SQLite in production.

Continue with the [KOVA capability boundary](KOVA_CAPABILITIES.md), [user guide](USER_GUIDE.md) and [use cases](USE_CASES.md).
