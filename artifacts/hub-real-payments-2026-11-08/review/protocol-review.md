Review only: this agent has not loaded the buyer key, prepared a live invoice,
signed a real authorization, broadcast a transaction, or invoked a paid tool.

The selected native seller-direct EIP-3009 rail requires no channel deposit or
token allowance. Escrow-required settings govern channel funding, and remain
unchanged. Exact principal: Factory weather 2,000, Independent KOVA status 2,000,
Attested contradiction scan 9,000 atomic Base-mainnet USDC; total 13,000 ($0.013).
The fixed owned buyer, token, recipients, public classical/PQ pins and synthetic
inputs are in ../targets.json. Per transaction, gas plus 100 times the Base L1
upper bound must be at most 10^13 wei; aggregate at most 3×10^13 wei. All three
transactions must run serially under the buyer lock.

`../run_paid_cycle.py` defaults to read-only public discovery/manifest and chain
preflight. `--execute --hub factory|independent|attested` is an explicit real
financial action; the root agent owns approval/execution. `--sign-preview`
prepares and validates a private signed offer but does not load the buyer key.
Execution may continue that same unexpired unsigned operation, never renew it.
`--resume` checks the saved transaction and recovers the same operation only; it
never signs, broadcasts, changes inputs, or creates another payment.

The journal lives only under the gitignored data/secrets/hub-real-payments-
2026-11-08 directory (0700, files 0600). Creation is exclusive; replacements,
files and parent directory are fsynced. The spendable authorization is saved
before RPC gas estimation. Its principal and worst-case fee envelope are checked
before signing; authorization-only attempts count against aggregate limits.
The signed raw transaction and computed hash are durable before the sole
broadcast. RPC ambiguity stops execution. A saved authorization without a saved
transaction requires manual same-invoice reconciliation; the runner never
automatically replaces it. Private documents and tokens are not public evidence.

The live quote is checked against exact immutable terms and both previously
verified Hub pins. Inputs validate with an offline-only JSON Schema registry.
Server HTTP Date and latest chain timestamp must agree; the controller clock is
used only for labeled log timestamps. Authorization expires no later than the
invoice minus 15 seconds, and initially within 180 seconds of chain time.
Fresh lifetime checks occur after estimation and immediately before broadcast.

Chain proof requires status 1, max(3, signed terms.min_confirmations), matching
block hash/number and paid-before-expiry timestamp, the exact signed transaction,
and exactly one token AuthorizationUsed(payer, invoice_nonce) immediately
followed by Transfer(payer, approved_payee, exact_atomic_price). Additional payer
USDC spend is refused. Actual L1 and execution fees are checked. The same
immutable operation executes once and is replayed once; the returned signed
cached documents must be byte-equivalent under canonical JSON.

The full signed operation binds offer digest, exact input digest, buyer,
transaction, result and inner receipt. The separately verified hybrid work
receipt binds listing, positive exact charged price and successful delivery;
legacy receipt v1 itself has no input/result/transaction fields. The runner does
not attribute those fields to the legacy inner signature. Exact selected
production ledger rows must additionally be checked read-only by the root:
one consumed settle_invoice, one settled x402 payment, one completed seller
operation, and the receipt link. The public result explicitly flags this separate
requirement rather than claiming the client can see the private ledger.

SellerOperations persists its single-winner busy claim before provider dispatch;
same request replays a cached terminal response. A changed wallet/input/tx is
refused. Payment-pending permits the same operation/transaction to resume;
reconciliation-required never means buy again. Native direct `/invoke` does not
provide equivalent cached Idempotency-Key behavior: spent nonce replay is refused.

There is no automatic monetary refund on this direct rail. Releasing a Hub
invoice/claim leaves the USDC with the seller. Successful exact-price delivery
creates no surplus deposit and needs no refund. A definite failure or uncertain
provider outcome requires reconciliation with the original payment, not a fresh
quote or a claimed cash refund.

Channel alternative review: local escrow V1/V2 MIN_DEPOSIT is 1,000,000 atomic
USDC ($1). V2 depositor exit requests wait SETTLE_WINDOW=one hour; bound Hub can
settle immediately. V1 immediate depositor exit can withdraw uncollected offchain
work. `/channel/close` is irreversible offchain bookkeeping and explicitly
reports refund_executed_usd=0 with a refund obligation. It is not an onchain
refund. Any channel path must collect the exact earned debit first and prove the
actual deployed contract's events before claiming returned money. This runner
does not use that more expensive path.

Relevant source: aimarket_hub/seller_operations.py (offer, durable claim, cached
response), hub_routes/payments.py (onchain verification, atomic claim/release),
settle.py (authorization-adjacent transfer and invoice store),
hub_routes/invoke_parts/local_admission.py (direct payment bypasses channel debit),
channel_ledger/opening.py (close obligations), contracts/evm/src/AIMarketEscrow*.sol.
The Oct31 pay_once.py was reviewed but not run: fixed historical parameters and
full task/request logging made it inappropriate unchanged. Available existing
workspace libraries suffice; no packages were installed.

Stop on changed pins/terms/domain/recipient/input, stale clocks/quote, pending
buyer nonce, inadequate real funds, excessive gas/L1/aggregate envelope,
ambiguous send, missing confirmations/logs, fee mismatch, paid-but-unfinished
operation, malformed/uncharged signatures, unexpected synthetic result, or
ledger mismatch. Preserve the original operation and transaction for all recovery.
