# One client call for a wallet-funded pipeline

[English](one-call-pipelines.md) · [Русский](one-call-pipelines.ru.md) · [Español](one-call-pipelines.es.md) · [Français](one-call-pipelines.fr.md) · [中文](one-call-pipelines.zh.md)

`await run_pipeline(...)` performs preparation, local signing, root execution and automatic waiting as one client operation. On the normal path it uses **two primary Hub requests**: prepare the graph, then invoke the root. Blockchain RPC calls are additional. HTTP 202, transport failures or temporary Hub errors can require more requests to the same order; two HTTP exchanges are not a completion guarantee.

## Independent sellers and recovery: 3.10.1

A paid graph can now include a trusted peer that advertises **`SELLER-OP/1`**, without `SELLS_FOR`, a resale account or a peer credit API key. The buyer pays that seller's invoice from real wallet funds. Keep `source_hub` in each node; the existing `run_pipeline(...)`, HTTP and MCP entry points select this adapter automatically. Free graphs still require no payment source.

Preparation reads the peer's signed discovery document and asks that same peer for a signed offer. The peer must be active and trusted, with pinned signing keys; a pinned PQ key is mandatory for verification too. The adapter checks the SKU, buyer, catalogue price, declared payout address, token, chain, split amounts and expiry. It never follows an offer to an arbitrary URL. Incompatible peers fail preflight with `settlement_route_unsupported`, before any signature or payment. Preparation may create an unused seller invoice; it performs no work and transfers no funds.

The seller creates a persistent `operation_id` and a scoped `operation_token`. Its signed offer contains terms, invoice nonce/expiry and input schema. The token stays in the buyer Hub's private run state, never in the public bill. Input may depend on earlier steps; the concrete input, buyer and transaction hash become immutable at the first invocation. A changed request returns HTTP 409. The seller holds its own invoice secret; the buyer Hub does not mint a competing invoice or forward credit credentials or SUB/1 grants. Wallet private keys remain with the client.

The three seller routes are `POST /ai-market/v2/operations/prepare`, `POST /ai-market/v2/operations/{operation_id}/invoke`, and `GET /ai-market/v2/operations/{operation_id}`. Invoke and status require `X-Operation-Token`; an absent or invalid token returns 404. Prepare accepts `product_id`, `capability_id`, `wallet`, `max_price_usd`; invoke accepts `input`, `wallet`, `tx_hash` (omit the hash for free work). A nonterminal invoke returns 202; terminal success or failure returns 200, so inspect `status` and `success`. Status returns a signed object and never dispatches work or sends money. These are seller-facing routes; ordinary pipeline callers still use the existing two primary requests.

After the buyer Hub broadcasts the original signed transaction and verifies settlement, it reads the remote operation before invoking it. The seller also checks settlement, stores the dispatch claim before calling its provider, and caches the signed outcome. Status signatures bind the operation to the offer digest, input digest, wallet and transaction hash. A lost HTTP response is recovered by reading the same operation; a completed result survives a seller restart. The root bill includes `payment_rail: independent_seller`, the signed seller offer and status/receipt. A local SUB/1 child links this result into the root tree, funded by `own`, without transferring a credit allowance across hubs.

A buyer worker renews its execution lease every 30 seconds. After 180 seconds without renewal, a persisted in-flight `SELLER-OP/1` child can be resumed by the same root invoke. The server atomically transfers ownership and fences stale state writes. Read-only status advertises `resume_same_run`; the SDK retains the original bundle. It does not unlock an arbitrary legacy provider. This recovery requires the durable remote step/job to have been saved; other uncertain states remain for operator reconciliation.

This is **at-most-once dispatch with durable results**, not universal exactly-once execution. The final provider receives a stable `Idempotency-Key` and `X-AIMarket-Operation-Id`; it must implement durable idempotency to eliminate its own execution/response gap. If the seller crashes around that boundary or cannot establish the outcome, it reports `reconciliation_required` and does not dispatch again. A stale seller claim is reported after 180 seconds, without unlocking it. `recovery.action: contact_operator` means reconcile that operation; `replacement_payment_allowed` remains false. Seller operations currently wrap local listings, excluding recursive `pipeline.run@v1`; arbitrary generic x402 endpoints do not acquire this protocol automatically.

