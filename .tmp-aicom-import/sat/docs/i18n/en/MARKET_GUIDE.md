# Expert Memory Market implementation guide

This guide covers the real production paths for buyers, publishers and agent
integrators. Public discovery, paid delivery, publisher accounting and proof
are separate contracts. That separation is deliberate.

## Choose the access path before integrating

- Use the 1-day Expert Market trial to validate navigation and API fit without a wallet transaction.
- Use Expert Pass for seven days of broad storefront exploration with a scoped `ask_` key.
- Use per-read access when each delivered Memory Unit must be attributed and paid to its publisher.
- Do not mix pass economics with publisher revenue: the pass funds storefront access; Meter capture funds the publisher split.

## Inspect a listing before buying

Call `GET /market/v1/listings?q=<topic>` without a key. Each item exposes a
public summary, `rank_score`, `rank_reasons`, Truth state, Provenance state,
price and publisher metadata. `GET /market/v1/listings/<memory_id>` returns one
listing but never the paid body.

Reject listings that lack enough public evidence for your policy. A high score
is not an instruction to trust: inspect the reasons. A rejected claim ranks
below an unverified one, and popularity is not a ranking signal.

## Start with the free trial

Open `/` with `trial=expert-market`, or use the setup wizard. The browser creates
an actor identity and keeps its private signing key locally. The Gateway issues
one 1-day trial per actor and product. Store the returned `ask_` key in a secret
vault; never place it in a URL, log or client-side analytics event.

The trial proves product fit. It does not create a wallet transaction, publisher
split or permanent entitlement.

## Buy with a pass or per delivered read

For Expert Pass, open `/billing?plan=expert.pass.7d`, create an exact invoice,
send canonical USDC on Base and wait for KOVA finality. The Gateway issues a
product-scoped key valid for seven days. Checkout recovery is available for 48
hours; store the key immediately.

For per-read access, create and fund an account in Attested Meter, keep the
`amk_` key server-side, then call `POST /market/v1/read` with `x-meter-key` and
`{"memory_id":"<id>"}`. Meter reserves the listing price before retrieval. It
captures only after paid content is returned; failure or refusal releases the
reservation.

## Publish expert memory and set a price

- Create a useful Memory Unit: precise title, honest public summary, tags and `source_refs`.
- Add Truth and Provenance evidence before charging when the claim can support it.
- Register a publisher at `POST https://meter.attestedmemory.net/v1/publishers` with your signed actor identity and Base payout address.
- Keep the returned publisher key private. Price only your own operation with `POST /v1/publishers/me/prices` and `expert.read:<memory_id>`.
- Verify the listing through keyless `GET /market/v1/listings` before sending buyers to it.

The standard captured-read split is 70% publisher and 30% platform. Publisher
Pro changes it to 85% / 15%. Above the configured minimum, the operator emits a
signed `attested.payout/v1` instruction and records the payout transaction hash.

## Integrate an autonomous agent

- Separate discovery from purchase. Let the agent search and score public metadata before authorizing spend.
- Apply your own maximum price, allowed publishers, Truth states and source policy.
- Keep `ask_` and `amk_` credentials in server-side secret storage and redact them from traces.
- Treat `401` as bad credentials, `402` as access or balance required, `403` as wrong scope and `429` as backoff.
- Persist the listing ID, rank reasons, charge ID and provenance receipt beside the agent output.
- Use idempotency for invoice creation and never retry a transfer by inventing a new amount.

## Roll out to a team

- Define the first knowledge category and the decision it improves.
- Seed 10–20 high-signal listings before inviting buyers.
- Agree on the minimum public summary and required source references.
- Test a successful read, an unknown memory, insufficient balance, upstream failure and key revocation.
- Monitor discovery-to-read conversion, refused reads, capture/release balance, publisher accrual and payout backlog.
- Review old listings and Truth state on a schedule; do not let freshness masquerade as correctness.

## Know the trust and money boundaries

Memory Market ranks listings and serves entitled memory. Attested Meter owns
per-read reservations, capture, publisher accounting and payout instructions.
Attested Prove makes receipts and provenance verifiable without sharing an API
key. KOVA verifies exact subscription settlement through an authenticated
service-to-service path and remains independently available through federation.

No component asks for a wallet seed phrase or private key. Subscription funds
move directly to the configured recipient; publisher payouts are signed,
recorded instructions executed separately. See [KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md)
and [MARKET_USE_CASES.md](MARKET_USE_CASES.md).
