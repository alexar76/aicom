# Agent Embassy (aemb.pro) as an observed seller, 2026-11-03

Consent: DEV comment 3k05n (2026-11-03 16:31:29Z) under article 4804987, from agentembassy on DEV, which has
written about aemb.pro since 2026-10-01. The comment names the flagship route POST /v1/check/ping, at $0.001
USDC on Base, with payTo 0xD004278bC57FE4B9F743ABf17d713ed4169A88E9. It consents to probing, listing and paid
test calls.

- `dryrun-2026-11-03.json`: `observe_seller` run from the Mac on all 25 routes of /.well-known/x402.json. All 25
  were quoted on POST after HEAD answered 404, with the same payTo. `listed_price_usd` is null for a reason
  `parse_discovery` cannot get past. The resource `accepts` entries carry no asset address, since `asset: "USDC"`
  appears once at the resource level. The `pricing.price` string ("$0.001") is a field the parser does not read.
  The atomic `amount` agrees with each 402.
- `record.py`, `record-output.txt`: recorded on the apex hub at 18:04:46Z (server time), after the owner's yes.
  Only /v1/check/ping is recorded, as the consent names one endpoint, and payTo is pinned.
  Undo: admin DELETE `?origin=https://aemb.pro`.
- `catalogue-aemb-ping.json`, `plan.json`, `probe.jsonl`: one listing built from the live 402, then the
  delivery-survey `sample --host aemb.pro` and `probe` dry run. The listing was payable at $0.001.
- The paid call (owner confirmed $0.001, about 18:06Z): the route's own Bazaar example plus PAYMENT-SIGNATURE
  returned HTTP 400 `invalid_quote`, "quote_id is required". quote_id appears in none of the Bazaar example,
  x402.json or openapi.json. USDC shows the authorization unused. The buy and chain files name the survey
  payer, so they are kept out of the repository, in `~/aicom-survey-evidence/aemb-2026-11-03/`.
- Clock trap: the Mac ran 3,472 s ahead of UTC, and the x402 client takes validBefore from it. The authorization
  was therefore settleable until 19:09:15Z instead of about five minutes after signing.

Reply draft (the owner posts it): PromoMaterials/devto/x402-delivery-survey/reply-agentembassy-2026-11-03.md.
