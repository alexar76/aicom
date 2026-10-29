# RouteVerdict — trust & liveness checks for x402 endpoints

**Before an agent pays an unfamiliar x402 endpoint, it pays $0.05 to ask
RouteVerdict first.** One `POST /v1/check` with a resource URL returns a
TRUSTED / CAUTION / AVOID verdict with a 0-100 trust score — the trust
layer for x402 itself, sold to the buyers who demonstrably pay repeatedly
in this economy: monitors, inspectors, rating services, and agents about
to route real money through a route they have never used.

Sibling service: [Token Verdict](https://github.com/QuincyGB/token-verdict)
(risk verdicts for token contracts). Same stack, same patterns, same
payout wallet.

## What a check does (observation only — it NEVER pays the target)

1. **Liveness** — the target is requested unauthenticated (GET, then
   POST `{}`). Status, latency, and whether its 402 parses as valid x402
   are recorded. No payment header is ever attached, so the target can
   never charge the checker.
2. **Terms** — from the challenge's accepts: price, network, asset,
   payTo, scheme, x402 version.
3. **Schema quality** — is a Bazaar discovery extension present? Does its
   output schema type real fields, or is it hollow (`{"type", "example"}`
   only — the shape 87.8% of listings ship)? Scored 0–100 with named
   deductions, including the >500-char description trap that makes the
   CDP facilitator reject payments.
4. **Catalog presence** — is the resource listed in the **CDP Bazaar**
   (public merchant lookup by payTo) and/or the **PayAI index**
   (listing-status)? Payer counts / last-activity are reported when the
   APIs return them. A failed lookup reports `unknown` — never a
   fabricated "not listed".
5. **Diff** — every check is persisted (sqlite, keyed by URL) and the
   response states what changed since the previous check: price, payTo,
   schema score, listing presence, liveness. A first check returns
   "no prior check on record". A payTo change is a named 15-point
   deduction: the money going somewhere new is exactly what a buyer
   needs to know.
6. **Verdict** — TRUSTED (≥75) / CAUTION (≥45) / AVOID (<45) with every
   deduction itemized in `reasons`.

## Endpoints

| Route | Price | Purpose |
|---|---|---|
| `POST /v1/check` | $0.05 USDC | Trust & liveness check for one x402 resource URL (x402 v2, Base) |
| `GET /quote` | free | Price, asset, network, pay-to wallet |
| `GET /.well-known/x402` | free | Machine-readable manifest (full input/output schemas) |
| `GET /skill.md` | free | Documentation written for agents |
| `GET /llms.txt` | free | Compact agent index |
| `GET /health` | free | Liveness |

Request body: `{"resource_url": "https://service.example.com/v1/endpoint"}`

## How cataloging works (why the facilitator env matters)

There is no submission form for the x402 indexes. **A listing is a
side-effect of a settled payment**: each facilitator catalogs only
settlements through *its own* facilitator, in its own index. So:

- `X402_FACILITATOR_URL` unset → keyless ultravioletadao facilitator:
  settles on Base, feeds no major index.
- `X402_FACILITATOR_URL=https://facilitator.payai.network` → settlements
  catalog RouteVerdict in the **PayAI index**. No API key needed.
- `X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402`
  plus `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` → settlements catalog
  RouteVerdict in the **CDP Bazaar / Agentic.Market**.

One deployment settles through one facilitator at a time; appearing in
both indexes means at least one settled call under each configuration,
and at least one settled call every ~30 days per index or the listing
ages out. The discovery metadata is built to catalog from birth: full
typed output schema (not the hollow norm), descriptions under 500 chars,
`/openapi.json`, `/.well-known/x402`, `/llms.txt` — all pinned by tests.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
.venv/bin/python -m pytest tests/ -q
```

Key env (see `.env.example`): `X402_PAY_TO` (payout wallet),
`X402_PRICE_USDC` (default `$0.05`), `X402_FACILITATOR_URL`,
`CDP_API_KEY_ID` / `CDP_API_KEY_SECRET`, `ROUTE_VERDICT_DB` (sqlite path
— put it on a persistent volume in production or diffs reset per deploy),
`ROUTE_VERDICT_FETCH_TIMEOUT_S`.

Production runs on Railway from the included `Dockerfile`
(healthcheck: `/health`).

## Honest limits

RouteVerdict reads what an endpoint publishes and what the public
catalogs hold. It does not settle a test payment to the target (that
would cost the target's price per check and entangle the checker in the
target's settlement path), does not grade the paid payload's quality,
and cannot see inside the target's wallet — the diff flags payTo
changes, it does not explain them.
