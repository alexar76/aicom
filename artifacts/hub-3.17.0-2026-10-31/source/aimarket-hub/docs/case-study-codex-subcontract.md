# Case study: Codex orders and pays for subcontracting

[English](case-study-codex-subcontract.md) · [Русский](case-study-codex-subcontract.ru.md) · [Español](case-study-codex-subcontract.es.md) · [Français](case-study-codex-subcontract.fr.md) · [中文](case-study-codex-subcontract.zh.md)

On **29 September 2026**, an agent running in **Codex** completed a real order on
[modelmarket.dev](https://modelmarket.dev) through `hephaestus / pipeline.run@v1`.
The root executor bought two GAIA capabilities, paid **0.002 USDC on Base mainnet**,
and returned a completed SUB/1 job tree, a signed bill and an air-quality result for Berlin.
The total including network fees was approximately **$0.00477**, within the user's $1 limit.

This was an operator-authorized integration test using an operator-provided buyer wallet.
GAIA and the Hub belong to the same operated ecosystem; the Hub was seller of record and
received the payments. The run demonstrates execution and settlement with real funds; it
does not establish independent customer demand or purchases from an independently owned seller.

## What Codex did

The Hub update was deployed first. The purchase then used the **public REST API** from
Python and HTTP commands in the Codex terminal, without Hub administrator credentials.
It was not an MCP purchase or a browser-wallet flow.

1. Sent the [two-step blueprint](evidence/codex-subcontract-2026-09-29-blueprint.json) to
   `POST /studio/preflight`, preserving `source_hub: https://iot.modelmarket.dev`.
2. Called `POST /studio/paid-runs/{run_id}/prepare-pipeline` with the buyer address.
3. Checked balances, Base chain ID **8453**, recipients, amounts and gas against the budget;
   signed EIP-3009 authorizations and EIP-1559 transactions locally. The private key was
   never sent to the Hub.
4. Submitted `pipeline.run@v1` to `POST /ai-market/v2/invoke`. The executor broadcast each
   payment immediately before the corresponding child call.
5. Continued the same run after HTTP 202 while confirmations were pending. These were
   retries of **one logical order**, not new purchases. After a Hub restart, a repeated
   invoke returned the identical cached result, job and transaction hashes.

```text
Codex → pipeline.run@v1
          ├─ weather: gaia.weather.read@v1 — 0.001 USDC
          └─ air:     gaia.air.read@v1     — 0.001 USDC
```

Both children have product ID `gaia.gateway`. The `air` step depends on `weather`
finishing; both receive `city: Berlin`. This graph orders two purchases but does not
feed weather data into the air step or evaluate agreement between their readings.

## Result and cost

Both children succeeded. The final step returned a signed reading from
`om-aq-01`, **GAIA-AQ1 (Open-Meteo AQ relay)**, at **2026-09-29 20:33:02 UTC**:

| Berlin air-quality field | Value |
|---|---:|
| PM2.5 | 7.9 µg/m³ |
| PM10 | 10.1 µg/m³ |
| US AQI | 41 |
| European AQI | 28 |

These are the relay's returned data, not evidence of an independently deployed physical
sensor in Berlin. The saved final response contains the air reading; it records the
weather step's successful receipt but does not include its intermediate reading.

| Cost | Observed amount |
|---|---:|
| Two services | 0.002 USDC |
| Network fees, including L1 data fees | 0.000001029431613611 ETH |
| Network fees at the recorded ETH/USD rate | ≈ $0.00276894 |
| Total | ≈ $0.00476894 |

The USD conversion uses **$2689.775/ETH**, the Coinbase spot quote recorded during the
order. Token amounts and fees are transaction facts; the dollar total is approximate.

## Evidence and scope

- [Public evidence bundle](evidence/codex-subcontract-2026-09-29.json): complete signed root
  response, bill, job tree, chain receipts and the Hub public key recorded before deployment.
- Weather payment: [`0x8982…a2285`](https://basescan.org/tx/0x8982b8ac596d0192254017149bc2d1c050c05e838aba7fd5528de7776b0a2285).
- Air payment: [`0xf974…dc016`](https://basescan.org/tx/0xf974e08b83c1518bed93bfac457f98d7088d3ae6901af9421950d402fb0dc016).
- Run: `paid_b78330d3c706ea5bc21424fc06d52603`.
- Job: `job_5d97a26f221d2cec0730e673` — one root and two children.

The root and bill signatures were verified against the previously recorded Hub key,
including the root's bill/result digests and two child receipt references. The device
reading signature was consistent with its included key; no independent device-key pin
was checked. Both chain receipts succeeded, and their fees matched the buyer's ETH decrease.
The bundle contains no wallet private key, run access token or raw signed transaction.

SUB/1 links the work. Funding is `buyer_wallet`; children are marked `funded_by: own`.
There was no credit-line allowance or `X-AIMarket-Job-Grant`. Separately, a two-step free
LOGOS graph completed through the new SKU without a wallet. The legacy `/studio/run`
route still required Factory federation configuration at the time of this test.

For a new order, obtain fresh quotes and authorizations using the
[agent example and protocol](../examples/pipeline-run/README.md). The recorded IDs are
historical evidence, not reusable payment credentials.

[New live test from Codex](case-study-codex-one-call.md) · [One-call pipelines](one-call-pipelines.md) — 2026-09-30.
