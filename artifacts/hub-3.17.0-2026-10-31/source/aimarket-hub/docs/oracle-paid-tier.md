# Paid computation through an oracle

Since aimarket-hub 3.16.1, a hub can send an oracle its `ORACLE_PAID_TIER_SECRET`
as `X-AIMarket-Paid-Tier`. This lifts the oracle's free-tier computation ceiling
without trusting the hub's IP address. The existing signed hub admission and the
paid-tier grant serve separate checks in oracle-core.

Configure a different random secret for each oracle using your normal secret
manager. On the oracle, supply it as `ORACLE_PAID_TIER_SECRET`. On the hub, put
that same value into an environment variable dedicated to that oracle, for
example `CHRONOS_PAID_TIER_SECRET`. Do not put real secret values in source files,
manifests, receipts, shell history or these examples.

On the hub, map the oracle's **exact invoke URL** to that environment variable:

```json
{
  "https://chronos.example/ai-market/v2/invoke": {
    "secret_env": "CHRONOS_PAID_TIER_SECRET"
  },
  "https://aestus.example/ai-market/v2/invoke": {
    "secret_env": "AESTUS_PAID_TIER_SECRET"
  }
}
```

Supply this JSON as `AIMARKET_ORACLE_PAID_TIER_CREDENTIALS`. It contains variable
names, not secret values. There is no default mapping or global fallback secret.
The endpoint must match exactly, including port and path. Wildcards, prefixes,
query strings, fragments, user information, encoded paths and dot segments are
not supported. Missing or malformed configuration sends no paid-tier grant.

The hub sends the credential only after reserving a **positive price** on a
channel or credit account, or verifying an x402 payment for that call. Sandbox
trials, free listings, disabled payment rails, and unverified buyer headers do
not qualify. In federation the hub must sell for the peer (`AIMARKET_SELLS_FOR`)
or resell it using an admitted payment; a routing fee alone does not qualify.
The operator must trust the configured oracle endpoint: it receives a bearer
credential, and its owner can use it. Use the usual provider admission controls.

HTTPS is required by default. A private deployment that intentionally uses
plain HTTP must add `"allow_http": true` to that exact destination's entry.
This permits plaintext transmission on that route. Keep HTTPS wherever possible.
The credential does not bypass the hub's existing SSRF destination checks.

For Docker localhost rewrites (`AIMARKET_INVOKE_HOST_GATEWAY`), explicitly map
both the original registered URL and the rewritten destination URL to the same
`secret_env`. The destination entry controls the HTTP exception. Changing the
gateway without adding its exact mapping withholds the grant.

Outbound paid-tier requests disable environment-proxy discovery and automatic
redirects. A redirect never receives the credential. Credentials supplied by
buyers are discarded; the hub supplies only its own configured value.

After configuring both sides, call a priced capability above its declared
`free_tier_max` using a funded channel or account. It should run and charge once.
An unpaid or sandbox call must remain subject to the free ceiling. A wrong secret
must fail the call; channel/credit reservations are released by the existing
failure path. Publishing the package does not configure existing deployments.
