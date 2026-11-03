# Codex: one client operation, two paid subcontractors

[English](case-study-codex-one-call.md) · [Русский](case-study-codex-one-call.ru.md) · [Español](case-study-codex-one-call.es.md) · [Français](case-study-codex-one-call.fr.md) · [中文](case-study-codex-one-call.zh.md)

On **30 September 2026**, Codex repeated the GAIA subcontracting test through the new `await run_pipeline(...)` client, with the same operator-provided wallet and a **$1 total budget**. The Hub ran `modelmarket-hub:prod-20260930-onecall`. Both children completed; the client handled confirmation retries automatically. Services cost **0.002 USDC**, and the measured total including gas was **≈ $0.00468270**.

## Procedure and observed requests

The client called `POST /studio/prepare-pipeline` with the two-step blueprint and wallet, checked the graph, payment terms, balances and fee budget, signed locally, saved the payment bundle privately, and invoked `pipeline.run@v1`. No administrator credential or private key was sent to the Hub. Calls came from Python in the Codex terminal, using the public REST API, not MCP. The caller awaited one SDK operation and did not manually issue a resume command.

| Order | Hub request | HTTP | Observed state |
|---|---|---:|---|
| 1 | `POST /studio/prepare-pipeline` | 200 | `ready` |
| 2 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 3 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 4 | `POST /ai-market/v2/invoke` | 200 | `completed` |

The paid test made **four Hub requests**, not exactly two. Blockchain RPC and exchange-rate requests are additional. The first prepare response supplied both the quote and authorizations. Each 202 resumed the same run with the identical signed bundle. There was one root job and two successful child calls. After completion, `run_pipeline(resume=True, ...)` returned the identical locally cached result with **zero additional Hub requests**. The test plus evidence checks took 11.872 seconds; this is an observation, not a latency guarantee.

## Graph and result

The graph bought `gaia.weather.read@v1` followed by `gaia.air.read@v1`, both from `gaia.gateway`, with `source_hub: https://iot.modelmarket.dev` and `city: Berlin`. `air` depended on completion of `weather`; no weather values were passed into the air call. The final result was a signed reading from **GAIA-AQ1 (Open-Meteo AQ relay)**, device `om-aq-01`, at **2026-09-30 04:24:34 UTC**. The evidence records the weather step as successful, but does not contain its intermediate reading. These are relay data, not proof of a separate physical Berlin sensor.

| Metric | Value |
|---|---:|
| PM2.5 | 8.8 µg/m³ |
| PM10 | 11.1 µg/m³ |
| US AQI | 33 |
| European AQI | 24 |

## Budget and settlement

The payer was `0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`; the USDC recipient was `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`. Settlement used existing USDC on Base mainnet, chain ID 8453. The buyer selected an ETH/USD ceiling of 6000; the last recorded conservative cost check was $0.1195256567368, below $1. Actual USD cost uses the Coinbase spot rate **$2673.555/ETH** observed during this run. Neither that spot price nor the conservative estimate is a hard on-chain dollar cap.

| Cost | Amount |
|---|---:|
| Services / USDC | 0.002 USDC |
| Gas (L2 + L1) | 0.000001003418744789 ETH |
| Gas / USD | ≈ $0.00268270 |
| Total / USD | ≈ $0.00468270 |

## Additional tests and verification

A two-step free LOGOS graph completed through the same SDK with no wallet, RPC or price ceiling, using exactly two Hub requests. A paid graph with a $0.003 total budget passed the service-price quote but was rejected locally because it could not cover the fee reserve: one prepare request, no root invoke, no payment. The local regression suite passed **84 tests**, plus **4 Anvil payment tests**. Tests cover response loss, identical retries, recovery without a signer after signing, gas-budget refusal, wrong chain or authorization, file locking, and terminal child failure.

The CLI also completed a free production graph, then returned the identical cached result on resume without a wallet key.

Both chain transactions succeeded. Their USDC transfer amounts and total network fees matched the buyer balance changes. Root and bill signatures were verified against the Hub key recorded before the test, together with the bill/result digests and two child receipt references. The air-reading signature was checked against its included key; no independent device-key pin was established. The public evidence contains signed results and chain receipts, but no private key, run access token or raw signed payment transaction.

This remains an operator-authorized integration test: GAIA and the Hub belong to the same operated ecosystem and the Hub is seller of record. It demonstrates real payment and subcontract execution, not independent customer demand. SUB/1 supplies job linkage; funding is `buyer_wallet`, children are `funded_by: own`, and no credit-line allowance was used. No smart contract was redeployed. The free SDK test does not certify the separately configured legacy `/studio/run` route.

## Evidence and reproduction

- [JSON](evidence/codex-one-call-2026-09-30.json) · [Blueprint](evidence/codex-one-call-2026-09-30-blueprint.json)
- [API / SDK](one-call-pipelines.md)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

Follow-up verification of the external-agent access update (3.9.0): 175 focused tests and four local Anvil payment tests passed. A clean client installation completed a free SDK graph in two Hub requests. MCP prepare/invoke/status completed another free graph. The original paid order was recovered with two GET requests (manifest and root status), without a wallet key or RPC. Hub receipt verification ran inside the SDK. This follow-up made no new mainnet payments. The wheel is distributed by the Hub, with its SHA-256 in the signed manifest; PyPI publication was not performed.

[JSON](evidence/agent-rails-2026-09-30.json)

## Follow-up: independent seller contract, 3.10.1

Codex added SELLER-OP/1 and deployed the Hub with migrations 44–45. The detailed protocol and limitations are in the pipeline guide. Validation: **223 focused tests and 6 local Anvil scenarios** passed, including two separate-hub settlements with a disposable token, one with a lost seller response. The buyer paid exactly 4,000 token units once in each independent-seller scenario; the seller owned and consumed the invoice. These are local-chain integration tests, not new mainnet purchases.

Production checks verified signed discovery, the released wheel and all five guides, a free MCP chain, a free SDK chain with two primary requests, and recovery of the original paid order using GET only. No additional mainnet payment was sent from the test wallet. The local weather.witness listing has no supported direct payout route: seller preparation now correctly returns 409/settlement_route_unsupported rather than 500, before execution or payment. This does not change its existing credit-backed SUB/1 contract. No independent production peer was upgraded or purchased in this test; that path was verified with two controlled hubs on Anvil.

[Sanitized verification evidence](evidence/seller-operations-2026-09-30.json). No private keys, operation tokens or signed transaction bundles are published.
