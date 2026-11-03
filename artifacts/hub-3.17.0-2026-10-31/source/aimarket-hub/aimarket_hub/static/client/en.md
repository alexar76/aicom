# One client call for a wallet-funded pipeline

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

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

[Codex: one client operation, two paid subcontractors](https://modelmarket.dev/clients/pipeline-guide/en) — 2026-09-30.

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

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · Evidence: `independent-seller-mainnet-2026-09-30.json` · Oracle RPC evidence — SDK 3.10.2: `native-price-oracle-2026-09-30.json`.


Production prepaid-provider test, 2026-09-30: `weather.witness@v1` now publishes its actual payout address and runs in fixed-price mode. A separate provider account started at zero, with zero grants and collateral. A real 0.02 USDC EIP-3009 deposit funded it; the buyer then paid 0.002 USDC for the root SKU. The provider bought GAIA weather and air for 0.001 each from that cash-backed prepaid balance, leaving 0.018. This is prepaid internal accounting after a real deposit, not two additional on-chain child transfers or a credit line. The provider's daily cap is 0.02; replenishment is not automatic. The result for Berlin was agreement=true, temperature 14.5°C, humidity 64%, PM2.5 9.9 µg/m³ and US AQI 33, sampled at 2026-09-30T07:01:32Z. Root run `paid_580f85c4a2f4deba7a83bc26140fc558` has job `job_db9c841f8a360f04c891a68b` and both child receipt digests. An RPC 429 after local signing stopped submission; resuming the saved bundle completed the same order. Both this deposit and purchase used the live oracle budget policy. Conservatively accounted cumulative test spending is $0.047149423922618862625 of the $1 limit; the entire deposit is included and child prepaid debits are not counted twice.

Evidence: `witness-prepaid-mainnet-2026-09-30.json` · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


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

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · Evidence: `gas-sponsorship-mainnet-2026-09-30.json`

## Provider result recovery — SDK/Hub 3.12.0

`PROVIDER-OP/1` closes the gap where a provider finishes but its reply does not reach the seller Hub. A compatible provider records the operation ID and a digest of product, capability and input before executing. It commits the result and its signature before returning. Repeating the same operation returns the durable result; a changed request is refused. Concurrent requests do not execute twice. KOVA implements this journal in its existing SQLite database.

The seller explicitly enables compatible products with `AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`. New signed `SELLER-OP/1` offers advertise `provider_recovery: PROVIDER-OP/1`; the original provider URL and public key are pinned in the private operation state. After a lost reply or stale execution claim, the seller reads `GET <invoke_url>/operations/<operation_id>`. It checks the provider's signature, operation ID, product, capability, exact input digest, and the separately signed result. Paid work is recovered only if the original payment verification was saved. The terminal seller response is immutable, including when an old worker finishes late. Recovery performs no second provider POST and creates no new payment.

KOVA invoke and status endpoints require the same private Hub-to-provider token. Configure matching `AIMARKET_CAPABILITY_TOKEN` and `KOVA_CAPABILITY_TOKEN`, and allow only the operator's provider host through `AIMARKET_INVOKE_HOST_GATEWAY`. Keys and scoped operation tokens are never part of public evidence. Ordinary buyer calls continue through the Hub's payment and authorization checks.

This is cooperative recovery, not an exactly-once claim for arbitrary remote side effects. A provider that crashes between an external side effect and saving its result reports an unknown outcome; it is not re-executed automatically. Such a provider must bind its business transaction to the operation ID, or reconcile the effect before publishing a result. Legacy providers retain manual reconciliation. KOVA's unknown journal entries remain blocked, protecting against duplicated writes.

A previously paid invoice may be redeemed after its expiry when the verified block timestamp is strictly before expiry. Paying after expiry remains invalid; nonce consumption and replay protection stay enforced. Comma-separated explicit RPC overrides now remain an exclusive list rather than becoming one invalid URL. Public pipeline bills omit the internal job grant field.

Tests cover provider restart/replay, concurrent dispatch, changed input, authenticated status, signed result tampering, recovery across two Hubs without another transfer, an unknown side effect, and the invoice expiry boundary.

Production verification, 2026-09-30: LOGOS → KOVA completed for 0.002 USDC with zero buyer gas. After restarting KOVA, the seller recovered its signed result via GET from the persistent provider journal. Response loss was simulated in an isolated copy of the seller operation; production ledgers were untouched. Recovery made no new provider invocation or payment. The recovered Base block remained 51984647. Gateway status without the private token returned 401; an authorized lookup of an unknown operation returned 404. Cumulative conservative test spend: $0.1183241752052936711504319125 of $1. Refunding and broader network/token support remain subsequent stages.

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · Evidence: `provider-recovery-mainnet-2026-09-30.json`


## Seller-approved refunds — SDK/Hub 3.13.0

A confirmed direct Base USDC payment can be returned through `SELLER-REFUND/1`. The buyer requests a refund offer for a terminal pipeline step; the original seller approves it with a local EIP-3009 signature. The sponsor pays gas for the return transfer. Neither party sends a private key to the Hub or needs ETH for this route. Preparing an offer does not move funds or compel the seller to accept a refund.

HTTP uses the original `X-Studio-Run-Token`: `POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` creates or retrieves the signed offer; `POST /studio/paid-runs/{run_id}/refunds/{step_id}` accepts `{"authorization":"0x…"}` and advances the same refund; `GET` on that path reads its status. HTTP 202 means pending. MCP exposes `pipeline_refund_prepare`, `pipeline_refund`, and `pipeline_refund_status`, with the same run ID, scoped access token and step ID. Send only the seller signature, never a wallet key.

The SDK helper `refund_pipeline(state_path=..., step_id=...)` returns the offer without payment. Send only its `offer` object to the seller, not the buyer recovery file. The seller calls `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)` from `aimarket_hub.refund_client`. The approved recipient, original payment, amount cap, token, chain and Hub signature are checked locally. Submit the returned signature using `refund_pipeline(..., authorization=signature)`. Subsequent calls with the same private state file recover the same refund; `RefundPending` retains its identity. Applications must decide whether the refund is owed before signing.

The Hub accepts only the original seller, original buyer and exact full paid amount. It requires a verified original payment and completed or failed pipeline, so an unknown provider outcome must be reconciled first. The refund signature is immutable after submission. Signed transaction bytes are committed before broadcast and share the sponsor's database nonce and budget coordinator. Lost responses and restarts reuse the same transaction. An expired approval can be renewed only before the Hub has signed a transaction; its refund ID and authorization nonce remain unchanged, preventing two transfers with old and renewed approvals.

The original signed bill and result remain immutable. A separate signed `pipeline.refund/1` credit note links the original and refund transaction hashes, amount, token, chain, parties and gas payer. Status reads do not send money. This first refund route supports one full refund per direct Base USDC payment with zero split fee and an available sponsor. Partial refunds, MarketSplitter fee recovery, unilateral debits and arbitrary-token refunds are not implemented. A seller can refuse approval or lack funds; exhausted sponsor capacity keeps the same refund pending. Gas already consumed is not refunded. Free graphs still require no payment source.

Validation covers wrong signers, changed amounts, concurrent state protection, expired approvals, immutable committed transactions, lost responses, SDK/MCP parity and an Anvil purchase plus refund where both buyer and seller need no gas funds. Mainnet verification is reported separately below when completed.


Mainnet verification, 2026-09-30: a temporary operator-owned static SKU delivered its result for 0.001 USDC, then its separate seller wallet approved a full 0.001 USDC refund. This fixture tests real settlement and refund mechanics, not an independent commercial seller. The buyer and seller USDC balances returned to their initial values; buyer ETH and nonce were unchanged. Both transactions were sponsored. A deliberately lost refund response recovered the same credit note; after a Hub restart, both the original result and refund were byte-for-byte identical JSON values. The temporary listing was removed. Cumulative conservative spending is $0.1193241752052936711504319125 of $1, counting the full sponsor funding and the gross purchase despite its refund. No new contracts were deployed.

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · Evidence: `refund-mainnet-2026-09-30.json`


## Additional payment profiles and multiple client hosts — SDK/Hub 3.14.0

The SDK now accepts native USDC on **Base 8453 and Ethereum 1**, with pinned addresses, six decimals and EIP-712 `USD Coin` / `2`. One paid graph still uses one chain and asset; split mixed-asset work into separate orders. The Hub must offer that payment route: accepting a network in the SDK does not move balances between chains or change a seller’s quoted currency. Free graphs are unchanged. Gas sponsorship and seller-approved refunds currently remain direct Base USDC features; an Ethereum order uses buyer-paid gas. `gas_mode="required"` refuses a paid route without a sponsor before signing.

`accepted_assets=[...]` replaces the SDK’s default allowlist. Each entry explicitly supplies `chain_id`, `token_contract`, `decimals`, `eip712_name`, `eip712_version`, `usd_pegged: true`, and `authorization: "EIP-3009"`. This is a buyer-owned policy for an audited dollar token, not a claim that an arbitrary ERC-20 has those properties. The Hub cannot add an asset to it. Decimal amounts are calculated without floating-point rounding. Non-USD assets, ordinary ERC-20 approval-only tokens, other chains and atomic mixed-chain graphs are refused rather than silently converted. CLI: `--accepted-assets approved-assets.json`. The recovery file pins the policy, and resume cannot change it.

For a local Ethereum seller, configure `AIMARKET_X402_CHAIN=ethereum`. Settlement and broadcast use the signed chain ID; `AIMARKET_SETTLE_RPC_1` and `AIMARKET_SETTLE_RPC_8453` select explicit endpoints per chain. A global `AIMARKET_SETTLE_RPC_URL` remains an exclusive fallback, so a Base-only override must not be used to serve Ethereum. Every RPC must report the invoice’s chain ID before receipt verification or broadcast. A custom Hub asset also requires its correct `AIMARKET_X402_ASSET`, `AIMARKET_X402_ASSET_SYMBOL`, decimals, `AIMARKET_X402_EIP712_NAME` and `AIMARKET_X402_EIP712_VERSION`, plus the buyer’s matching allowlist. Do not price non-dollar tokens as dollars.

Ethereum gas uses a fresh ETH/USD feed through two different RPC hostnames, a 25% price margin, bounded transaction gas and the existing $0.05 reserve. Ethereum has no Base L1 fee surcharge. Its pinned Chainlink feed is `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, eight decimals, heartbeat 3600 seconds and maximum age 3900 seconds. Base retains its sequencer check and separate L1 reserve. Wrong chains, stale blocks, stale prices and disagreement above 2% stop payment. Manual price input can only raise the ceiling.

For agents on multiple machines, install the `postgres` extra and configure the same **buyer-owned** `AIMARKET_WALLET_DATABASE_URL` before creating orders. Use a direct PostgreSQL connection or session pooling; transaction-mode PgBouncer cannot preserve session advisory locks. The coordinator serializes each `(chain_id, wallet)` across connections. The database stores the private recovery state, scoped Hub token and exact signed transaction bundle before submission; it never stores a wallet private key. Restrict database access to cooperating buyer agents. The DSN is not saved in the order or sent to the Hub.

To move an unfinished order, copy its private recovery file securely to the next host and call `run_pipeline(resume=True, state_path=...)`. A stale pre-signing copy loads the committed bundle from PostgreSQL, and a completed order is read before any new signing. Different orders cannot take over an unfinished reservation. A terminal failure releases ownership only after all signed nonces are consumed, or authorizations expire and no transaction remains pending. Database failure stops new submission; cached completed results remain readable. Keep the same database and schema on every cooperating host, and never mix independent coordinators or unrelated wallet software for that wallet. Local file coordination remains the default; sponsored buyers do not allocate transaction nonces and need no PostgreSQL.

Validation used a real disposable PostgreSQL with independent client connections, crash recovery, stale recovery files, missing checkpoints and no duplicate signing. A local EVM with chain ID 1 executed an actual SDK EIP-3009 purchase; native price checks are tested separately because that local chain has no Chainlink feed. Ethereum mainnet checks were read-only: both RPC observations agreed, and USDC’s name/version/decimals matched the pinned profile. No Ethereum mainnet purchase is claimed and no additional funds were spent.

[Circle contract registry](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD feed](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · Read-only verification: `ethereum-profile-2026-09-30.json`

Release delivery: the deployed Hub and downloadable client wheel are 3.14.0. PyPI was checked on 2026-09-30 and still reports `aimarket-hub==3.10.3` and `aimarket-agent==2.4.0`. The new publication artifacts are `aimarket-hub==3.14.0` and the separate provider SDK `aimarket-agent==2.5.0`. Publication credentials are not available in this workspace; uploading those packages to PyPI remains an operator action. Installing the pinned Hub wheel below already works without waiting for PyPI. Existing deployed contracts require no redeployment.

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```

---

# Codex: one client operation, two paid subcontractors

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

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

- JSON: `codex-one-call-2026-09-30.json` · Blueprint: `codex-one-call-2026-09-30-blueprint.json`
- [API / SDK](https://modelmarket.dev/clients/pipeline-guide/en)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

Follow-up verification of the external-agent access update (3.9.0): 175 focused tests and four local Anvil payment tests passed. A clean client installation completed a free SDK graph in two Hub requests. MCP prepare/invoke/status completed another free graph. The original paid order was recovered with two GET requests (manifest and root status), without a wallet key or RPC. Hub receipt verification ran inside the SDK. This follow-up made no new mainnet payments. The wheel is distributed by the Hub, with its SHA-256 in the signed manifest; PyPI publication was not performed.

JSON: `agent-rails-2026-09-30.json`

## Follow-up: independent seller contract, 3.10.1

Codex added SELLER-OP/1 and deployed the Hub with migrations 44–45. The detailed protocol and limitations are in the pipeline guide. Validation: **223 focused tests and 6 local Anvil scenarios** passed, including two separate-hub settlements with a disposable token, one with a lost seller response. The buyer paid exactly 4,000 token units once in each independent-seller scenario; the seller owned and consumed the invoice. These are local-chain integration tests, not new mainnet purchases.

Production checks verified signed discovery, the released wheel and all five guides, a free MCP chain, a free SDK chain with two primary requests, and recovery of the original paid order using GET only. No additional mainnet payment was sent from the test wallet. The local weather.witness listing has no supported direct payout route: seller preparation now correctly returns 409/settlement_route_unsupported rather than 500, before execution or payment. This does not change its existing credit-backed SUB/1 contract. No independent production peer was upgraded or purchased in this test; that path was verified with two controlled hubs on Anvil.

Sanitized verification evidence: `seller-operations-2026-09-30.json`. No private keys, operation tokens or signed transaction bundles are published.

### codex-one-call-2026-09-30-blueprint.json

```json
{
  "nodes": [
    {
      "id": "weather",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.weather.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "input": {
        "city": "Berlin"
      }
    },
    {
      "id": "air",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.air.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "depends_on": [
        "weather"
      ],
      "input": {
        "city": "Berlin"
      }
    }
  ]
}
```

### agent-rails-2026-09-30.json

```json
{
  "version": "3.9.0",
  "wheel_sha256": "b5a3ccc3ec10be2a2c4ae01dd052d60216e1834751550ba206f63b2446ae4014",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "mcp_free_run_id": "paid_838b4c9fceefadc04daee59599a8ff2e",
  "mcp_free_job_id": "job_f3dbbfcd48b38769c2bc5959",
  "sdk_free_run_id": "paid_c997741497bb4fad3c0a6c8183cddea1",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true
}
```

### seller-operations-2026-09-30.json

```json
{
  "version": "3.10.1",
  "wheel_sha256": "32dd7e248a05f9c4052d7d3dd71470e6b3d183d73a786c7795f1e7f4b87c8d94",
  "protocol": "SELLER-OP/1",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "older_wheel_preserved": true,
  "mcp_free_run_id": "paid_20e4b10e6eafcb80199cce1b34a759e2",
  "mcp_free_job_id": "job_78bb0fc253938109f00762c1",
  "sdk_free_run_id": "paid_0d1a123a53176be3c66490aef8e35b46",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true,
  "local_tests": {
    "focused": 223,
    "anvil": 6,
    "independent_seller_anvil": 2,
    "mainnet_independent_seller_test": false
  },
  "seller_quote_smoke": {
    "sku": "weather.witness@v1",
    "status": "preflight_refused",
    "reason": "listing has no supported seller payout or token",
    "http_status": 409,
    "invoke_sent": false,
    "payment_sent": false,
    "invalid_token_rejected": true,
    "recursive_pipeline_rejected": true
  },
  "production_migrations": [
    44,
    45
  ]
}
```

### independent-seller-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "buyer_hub": "https://modelmarket.dev",
  "seller_hub": "https://independentai.network/hub",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "run_id": "paid_356c3e6931dc6a7f4b3bd2640881e04b",
  "job_id": "job_b9aebbd2aa412d310b14c91e",
  "operation_id": "op_c6d88ad6d742603073eaa6eab5326d38",
  "source_hub": "https://independentai.network/hub",
  "payment_rail": "independent_seller",
  "pay_to": "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec",
  "tx_hash": "0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919",
  "success": true,
  "status": "completed",
  "final_result": {
    "block_number": 51980340,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "service_usdc": ".002",
  "gas_wei": "603167313432",
  "usd_policy_ceiling": 6000,
  "prior_cost_at_ceiling_usd": "0.016197102150400000",
  "new_cost_at_ceiling_usd": "0.005619003880592000",
  "cumulative_cost_at_ceiling_usd": "0.021816106030992000",
  "approved_total_usd": "1",
  "new_order_limit_usd": ".15",
  "controlled_client_response_loss": true,
  "signed_result_verified": true,
  "http_requests": [
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "modelmarket.dev",
      "path": "/ai-market/v2/invoke",
      "http_status": 200
    },
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    }
  ],
  "operator_note": "Separate production hub, keys, database and seller wallet; both deployments administered by the same user. Not evidence of an independently owned customer."
}
```

### native-price-oracle-2026-09-30.json

```json
{
  "source": "chainlink_base_eth_usd",
  "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
  "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
  "observations": [
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    },
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    }
  ],
  "margin_percent": 25,
  "max_age_s": 1500,
  "manual_floor_usd": null,
  "native_usd_ceiling": "3323.4373758875",
  "checked_at": 1790750864.630485,
  "rpc_providers": [
    "mainnet.base.org",
    "base-rpc.publicnode.com"
  ],
  "new_mainnet_payments": 0,
  "private_key_used": false,
  "client_version": "3.10.2"
}
```

### witness-prepaid-mainnet-2026-09-30.json

```json
{
  "topup": {
    "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
    "amount_usdc": ".02",
    "fee_wei": "500743844349",
    "budget_check": {
      "service_usdc": "0.02",
      "native_fee_bound_wei": "4832812118600",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751427.5852952
      },
      "l1_upper_bound_wei": "12328121186",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.08608637759766899500",
      "checked_at": 1790751427.585309
    },
    "redeem_status": 200,
    "redeem_result": {
      "success": true,
      "status": "credited",
      "nonce": "0x9078baf0077009ef3f0c29a7baea1458ec130c16600df38260e1e71153e763a1",
      "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
      "credited_usd": 0.02,
      "chain": "base",
      "paid_usd": 0.02,
      "idempotent_replay": false,
      "protocol_version": "v2"
    }
  },
  "purchase": {
    "result": {
      "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
      "status": "completed",
      "busy": false,
      "bill_of_materials": {
        "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "funding": "buyer_wallet",
        "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
        "status": "completed",
        "budget_usd": 0.002,
        "total_usd": 0.002,
        "remaining_budget_usd": 0.0,
        "payment_unresolved": [],
        "steps": [
          {
            "id": "witness",
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "source_hub": "local",
            "status": "succeeded",
            "quoted_usd": 0.002,
            "payment_rail": "seller_direct",
            "terms": {
              "amount_units": "2000",
              "amount_usd": 0.002,
              "chain": "base",
              "chain_id": 8453,
              "decimals": 6,
              "eip712_name": "USD Coin",
              "eip712_version": "2",
              "fee_to": "",
              "fee_units": "0",
              "min_confirmations": 1,
              "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "seller_units": "2000",
              "token": "USDC",
              "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
            },
            "success": true,
            "status_code": 200,
            "receipt": {
              "capability_id": "weather.witness@v1",
              "latency_ms": 1738,
              "list_price_usd": 0.002,
              "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
              "price_usd": 0.002,
              "product_id": "weather-witness",
              "signature": {
                "algorithm": "ed25519",
                "pq_algorithm": "ml-dsa-65",
                "pq_public_key": "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",
                "pq_value": "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",
                "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
              },
              "success": true,
              "timestamp": "2026-09-30T07:01:33Z"
            },
            "job": {
              "depth": 1,
              "funded_by": "own",
              "job_id": "job_db9c841f8a360f04c891a68b",
              "node": "node_228186546b7fac0f4d89706a",
              "parent": "node_ba3a877444eda0486258c30b"
            },
            "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
            "payment": {
              "amount_usd": 0.002,
              "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
              "block_number": 51981171,
              "chain": "base",
              "confirmations": 2,
              "fee_units": "0",
              "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
              "paid_units": "2000",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "token": "USDC",
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "verified_at": 1790751691.358382
            },
            "started_at": 1790751691.358526,
            "finished_at": 1790751693.5381346,
            "price_usd": 0.002
          }
        ],
        "created_at": 1790751593.7525403,
        "completed_at": 1790751693.53815,
        "job_id": "job_db9c841f8a360f04c891a68b",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      },
      "next_step": null,
      "final_result": {
        "agreement": {
          "agree": true,
          "location_km": 0.0,
          "max_km": 75.0,
          "max_time_apart_s": 7200,
          "reasons": [],
          "time_apart_s": 0
        },
        "air": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
            "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
          },
          "capability_id": "gaia.air.read@v1",
          "reading": {
            "device_id": "om-aq-01",
            "firmware": "1.0.0",
            "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
            "seq": 184,
            "site": "live-air-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "co2_ppm": "ppm",
              "european_aqi": "EAQI",
              "pm10_ugm3": "ug/m3",
              "pm2_5_ugm3": "ug/m3",
              "us_aqi": "US AQI"
            },
            "values": {
              "european_aqi": 22.0,
              "pm10_ugm3": 12.8,
              "pm2_5_ugm3": 9.9,
              "us_aqi": 33.0
            }
          },
          "resolved": {
            "device_id": "om-aq-01",
            "latitude": 52.52,
            "longitude": 13.41,
            "matched_place": "Berlin",
            "requested": "Berlin"
          }
        },
        "children": [
          {
            "capability_id": "gaia.weather.read@v1",
            "funded_by": "own",
            "node": "node_766d429147ff1048f8f0fc11",
            "price_usd": 0.001,
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
          },
          {
            "capability_id": "gaia.air.read@v1",
            "funded_by": "own",
            "node": "node_db5caa18e04cca2e44466d23",
            "price_usd": 0.001,
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
          }
        ],
        "funding": "fixed-price",
        "job": {
          "depth": 1,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "node": "node_228186546b7fac0f4d89706a"
        },
        "place": {
          "city": "Berlin"
        },
        "weather": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
            "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
          },
          "capability_id": "gaia.weather.read@v1",
          "reading": {
            "device_id": "om-wx-01",
            "firmware": "1.0.0",
            "model": "GAIA-WS1 (Open-Meteo relay)",
            "seq": 231,
            "site": "live-weather-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "humidity_pct": "percent",
              "pressure_hpa": "hPa",
              "temperature_c": "cel",
              "wind_mps": "m/s"
            },
            "values": {
              "humidity_pct": 64.0,
              "pressure_hpa": 1020.3,
              "temperature_c": 14.5,
              "wind_mps": 2.82
            }
          },
          "resolved": {
            "device_id": "om-wx-01",
            "distance_km": 0.0,
            "matched_place": "Berlin",
            "relay_latitude": 52.52,
            "relay_longitude": 13.41,
            "requested": "Berlin"
          }
        },
        "witness": "weather-witness/1"
      },
      "detail": "",
      "success": true,
      "price_usd": 0,
      "product_id": "hephaestus",
      "capability_id": "pipeline.run@v1",
      "result": {
        "status": "completed",
        "final_result": {
          "agreement": {
            "agree": true,
            "location_km": 0.0,
            "max_km": 75.0,
            "max_time_apart_s": 7200,
            "reasons": [],
            "time_apart_s": 0
          },
          "air": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
              "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
            },
            "capability_id": "gaia.air.read@v1",
            "reading": {
              "device_id": "om-aq-01",
              "firmware": "1.0.0",
              "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
              "seq": 184,
              "site": "live-air-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "co2_ppm": "ppm",
                "european_aqi": "EAQI",
                "pm10_ugm3": "ug/m3",
                "pm2_5_ugm3": "ug/m3",
                "us_aqi": "US AQI"
              },
              "values": {
                "european_aqi": 22.0,
                "pm10_ugm3": 12.8,
                "pm2_5_ugm3": 9.9,
                "us_aqi": 33.0
              }
            },
            "resolved": {
              "device_id": "om-aq-01",
              "latitude": 52.52,
              "longitude": 13.41,
              "matched_place": "Berlin",
              "requested": "Berlin"
            }
          },
          "children": [
            {
              "capability_id": "gaia.weather.read@v1",
              "funded_by": "own",
              "node": "node_766d429147ff1048f8f0fc11",
              "price_usd": 0.001,
              "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
            },
            {
              "capability_id": "gaia.air.read@v1",
              "funded_by": "own",
              "node": "node_db5caa18e04cca2e44466d23",
              "price_usd": 0.001,
              "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
            }
          ],
          "funding": "fixed-price",
          "job": {
            "depth": 1,
            "job_id": "job_db9c841f8a360f04c891a68b",
            "node": "node_228186546b7fac0f4d89706a"
          },
          "place": {
            "city": "Berlin"
          },
          "weather": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
              "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
            },
            "capability_id": "gaia.weather.read@v1",
            "reading": {
              "device_id": "om-wx-01",
              "firmware": "1.0.0",
              "model": "GAIA-WS1 (Open-Meteo relay)",
              "seq": 231,
              "site": "live-weather-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "humidity_pct": "percent",
                "pressure_hpa": "hPa",
                "temperature_c": "cel",
                "wind_mps": "m/s"
              },
              "values": {
                "humidity_pct": 64.0,
                "pressure_hpa": 1020.3,
                "temperature_c": 14.5,
                "wind_mps": 2.82
              }
            },
            "resolved": {
              "device_id": "om-wx-01",
              "distance_km": 0.0,
              "matched_place": "Berlin",
              "relay_latitude": 52.52,
              "relay_longitude": 13.41,
              "requested": "Berlin"
            }
          },
          "witness": "weather-witness/1"
        },
        "bill_of_materials": {
          "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
          "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
          "funding": "buyer_wallet",
          "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
          "status": "completed",
          "budget_usd": 0.002,
          "total_usd": 0.002,
          "remaining_budget_usd": 0.0,
          "payment_unresolved": [],
          "steps": [
            {
              "id": "witness",
              "product_id": "weather-witness",
              "capability_id": "weather.witness@v1",
              "source_hub": "local",
              "status": "succeeded",
              "quoted_usd": 0.002,
              "payment_rail": "seller_direct",
              "terms": {
                "amount_units": "2000",
                "amount_usd": 0.002,
                "chain": "base",
                "chain_id": 8453,
                "decimals": 6,
                "eip712_name": "USD Coin",
                "eip712_version": "2",
                "fee_to": "",
                "fee_units": "0",
                "min_confirmations": 1,
                "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "seller_units": "2000",
                "token": "USDC",
                "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
              },
              "success": true,
              "status_code": 200,
              "receipt": {
                "capability_id": "weather.witness@v1",
                "latency_ms": 1738,
                "list_price_usd": 0.002,
                "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
                "price_usd": 0.002,
                "product_id": "weather-witness",
                "signature": {
                  "algorithm": "ed25519",
                  "pq_algorithm": "ml-dsa-65",
                  "pq_public_key": "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",
                  "pq_value": "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",
                  "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
                },
                "success": true,
                "timestamp": "2026-09-30T07:01:33Z"
              },
              "job": {
                "depth": 1,
                "funded_by": "own",
                "job_id": "job_db9c841f8a360f04c891a68b",
                "node": "node_228186546b7fac0f4d89706a",
                "parent": "node_ba3a877444eda0486258c30b"
              },
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "payment": {
                "amount_usd": 0.002,
                "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
                "block_number": 51981171,
                "chain": "base",
                "confirmations": 2,
                "fee_units": "0",
                "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
                "paid_units": "2000",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "token": "USDC",
                "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
                "verified_at": 1790751691.358382
              },
              "started_at": 1790751691.358526,
              "finished_at": 1790751693.5381346,
              "price_usd": 0.002
            }
          ],
          "created_at": 1790751593.7525403,
          "completed_at": 1790751693.53815,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "signature": {
            "algorithm": "ed25519",
            "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
            "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
            "pq_algorithm": "ml-dsa-65",
            "pq_public_key": "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",
            "pq_value": "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"
          }
        }
      },
      "subcontracting": {
        "job_id": "job_db9c841f8a360f04c891a68b",
        "funding": "buyer_wallet",
        "nodes": [
          {
            "node": "node_ba3a877444eda0486258c30b",
            "parent": "",
            "depth": 0,
            "product_id": "hephaestus",
            "capability_id": "pipeline.run@v1",
            "price_usd": 0.0,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-yKlROh9qyPfcrewL0EbuIbu7PLEh4omMZDqPYz4aNbA=",
            "receipt_id": "urn:aimarket:pipeline:paid_580f85c4a2f4deba7a83bc26140fc558"
          },
          {
            "node": "node_228186546b7fac0f4d89706a",
            "parent": "node_ba3a877444eda0486258c30b",
            "depth": 1,
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "price_usd": 0.002,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY=",
            "receipt_id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e"
          },
          {
            "node": "node_db5caa18e04cca2e44466d23",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.air.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY=",
            "receipt_id": "urn:uuid:645e7e42-42fa-4e42-91d6-b84cb2344b67"
          },
          {
            "node": "node_766d429147ff1048f8f0fc11",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.weather.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY=",
            "receipt_id": "urn:uuid:c18abe0c-33aa-4ea7-9a25-97c7f167293f"
          }
        ],
        "budget_usd": 0.002,
        "spent_usd": 0.002,
        "unspent_budget_usd": 0.0
      },
      "protocol_version": "v2",
      "receipt": {
        "kind": "pipeline.run/1",
        "run_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "job_id": "job_db9c841f8a360f04c891a68b",
        "product_id": "hephaestus",
        "capability_id": "pipeline.run@v1",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "success": true,
        "parents": [
          {
            "id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e",
            "digestSRI": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY="
          }
        ],
        "result_digest": "04b959e9264be0c3203b005819cd8ded9e468532e94647122fba0004aa26571a",
        "bill_digest": "7bb9257690299bad9d875484b5f4741c0a39a6a781bab36b647e5d333744fd4e",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "rSfbsQKIdwcJccPjytyKVqcvOZ4Lk1pcQWDm5RnuWIyGA/Y3cCmqNs1I/6kGVQQmRwtj6USCIo+LXip0UgMMCQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      }
    },
    "tx_hashes": {
      "witness": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272"
    },
    "fee_wei": "500681057186",
    "budget_check": {
      "service_usdc": "0.002",
      "native_fee_bound_wei": "4774506722000",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751690.875712
      },
      "l1_upper_bound_wei": "11745067220",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.0678923037121811500",
      "checked_at": 1790751690.875724
    }
  },
  "account_starting_grant_usd": 0,
  "conservative_cumulative_usd": "0.047149423922618862625",
  "cumulative_limit_usd": "1",
  "accounting_note": "Earlier runs retain their historical 6000 USD/ETH ceiling; new gas is valued at the saved oracle price plus 25%. Entire 0.02 USDC deposit is counted; later prepaid child debits are not counted twice.",
  "provider_account_after": {
    "balance_usd": 0.018,
    "spent_usd": 0.002,
    "granted_usd": 0,
    "topped_up_usd": 0.02,
    "collateral_usd": 0
  }
}
```

### gas-sponsorship-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.11.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_38c0a7c6c2fe992186116a2822205d3d",
  "job_id": "job_dc0b37b785a7f358bfb30b23",
  "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516607663289",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1163241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_38c0a7c6c2fe992186116a2822205d3d/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "funding": {
    "sponsor": "0x663E0C31925EAd877fD9414C2e1862fa50b2650b",
    "payer": "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
    "tx_hash": "0x73cff1e1da3242a2f3c77e1f7389fc5ed23f7625634975d7dbef2086bcfcfc78",
    "funding_wei": "20000000000000",
    "funding_fee_wei": "133597605703",
    "budget_check": {
      "service_usdc": "0",
      "native_fee_bound_wei": "6235958489800",
      "native_usd_ceiling": "3336.4504743875",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3336.4504743875",
        "checked_at": 1790756935.732915
      },
      "l1_upper_bound_wei": "26359584898",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.07080596666155396807999750",
      "checked_at": 1790756935.7329228
    },
    "prior_total_usd": "0.047149423922618862625",
    "cumulative_conservative_usd": "0.1143241752052936711504319125",
    "budget_limit_usd": "1",
    "funding_counted_in_full": true
  },
  "local_validation": {
    "focused_regression_passed": 178,
    "mcp_after_static_card_sync_passed": 81,
    "oracle_and_relay_passed": 37,
    "anvil_zero_eth_buyer_passed": 1
  },
  "final_result": {
    "block_number": 51983924,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "steps": [
    {
      "id": "summary",
      "product_id": "prod-logos",
      "capability_id": "logos.federation.summary@v1",
      "source_hub": "https://logos.modelmarket.dev",
      "status": "succeeded",
      "price_usd": 0.0
    },
    {
      "id": "network",
      "product_id": "kova-network",
      "capability_id": "kova.network.status@v1",
      "source_hub": "https://independentai.network/hub",
      "status": "succeeded",
      "price_usd": 0.002,
      "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857"
    }
  ]
}
```

