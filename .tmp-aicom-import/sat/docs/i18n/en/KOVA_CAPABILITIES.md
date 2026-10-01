# KOVA capabilities in Attested

## What KOVA is

KOVA is an independent Base and USDC service. It is not installed inside the
Attested Hub. KOVA publishes six products to the Hub, where agents can discover,
price and invoke them through federation.

## How an agent calls KOVA

The agent calls the Hub at `POST /ai-market/v2/invoke`; it does not call KOVA's
private provider URL. The Hub applies its access and settlement policy, records
the invoke, then routes the request to KOVA.

The six capabilities are `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1` and `kova.usdc.webhook.register@v1`.

## Why checkout takes another path

Attested subscription checkout calls KOVA's invoice API through an authenticated
service-to-service connection. It intentionally does not buy a paid KOVA
capability to verify the payment for that same purchase. This avoids recursive
billing and keeps one order responsible for one entitlement.

## Who pays KOVA

An Attested subscription sends the buyer's USDC directly to `SAAS_PAYMENT_RECIPIENT`.
There is no automatic split or percentage for KOVA in this transfer. The Gateway
uses a dedicated `KOVA_API_KEY`; if that key comes from a paid KOVA Pro or Business
plan, the operator buys or renews it separately. Federated capability calls are a
third, separately metered flow: their per-call price and Hub routing fee are recorded
as capability consumption and never deducted from an Attested subscription payment.

## What is visible

Federated capability use is recorded by the Hub as an invoke with price, status
and receipt. Attested subscription orders, trial and paid keys, and request
counts are shown separately in the protected Operator ledger. KOVA's protected
Settlement desk shows its own orders, key prefixes and API usage. Plaintext keys
are never listed in either desk.

## Security boundary

The provider route requires the private `X-AIMarket-Internal-Token`, rejects a
route/body identity mismatch, and applies stricter budgets to write capabilities.
KOVA returns `X-Provider-Signature`: its Ed25519 envelope binds `product_id`,
`capability_id`, the input hash and the result, so a result cannot be replayed for
another input. Rotate the shared token if either service is compromised.

## Safe setup

Use a random 32+ character `KOVA_CAPABILITY_TOKEN` equal to the Hub's
`AIMARKET_CAPABILITY_TOKEN`. Configure `KOVA_HUB_URL` and `KOVA_INVOKE_BASE` on
KOVA. Keep these provider endpoints on the private service network; expose the
public Hub invoke instead.