Deploy Hub **3.10.1** with database migrations **44** (seller operations) and **45** (pipeline worker leases). Existing payment contracts need no redeployment. Update independent peers too if they are to expose this seller contract. One funded graph still uses one chain/token; the packaged paid client still supports Base USDC and requires native gas. Gas sponsorship, multiple networks, distributed wallet nonce coordination and automatic refunds are not added by this release.

Validation covers separately keyed databases, immutable requests, forged/changed offers, concurrent invokes, lost responses, stale buyer fencing, dynamic inputs, free chains and local Anvil settlement through the actual Hub payment path. Two Anvil scenarios use a disposable token and development wallets, including response loss; they prove the integration, not deployment of every external seller. Production smoke evidence is recorded separately. No additional mainnet charge is needed for these checks.

## 1. Prepare the graph

Call `POST /studio/prepare-pipeline` with `nodes`, optional `wallet` and `max_budget_usd`. It combines the old `/studio/preflight` and `/studio/paid-runs/{run_id}/prepare-pipeline`. The response contains `ready`, `blockers`, step identities and terms, `total_units`, `run_id`, `access_token`, `graph_digest`, `wallet`, `expires_at`, and `offers` with invoice nonces and EIP-712 authorizations. Preparation creates no root job and sends no payment. A free graph needs no wallet and returns an empty `offers` array. A paid graph without a wallet is refused. The old endpoints remain available. The manifest advertises the new route as `pipeline_execution.prepare_graph`.

`max_budget_usd` in the Hub request limits service charges only. The SDK’s `max_total_usd` additionally checks the network-fee allowance described below.

```json
{
  "nodes": [
    {"id": "weather", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}},
    {"id": "air", "product_id": "gaia.gateway", "capability_id": "gaia.air.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}, "depends_on": ["weather"]}
  ],
  "wallet": "<buyer-address>",
  "max_budget_usd": 1
}
```

## 2. Sign locally and invoke

The client binds the response to the requested graph and wallet, checks every offer and authorization, balances, chain, pending nonces and estimated gas. It locally signs EIP-3009 authorizations and EIP-1559 transactions, assigns consecutive wallet nonces and saves the complete bundle before sending it. The Hub receives signed transactions, never the private key. Send one `pipeline.run@v1` root request; the executor broadcasts a child payment only when that step is ready. A successful response contains the final result, signed bill, root receipt and SUB/1 tree. Inspect `status` and `success`: a failed delivery is a terminal result too, and an external payment is not automatically refunded.

```json
{
  "product_id": "hephaestus",
  "capability_id": "pipeline.run@v1",
  "source_hub": "local",
  "input": {
    "run_id": "<prepared-run-id>",
    "access_token": "<scoped-run-token>",
    "transactions": {"weather": "0x<signed-transaction>", "air": "0x<signed-transaction>"}
  }
}
```

## Python and command line