### provider-recovery-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.12.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_7f29b95f0ebf51092a52883053172f93",
  "job_id": "job_4ca838ba5866031111ed1778",
  "tx_hash": "0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516795861906",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1183241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_7f29b95f0ebf51092a52883053172f93/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "final_result": {
    "block_number": 51984647,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "recovery_proof": {
    "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
    "isolated_copy_recovered": true,
    "production_ledgers_modified": false,
    "new_payments": 0,
    "new_provider_invokes": 0,
    "status_reads": [
      {
        "method": "GET",
        "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5"
      }
    ],
    "provider_result": {
      "capability_id": "kova.network.status@v1",
      "input_sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
      "product_id": "kova-network",
      "protocol": "PROVIDER-OP/1",
      "result": {
        "block_number": 51984647,
        "chain": "base",
        "chain_id": 8453,
        "findings": [],
        "score": 100,
        "summary": "Base mainnet is reachable through KOVA.",
        "verdict": "pass"
      },
      "result_signature": "SDpaLWz7Xvwpa4jVM515EFOVv3rtqUUH8skEbfXBShKDEQ8vuvgy6rraGxFNXJr9eOZevFArDr7Z3Hxk36BECQ==",
      "signature": "4i9lfCn+KRuVi2NUW49E2DsnziK2nbFivGD+Ciex8VwFkBVZUFDXVedYIvgCSoU2H4ZaVhf7Rp7WLflOsl1lCA==",
      "status": "completed"
    }
  },
  "scope": "Live provider journal after restart; lost seller response simulated in an isolated database copy. Production ledgers were not altered.",
  "provider_gateway_authenticated": true,
  "local_validation": {
    "recovery_payment_and_peer_tests": 76,
    "recovery_and_pipeline_tests": 36,
    "kova_operations_and_api_tests": 22,
    "kova_bound_signature_followup_tests": 9
  }
}
```

### refund-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.13.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "seller": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
  "operator_owned_fixture": true,
  "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
  "job_id": "job_da32d04e2b39e575684e9d50",
  "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
  "service_usdc": ".001",
  "refunded_usdc": ".001",
  "buyer_gas_wei": "0",
  "transactions": [
    {
      "tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "620782210434"
    },
    {
      "tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "487781767367"
    }
  ],
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "buyer_usdc_balance_restored": true,
  "seller_usdc_balance_restored": true,
  "controlled_refund_reply_loss": true,
  "original_bill_unchanged": true,
  "same_refund_retry": true,
  "credit_note": {
    "amount_units": "1000",
    "amount_usdc": "0.001",
    "buyer_gas_fee_units": "0",
    "chain_id": 8453,
    "from": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
    "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
    "kind": "pipeline.refund/1",
    "original_tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
    "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
    "refund_tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
    "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
    "signature": {
      "algorithm": "ed25519",
      "pq_algorithm": "ml-dsa-65",
      "pq_public_key": "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",
      "pq_value": "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",
      "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
      "value": "uCRKNXnCxZpCl+4d2SitFnEX6PjvYdqq3trKwowCGjPDm7QPKT2SzWzSJJgJ81FI9fekrgy9ti+HIuhSxGcrDA=="
    },
    "step_id": "proof",
    "to": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
    "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
  },
  "final_result": {
    "operator_owned_fixture": true,
    "refund_test": "2026-09-30",
    "result": "delivered"
  },
  "cumulative_conservative_usd": "0.1193241752052936711504319125",
  "gross_purchase_counted_despite_refund": true,
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "same_refund_after_hub_restart": true,
  "original_result_after_hub_restart": true,
  "temporary_listing_removed": true
}
```

### ethereum-profile-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.14.0",
  "chain_id": 1,
  "token_contract": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "token_metadata": {
    "name": "USD Coin",
    "version": "2",
    "decimals": 6
  },
  "native_price": {
    "source": "chainlink_ethereum_eth_usd",
    "feed": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "sequencer_feed": null,
    "observations": [
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      },
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      }
    ],
    "margin_percent": 25,
    "max_age_s": 3900,
    "manual_floor_usd": null,
    "native_usd_ceiling": "3354.3941056125",
    "checked_at": 1790761170.358094
  },
  "read_only": true,
  "new_mainnet_transactions": 0,
  "sources": [
    "https://developers.circle.com/stablecoins/usdc-contract-addresses",
    "https://data.chain.link/feeds/ethereum/mainnet/eth-usd",
    "https://reference-data-directory.vercel.app/feeds-mainnet.json"
  ]
}
```