Install the released wheel with its `client` extra (command below). The client pays in native **USDC on Base (8453) or Ethereum (1)** (see [additional payment profiles](#additional-payment-profiles-and-multiple-client-hosts--sdkhub-3140)) and is tested on macOS/Linux. Any other chain or token is refused unless your own `accepted_assets` policy lists it. Free graphs require neither signer, RPC nor exchange-rate ceiling. The signer is a local object exposing `address`, `sign_message` and `sign_transaction`.

```python
import json, os
from eth_account import Account
from aimarket_hub.pipeline_client import run_pipeline

result = await run_pipeline(
    json.load(open("blueprint.json")),
    hub="https://modelmarket.dev",
    signer=Account.from_key(os.environ["PIPELINE_WALLET_KEY"]),
    rpc_url="https://mainnet.base.org",
    max_total_usd="1",
    state_path="order.private.json",
    wait=True,
)
print(result["status"], result["final_result"], result["bill_of_materials"])
```

```bash
python examples/pipeline-run/run.py blueprint.json \
  --hub https://modelmarket.dev --rpc https://mainnet.base.org \
  --max-total-usd 1 \
  --execute --prompt-key --state order.private.json
```

`--prompt-key` reads a key locally without echo; alternatively supply `PIPELINE_WALLET_KEY` securely in the environment. No key is needed for a free graph or a resume after signing. `--execute` is mandatory for a new CLI order. The earlier `client.py --budget` example remains available with its original service-only budget semantics. Release 3.10.1 requires Hub deployment and database migrations 44–45; no payment smart-contract redeployment.

## Budget, state and recovery

`max_total_usd` includes services and a conservative allowance for gas. ETH/USD is read from the pinned Chainlink Base feed through two RPC hostnames before signing and before every root submission or retry. The default second endpoint is `https://base-rpc.publicnode.com` (or `https://mainnet.base.org` when PublicNode is primary); set `price_rpc_url` / `--price-rpc` to use another trusted provider. Both observations must pass: Base chain ID, an 8-decimal positive completed round no older than 1500 seconds, a block no older than 120 seconds, and an UP sequencer past a one-hour recovery grace period. Feed calls use the observed block number. More than 2% price disagreement stops payment. Budget valuation is the higher price **plus 25%**. The optional legacy `native_usd_ceiling` is now an additional floor: it can increase this valuation but cannot lower it or bypass an unavailable oracle. A rise to $20,000 therefore means at least $25,000 for the gas calculation, even if an old recovery file contains 6000.

Each payment reserves 300,000 gas at twice the observed gas price and 100 times the Base GasPriceOracle L1 upper bound for 2048 bytes, plus $0.05 per order. Exceeding the saved budget pauses submission and preserves the same order and signatures. Missing, stale or inconsistent oracle data also blocks new submissions; it never falls back to a fixed price. Free graphs and locally cached completed results require no oracle. After an interrupted submitted order, read-only status recovery comes before repricing. The recovery file records both observations, rounds, timestamps and the valuation used. Never replace an uncertain order just because repricing stopped a retry.

The check runs at the client submission boundary, not continuously while the Hub executes a long graph. RPC providers remain a trust dependency; different hostnames do not prove independent infrastructure. USD exchange rates and Base L1 fees can change after submission and are not capped by an EIP-1559 signature. This is conservative budget protection, not a guaranteed dollar escrow.

[Chainlink ETH/USD — Base](https://data.chain.link/feeds/base/base/eth-usd) · [L2 sequencer](https://docs.chain.link/data-feeds/l2-sequencer-feeds).

The recovery file is atomically replaced with mode 0600 and fsynced; a separate file lock rejects concurrent use of the same path. It contains scoped credentials and executable signed transactions, so keep it private. It contains no wallet private key. Once the bundle is saved, resume needs no signer and never selects another nonce or creates a replacement payment. If interruption happened before signing, the original signer is still needed. A lost preparation response can leave an unused quote; no payment or root job exists at that stage. Use a wallet without other concurrent transactions.

Waiting is enabled by default. HTTP 202 continues the same order; after transport errors the client reads its status before resubmitting the original payload. `PipelinePending` preserves the state path on wait timeout or when reconciliation is required. A busy server claim is polled read-only and never unlocked by the client. `wait=False` returns a pending response for the caller to resume. A completed local recovery file returns its cached result without network calls. A failed child is not retried or repurchased automatically. To resume, omit the blueprint and budget/RPC overrides; the saved policy and graph are immutable.

```python
result = await run_pipeline(resume=True, state_path="order.private.json")
```

```bash
python examples/pipeline-run/run.py --resume --state order.private.json
```

[Codex: one client operation, two paid subcontractors](case-study-codex-one-call.md) — 2026-09-30.

## Agent access update: 3.9.0

Install a versioned wheel without cloning the repository. The live signed manifest publishes `pipeline_execution.client.distribution`, including its URL and SHA-256. The distribution is served by the Hub; this does not imply that PyPI already carries this version.

```bash
pip install "aimarket-hub[client] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
aimarket-pipeline --help
```

The installed `aimarket-pipeline` command accepts the same arguments as `examples/pipeline-run/run.py`. The `client` extra includes payment signing and ML-DSA verification. Python 3.11+ is required. Linux/macOS are tested; Windows locking has an implementation but has not been tested in this release. A hosted HTTP/MCP client may use any language and keep its signer outside the Hub.

Three MCP tools now expose the full protocol: `pipeline_prepare`, `pipeline_invoke`, `pipeline_status`. Preparation accepts the graph, service budget and optional wallet; invoke accepts `run_id`, `access_token` and the locally signed bundle; status accepts only the run ID and token. A free graph needs no signer or payment source. A remote MCP server cannot sign on behalf of a wallet it does not control: connect a local signer or use the Python client for paid execution. Never send a private key as a tool argument. Preserve full signatures and offers; these tools do not truncate them.

The SDK verifies the signed preparation, bill and terminal root receipt, their graph/run/wallet bindings and result/bill digests, including a cached local result. It pins the Hub signing keys from the first HTTPS preparation. Supply `trusted_hub_key` and `trusted_hub_pq_key` (CLI: `--trusted-hub-key`, `--trusted-hub-pq-key`) to establish trust independently. If a PQ key was pinned, removing the PQ signature fails verification. This checks the Hub's signed account of execution; it does not independently establish every device's identity.

`GET /studio/paid-runs/{run_id}/pipeline` with `X-Studio-Run-Token` reads the root result without sending money or invoking children. On resume or a lost response, the SDK reads this endpoint before checking RPC/gas again. A completed order can therefore be retrieved while RPC is down or fees have increased. Busy work is polled read-only. HTTP 429/5xx retries back off and respect numeric `Retry-After` within the remaining waiting window. `PipelineHTTPError` retains `status_code`, `detail` and `state_path` for automation.

A durable wallet reservation prevents two state files on the same host from signing overlapping nonce ranges. It lives in `~/.aimarket/wallets` (`AIMARKET_WALLET_STATE_DIR` can select a shared directory). Every cooperating client must use the same directory. A successful order releases the reservation. A failed order retains it until all signed nonces were consumed, or authorizations expired and no transaction is pending. Keep the original recovery file. Across different hosts or unrelated wallet software, use a shared signer/nonce coordinator or dedicated wallets; host-local files cannot coordinate arbitrary external signers.

Preflight returns stable `blockers[].code`, including `settlement_route_unsupported`, `route_unavailable`, `mixed_assets_unsupported` and `service_budget_exceeded`. Supported foreign routes are seller-of-record, configured resale and independent peers implementing SELLER-OP/1. The manifest explicitly advertises this boundary. A funded graph uses one chain/token; the Python client accepts Base USDC. This is not a promise that every catalogue listing accepts the same payment rail.

If a provider executed but its answer was lost, the Hub must not automatically purchase again. Status reports `recovery.action` (`wait`, `resume_same_run`, `contact_operator`) and disallows replacement payment. Reconciliation requires the provider's receipt or other execution evidence. Unsent children remain unpaid; already confirmed external payments are not automatically refunded. This unavoidable uncertainty is surfaced explicitly rather than silently replayed.


Production follow-up, 2026-09-30: the separate seller Hub at `https://independentai.network/hub` completed `kova.network.status@v1` for 0.002 USDC on Base. The buyer deliberately lost the first response and resumed the same operation, without a replacement payment. Both Hubs are administered by the same operator; this demonstrates a separate seller deployment and payout, not independent business ownership.

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · [Evidence](evidence/independent-seller-mainnet-2026-09-30.json) · [Oracle RPC evidence — SDK 3.10.2](evidence/native-price-oracle-2026-09-30.json).


Production prepaid-provider test, 2026-09-30: `weather.witness@v1` now publishes its actual payout address and runs in fixed-price mode. A separate provider account started at zero, with zero grants and collateral. A real 0.02 USDC EIP-3009 deposit funded it; the buyer then paid 0.002 USDC for the root SKU. The provider bought GAIA weather and air for 0.001 each from that cash-backed prepaid balance, leaving 0.018. This is prepaid internal accounting after a real deposit, not two additional on-chain child transfers or a credit line. The provider's daily cap is 0.02; replenishment is not automatic. The result for Berlin was agreement=true, temperature 14.5°C, humidity 64%, PM2.5 9.9 µg/m³ and US AQI 33, sampled at 2026-09-30T07:01:32Z. Root run `paid_580f85c4a2f4deba7a83bc26140fc558` has job `job_db9c841f8a360f04c891a68b` and both child receipt digests. An RPC 429 after local signing stopped submission; resuming the saved bundle completed the same order. Both this deposit and purchase used the live oracle budget policy. Conservatively accounted cumulative test spending is $0.047149423922618862625 of the $1 limit; the entire deposit is included and child prepaid debits are not counted twice.

[Evidence](evidence/witness-prepaid-mainnet-2026-09-30.json) · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


SDK 3.10.3 retries an identical RPC request up to three times on HTTP 429/5xx or transport failure, with bounded backoff (at most five seconds per delay). Exhausted retries stop submission and retain the existing order; they do not substitute a fixed exchange rate or create a new payment.

## Package publication status — checked 2026-09-30

PyPI `aimarket-hub==3.10.3` now contains both wheel and source archive. Its 131 package files were compared with the production build and matched. Version 3.11.0 adds gas sponsorship and requires a new release; never replace published 3.10.3 files. The separate `aimarket-agent==2.5.0` publication remains to be checked. Package publication and Hub deployment are separate operations. Provider recovery, refunds and broader network/token support remain subsequent stages.

## Gas sponsorship — SDK 3.11.0

`gas_mode="auto"` is the new SDK default. The prepare response, signed by the Hub, says whether sponsorship is available for the entire graph. If available, the buyer signs only the exact EIP-3009 USDC authorizations locally. The operator's separate wallet signs and pays for network transactions. The buyer needs no ETH, no transaction-signing method, and no RPC configuration for this route. `gas_mode="required"` refuses a paid graph during preparation if sponsorship is unavailable; `gas_mode="buyer"` keeps the existing buyer-paid gas route. Raw HTTP and MCP preparation default to `buyer` for compatibility. CLI: `--gas-mode required`.

Preparation returns `gas_sponsorship`; root invocation accepts `authorizations: {step_id: signature}` instead of `transactions`. Never send both. The quote fixes the funding mode, buyer, recipients, amounts, authorization nonces and expiration. Changing the bundle on retry is refused. The Hub never receives the buyer's private key. The signed bill identifies sponsorship and each payment's gas payer; buyer gas fee is zero. Existing free graphs require neither a signer nor a sponsor, even with `required`.

The initial sponsor supports direct Base 8453 USDC payments, including compatible independent sellers. The existing MarketSplitter binds its payer to `msg.sender`, so fee-split payments are explicitly ineligible. No contract redeployment is required for the direct route. `auto` may fall back to buyer-paid gas; `required` cannot. Sponsorship cannot promise unlimited capacity: an empty sponsor wallet, exhausted daily allowance, unavailable price oracle or occupied nonce returns a pending order to resume, with no replacement payment.

Before each new payment, the Hub checks the live ETH/USD oracle, its conservative gas estimate, sponsor balance and per-payment/daily limits. Only after resolving and validating the step's input does it reserve one wallet nonce and save signed transaction bytes atomically in the shared database. One transaction may be in flight per sponsor wallet. Competing workers share the nonce and budget ledger; retries rebroadcast identical bytes. A crash after saving relay bytes is recoverable even after quote expiry, because the transfer may already have happened. Cached completed results need no RPC. Separate sponsor databases must not share a gas wallet.

Operator configuration: `AIMARKET_PIPELINE_RELAY_ENABLED=1`, `AIMARKET_PIPELINE_RELAY_KEY_FILE` (private, non-symlink file), `AIMARKET_PIPELINE_RELAY_RPC`, optional `AIMARKET_PIPELINE_RELAY_PRICE_RPC`, `AIMARKET_PIPELINE_RELAY_DAILY_WEI` (default 20000000000000), and `AIMARKET_PIPELINE_RELAY_MAX_GAS_USD` (default 0.10). Fund a dedicated gas wallet; never install the buyer's key. Daily accounting reserves conservative native fee bounds and does not release the difference after mining. USD gas estimates are conservative checks, not an immutable on-chain USD cap. Already saved transactions remain recoverable if new sponsorship is disabled.

Validation includes competing workers on separate database connections, budget rollback, invalid buyer signatures, immutable recovery, free graphs, and a real Anvil EIP-3009 transfer from a buyer with zero ETH. These tests do not assert production deployment or completion of the remaining provider-recovery, refund and multichain work.

Production verification on 2026-09-30: a free LOGOS step followed by `kova.network.status@v1` at `https://independentai.network/hub` completed through a message-only signer, without SDK RPC configuration. Buyer service cost: **0.002 USDC**; buyer gas: **0**; buyer ETH balance and transaction nonce were unchanged. The deliberately lost first invoke response recovered the same order. KOVA returned `pass`, score 100, Base block 51983924. The operator sponsor paid 516607663289 wei. Its entire 0.00002 ETH funding was already counted, so sponsor gas is not counted twice. Conservative cumulative test spend: **$0.1163241752052936711504319125 of $1**, including all earlier tests and the full sponsor funding. Run and transaction evidence below contain no access tokens or private keys.

`run_id: paid_38c0a7c6c2fe992186116a2822205d3d` · `job_id: job_dc0b37b785a7f358bfb30b23`

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · [Evidence](evidence/gas-sponsorship-mainnet-2026-09-30.json)

## Provider result recovery — SDK/Hub 3.12.0

`PROVIDER-OP/1` closes the gap where a provider finishes but its reply does not reach the seller Hub. A compatible provider records the operation ID and a digest of product, capability and input before executing. It commits the result and its signature before returning. Repeating the same operation returns the durable result; a changed request is refused. Concurrent requests do not execute twice. KOVA implements this journal in its existing SQLite database.

The seller explicitly enables compatible products with `AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`. New signed `SELLER-OP/1` offers advertise `provider_recovery: PROVIDER-OP/1`; the original provider URL and public key are pinned in the private operation state. After a lost reply or stale execution claim, the seller reads `GET <invoke_url>/operations/<operation_id>`. It checks the provider's signature, operation ID, product, capability, exact input digest, and the separately signed result. Paid work is recovered only if the original payment verification was saved. The terminal seller response is immutable, including when an old worker finishes late. Recovery performs no second provider POST and creates no new payment.

KOVA invoke and status endpoints require the same private Hub-to-provider token. Configure matching `AIMARKET_CAPABILITY_TOKEN` and `KOVA_CAPABILITY_TOKEN`, and allow only the operator's provider host through `AIMARKET_INVOKE_HOST_GATEWAY`. Keys and scoped operation tokens are never part of public evidence. Ordinary buyer calls continue through the Hub's payment and authorization checks.

This is cooperative recovery, not an exactly-once claim for arbitrary remote side effects. A provider that crashes between an external side effect and saving its result reports an unknown outcome; it is not re-executed automatically. Such a provider must bind its business transaction to the operation ID, or reconcile the effect before publishing a result. Legacy providers retain manual reconciliation. KOVA's unknown journal entries remain blocked, protecting against duplicated writes.

A previously paid invoice may be redeemed after its expiry when the verified block timestamp is strictly before expiry. Paying after expiry remains invalid; nonce consumption and replay protection stay enforced. Comma-separated explicit RPC overrides now remain an exclusive list rather than becoming one invalid URL. Public pipeline bills omit the internal job grant field.

Tests cover provider restart/replay, concurrent dispatch, changed input, authenticated status, signed result tampering, recovery across two Hubs without another transfer, an unknown side effect, and the invoice expiry boundary.

Production verification, 2026-09-30: LOGOS → KOVA completed for 0.002 USDC with zero buyer gas. After restarting KOVA, the seller recovered its signed result via GET from the persistent provider journal. Response loss was simulated in an isolated copy of the seller operation; production ledgers were untouched. Recovery made no new provider invocation or payment. The recovered Base block remained 51984647. Gateway status without the private token returned 401; an authorized lookup of an unknown operation returned 404. Cumulative conservative test spend: $0.1183241752052936711504319125 of $1. Refunding and broader network/token support remain subsequent stages.

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · [Evidence](evidence/provider-recovery-mainnet-2026-09-30.json)


## Seller-approved refunds — SDK/Hub 3.13.0

A confirmed direct Base USDC payment can be returned through `SELLER-REFUND/1`. The buyer requests a refund offer for a terminal pipeline step; the original seller approves it with a local EIP-3009 signature. The sponsor pays gas for the return transfer. Neither party sends a private key to the Hub or needs ETH for this route. Preparing an offer does not move funds or compel the seller to accept a refund.

HTTP uses the original `X-Studio-Run-Token`: `POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` creates or retrieves the signed offer; `POST /studio/paid-runs/{run_id}/refunds/{step_id}` accepts `{"authorization":"0x…"}` and advances the same refund; `GET` on that path reads its status. HTTP 202 means pending. MCP exposes `pipeline_refund_prepare`, `pipeline_refund`, and `pipeline_refund_status`, with the same run ID, scoped access token and step ID. Send only the seller signature, never a wallet key.

The SDK helper `refund_pipeline(state_path=..., step_id=...)` returns the offer without payment. Send only its `offer` object to the seller, not the buyer recovery file. The seller calls `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)` from `aimarket_hub.refund_client`. The approved recipient, original payment, amount cap, token, chain and Hub signature are checked locally. Submit the returned signature using `refund_pipeline(..., authorization=signature)`. Subsequent calls with the same private state file recover the same refund; `RefundPending` retains its identity. Applications must decide whether the refund is owed before signing.

The Hub accepts only the original seller, original buyer and exact full paid amount. It requires a verified original payment and completed or failed pipeline, so an unknown provider outcome must be reconciled first. The refund signature is immutable after submission. Signed transaction bytes are committed before broadcast and share the sponsor's database nonce and budget coordinator. Lost responses and restarts reuse the same transaction. An expired approval can be renewed only before the Hub has signed a transaction; its refund ID and authorization nonce remain unchanged, preventing two transfers with old and renewed approvals.

The original signed bill and result remain immutable. A separate signed `pipeline.refund/1` credit note links the original and refund transaction hashes, amount, token, chain, parties and gas payer. Status reads do not send money. This first refund route supports one full refund per direct Base USDC payment with zero split fee and an available sponsor. Partial refunds, MarketSplitter fee recovery, unilateral debits and arbitrary-token refunds are not implemented. A seller can refuse approval or lack funds; exhausted sponsor capacity keeps the same refund pending. Gas already consumed is not refunded. Free graphs still require no payment source.

Validation covers wrong signers, changed amounts, concurrent state protection, expired approvals, immutable committed transactions, lost responses, SDK/MCP parity and an Anvil purchase plus refund where both buyer and seller need no gas funds. Mainnet verification is reported separately below when completed.


Mainnet verification, 2026-09-30: a temporary operator-owned static SKU delivered its result for 0.001 USDC, then its separate seller wallet approved a full 0.001 USDC refund. This fixture tests real settlement and refund mechanics, not an independent commercial seller. The buyer and seller USDC balances returned to their initial values; buyer ETH and nonce were unchanged. Both transactions were sponsored. A deliberately lost refund response recovered the same credit note; after a Hub restart, both the original result and refund were byte-for-byte identical JSON values. The temporary listing was removed. Cumulative conservative spending is $0.1193241752052936711504319125 of $1, counting the full sponsor funding and the gross purchase despite its refund. No new contracts were deployed.

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · [Evidence](evidence/refund-mainnet-2026-09-30.json)


## Additional payment profiles and multiple client hosts — SDK/Hub 3.14.0

The SDK now accepts native USDC on **Base 8453 and Ethereum 1**, with pinned addresses, six decimals and EIP-712 `USD Coin` / `2`. One paid graph still uses one chain and asset; split mixed-asset work into separate orders. The Hub must offer that payment route: accepting a network in the SDK does not move balances between chains or change a seller’s quoted currency. Free graphs are unchanged. Gas sponsorship and seller-approved refunds currently remain direct Base USDC features; an Ethereum order uses buyer-paid gas. `gas_mode="required"` refuses a paid route without a sponsor before signing.

`accepted_assets=[...]` replaces the SDK’s default allowlist. Each entry explicitly supplies `chain_id`, `token_contract`, `decimals`, `eip712_name`, `eip712_version`, `usd_pegged: true`, and `authorization: "EIP-3009"`. This is a buyer-owned policy for an audited dollar token, not a claim that an arbitrary ERC-20 has those properties. The Hub cannot add an asset to it. Decimal amounts are calculated without floating-point rounding. Non-USD assets, ordinary ERC-20 approval-only tokens, other chains and atomic mixed-chain graphs are refused rather than silently converted. CLI: `--accepted-assets approved-assets.json`. The recovery file pins the policy, and resume cannot change it.

For a local Ethereum seller, configure `AIMARKET_X402_CHAIN=ethereum`. Settlement and broadcast use the signed chain ID; `AIMARKET_SETTLE_RPC_1` and `AIMARKET_SETTLE_RPC_8453` select explicit endpoints per chain. A global `AIMARKET_SETTLE_RPC_URL` remains an exclusive fallback, so a Base-only override must not be used to serve Ethereum. Every RPC must report the invoice’s chain ID before receipt verification or broadcast. A custom Hub asset also requires its correct `AIMARKET_X402_ASSET`, `AIMARKET_X402_ASSET_SYMBOL`, decimals, `AIMARKET_X402_EIP712_NAME` and `AIMARKET_X402_EIP712_VERSION`, plus the buyer’s matching allowlist. Do not price non-dollar tokens as dollars.

Ethereum gas uses a fresh ETH/USD feed through two different RPC hostnames, a 25% price margin, bounded transaction gas and the existing $0.05 reserve. Ethereum has no Base L1 fee surcharge. Its pinned Chainlink feed is `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, eight decimals, heartbeat 3600 seconds and maximum age 3900 seconds. Base retains its sequencer check and separate L1 reserve. Wrong chains, stale blocks, stale prices and disagreement above 2% stop payment. Manual price input can only raise the ceiling.

For agents on multiple machines, install the `postgres` extra and configure the same **buyer-owned** `AIMARKET_WALLET_DATABASE_URL` before creating orders. Use a direct PostgreSQL connection or session pooling; transaction-mode PgBouncer cannot preserve session advisory locks. The coordinator serializes each `(chain_id, wallet)` across connections. The database stores the private recovery state, scoped Hub token and exact signed transaction bundle before submission; it never stores a wallet private key. Restrict database access to cooperating buyer agents. The DSN is not saved in the order or sent to the Hub.

To move an unfinished order, copy its private recovery file securely to the next host and call `run_pipeline(resume=True, state_path=...)`. A stale pre-signing copy loads the committed bundle from PostgreSQL, and a completed order is read before any new signing. Different orders cannot take over an unfinished reservation. A terminal failure releases ownership only after all signed nonces are consumed, or authorizations expire and no transaction remains pending. Database failure stops new submission; cached completed results remain readable. Keep the same database and schema on every cooperating host, and never mix independent coordinators or unrelated wallet software for that wallet. Local file coordination remains the default; sponsored buyers do not allocate transaction nonces and need no PostgreSQL.

Validation used a real disposable PostgreSQL with independent client connections, crash recovery, stale recovery files, missing checkpoints and no duplicate signing. A local EVM with chain ID 1 executed an actual SDK EIP-3009 purchase; native price checks are tested separately because that local chain has no Chainlink feed. Ethereum mainnet checks were read-only: both RPC observations agreed, and USDC’s name/version/decimals matched the pinned profile. No Ethereum mainnet purchase is claimed and no additional funds were spent.

[Circle contract registry](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD feed](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · [Read-only verification](evidence/ethereum-profile-2026-09-30.json)

Release delivery: the deployed Hub and downloadable client wheel are 3.14.0. PyPI was checked on 2026-09-30 and still reports `aimarket-hub==3.10.3` and `aimarket-agent==2.4.0`. The new publication artifacts are `aimarket-hub==3.14.0` and the separate provider SDK `aimarket-agent==2.5.0`. Publication credentials are not available in this workspace; uploading those packages to PyPI remains an operator action. Installing the pinned Hub wheel below already works without waiting for PyPI. Existing deployed contracts require no redeployment.

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```
