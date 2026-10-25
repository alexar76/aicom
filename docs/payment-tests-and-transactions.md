# Payment tests and transactions

**EN** [English](payment-tests-and-transactions.md) · **RU** [Русский](payment-tests-and-transactions.ru.md) · **ES** [Español](payment-tests-and-transactions.es.md) · **FR** [Français](payment-tests-and-transactions.fr.md) · **ZH** [中文](payment-tests-and-transactions.zh.md)

Recorded verification: **2026-10-23**. This guide describes the checkout, transaction claims,
internal UNI ledger, recovery tests and what their results actually demonstrate.

## 1. Evidence and scope

Initial baseline is retained in this table; the latest verification appears immediately below.

| Verification | Recorded result | What was real / simulated |
| --- | --- | --- |
| Payment recovery suite | **50 passed, zero skipped**: 25 SQLite + 25 PostgreSQL cases | Real stores, signatures, concurrency and child-process exits; synthetic transactions and simulated chain/provider responses |
| Main Factory suite | **5,828 passed**, 60 skipped | The main selection; overlapping payment tests must not be added again to this count |
| Supplementary PostgreSQL run | PostgreSQL **18.3**, temporary cluster, stopped afterwards | Separate local database; no production database was used |

Evidence: [payment JUnit report](../artifacts/quality-audit-2026-10-23/payments-sqlite-postgres.xml),
[verification manifest](../artifacts/quality-audit-2026-10-23/verification.json),
[full quality report](quality-audit-2026-10-23.md).
A green local suite is **not** proof of a newly completed real-money transfer. The separate dated
[deployment record](../artifacts/payment-production-deploy-2026-10-23/deployment-summary.json)
also states that no positive end-to-end payment or chain refund with real funds was executed.
Historical real-chain transactions are documented in the [on-chain journal](onchain-journal.md)
and [paid-invoke case study](case-study-paid-invoke.md); those are dated evidence, not a current availability check.

PostgreSQL parameterization applies to the UNI ledger. Factory commerce and the KOVA/SaaS stores retain their own SQLite databases; this does not claim a PostgreSQL checkout-order backend.

### Follow-up: failure handling and critical coverage

Latest verification: **6,139 passed, 84 subtests; 24 intentional live-probe skips** in the local full suite, with **450 payment/UNI cases and no financial skips**. A separate production run passed **32 tests: 24 live checks and 8 contracts, zero skips**. All **13 named critical financial functions** reached 100% lines/branches, enforced by the coverage gate. Global coverage: **60.8% lines / 50.0% branches**. The dependency audit remains clean.

The final boundary tests add seven scenarios on both store fixtures: blank/wrong-chain hashes, a quote consumed while waiting for the real async lock, legacy quotes without an amount, pinned-transfer retry, an unsupported persisted chain, and an order insert conflict. A real committed competing order produces **409**, creates no extra license and discloses no license key. See [confirmation boundaries](../tests/test_payment_confirmation_boundaries.py) and [latest evidence](quality-audit-2026-10-23.md#braces-resolution). The completion helper has no static branches; its exception cleanup is tested. This is coverage of named critical functions, not every payment integration or production failure mode.

The follow-up adds HTTP-level recovery checks for failures before/after order commit, pending-store writes,
missing/truncated quote keys, unavailable RPC and claim history. A **503** preserves recovery with the same
transaction; an ambiguous commit retains its single-use claim. A `confirmed` flag without a committed
order is never accepted as success. Restore the original quote key from backup rather than replacing it.
Empty/non-object legacy stores and unavailable UNI history fail closed. A corrupt pending-payment file is preserved until restored; RPC credentials are excluded from both public errors and checkout logs. Solana balances must be finite
and nonnegative; raw SPL amounts/decimals are validated. Real Ed25519 tests reject malformed signatures,
small-order keys and proofs for another customer/site/transfer. Refund tests reject unknown, ineligible,
already-broadcast and invalid-amount withdrawals without crediting funds.

See [follow-up results and remaining limits](quality-audit-2026-10-23.md#follow-up).

### Production verification and the 34 original skips

All **34 original skipped cases were exercised** in this verification campaign. Five filesystem cases ran on a temporary case-sensitive volume; three Compose cases now render the real configurations with synthetic interpolation values and without resolving deployment secret files; two stylesheet checks follow current CSS imports and the self-hosted font link; KOVA's placeholder badge now records **59 actually passing tests**. Rendering/configuration errors fail instead of becoming skips.

The 23 original live cases ran on production, plus a new unpaid-invoke guard. SKOPOS public health is checked for privacy; authenticated fleet status is read with the operator key, and an unauthenticated request must return **402**. The SSH runner keeps credentials in memory, binds forwards to loopback and closes them afterwards. No payment channel, transfer, license issuance or LLM work is triggered. The local full suite retains its 24 opt-in live skips; those exact cases passed in the separate production run. Counts overlap and must not be added blindly.

**88 new settlement cases** cover both SQLite and PostgreSQL: signing failures, real database-trigger failures, eight hard child-process exits after receipt insertion, concurrent retries, depleted holds and legacy missing history. Balance, ledger, withdrawal/hold changes and signed receipt now commit together; failure rolls everything back. Receipt retry returns the stored payload; full idempotency keys stay distinct even when their first 128 characters match. Non-object receipt JSON and unknown wallet amounts fail closed. Missing legacy receipts or reserve records fail closed and require reconciliation. The seven added 100% targets are `charge`, `withdraw_to_chain`, `hold`, `spend_hold`, `release_hold`, `_credit` on `UniWalletService`, and `issue_receipt`.

**The UNI fixes are local and were not deployed by this audit.** Production probes validate the running release; they do not establish that these new fixes are deployed. See the [case-by-case skip evidence and results](quality-audit-2026-10-23.md#skip-resolution).

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-live-contracts \
  "$PYTHON" scripts/run_ecosystem_live_tests.py --ssh-host factory-vps \
  --skopos-ssh-host skopos-vps
```

## 2. A checkout transaction, step by step

1. An authenticated customer calls `POST /api/payment/create`. The server takes the catalog price,
   ignores a client-supplied amount and issues a **one-hour quote** bound to the customer, product,
   site, chain, token and recipient. Factory checkout accepts **USDT/USDC**, not ETH/SOL as a USD amount.
2. The customer sends the quoted token on the quoted network. `payment_id` is an internal quote ID;
   `tx_hash` is the blockchain transaction ID. Neither a hash nor a successful HTTP response proves payment.
3. `GET /api/payment/proof/{payment_id}?tx_hash=...` returns the message to sign.
   `POST /api/payment/confirm/{payment_id}` carries `tx_hash` and `payer_signature`. The proof binds
   the transfer to this customer's checkout and site. EVM supports EIP-191 and the EIP-1271 contract-wallet check.
4. The verifier checks the receipt, correct network/token/recipient, transferred amount and confirmations.
   Factory's amount tolerance is **0.1%**; `AIFACTORY_PAYMENT_MIN_CONFIRMATIONS` defaults to **2**, minimum 1.
   Check the actual configuration through `GET /api/payment/chains`; other services have their own rules.
5. The durable transfer-claim registry prevents the same transfer buying through checkout, pilot,
   channel funding, paid invoke or UNI top-up again. EVM hash case and a missing `0x` cannot bypass it;
   Solana signatures remain case-sensitive. A successful checkout creates **one order and one license**.

| Result / state | Meaning and next step |
| --- | --- |
| `pending` | Quote exists; settlement has not completed |
| `pending_confirmation` | Same transaction is waiting for confirmations; retry with that same hash |
| `confirmed` | Order/license created or recovered; preserve the confirmation response and `order_id` |
| `claim_review` metadata | Missing/invalid payer proof, or late/unprovable payment time; preserve the claim for operator review |
| Legacy `confirming` after restart | Restored to a retryable state rather than permanently blocking a paid customer |

Completed quotes leave the pending store: a later status read can return **404**. That is not proof
that the payment was lost; inspect the customer's orders. Retries reconcile an existing committed order.
A catalog-price change or login-key rotation does not rewrite a sealed quote. An expired quote can
recover an on-time transfer at its quoted price; late/unknown payment time requires review.
Back up `checkout_quote.key` together with the persisted quotes; never put its contents in logs or docs.

## 3. Separate payment, credit and refund

- Checkout buys a license. It **does not also credit spendable UNI**. Wallet funding has a separate
  `/api/uni/topup/confirm` door and participates in single-use transfer protection.
- Hub card top-ups verify Stripe's webhook signature and retrieve the stored checkout session;
  event data cannot choose the customer or credited amount. Duplicate/concurrent deliveries credit
  once, unpaid sessions credit nothing, and test-mode money cannot credit a live hub. Tests also
  cover lost-webhook recovery, fees/tax, refunds, disputes and reversals arriving before payment completion.
- In the UNI ledger, `balance_uni` means **unreserved** money; `hold_uni` means reserved money.
  Holding 600 from 1,000 leaves 400 available, not a second deduction to zero. `hold_charge` spends
  the reservation; ordinary `charge` spends the available balance. Ledger snapshots must match the wallet.
- Failed withdrawals use durable `refund_due`; balance, refund ledger entry and terminal status commit
  atomically. Retry, restart or competing workers must refund once. Withdrawal fees are not revenue
  before a successful payout; legacy fees are reversed on refund.
- An unknown/submitted chain transaction must **not** be refunded automatically: reconcile it first,
  or both the chain payout and the internal refund may pay out. The current deployment record says
  the real UNI chain payout adapter is not implemented; a queued request is not proof of broadcast.
- KOVA invoices reject transfers predating the invoice. SaaS issuance binds the invoice/payment to
  one API key. eSIM procurement persists its intent before calling the supplier; an ambiguous timeout
  becomes `procurement_pending` and is reconciled by supplier transaction ID before buying again.

## 4. Regression matrix

| Invariant | Main test source |
| --- | --- |
| Server price, recipient, stablecoin, receipt, amount and confirmation checks | [price control](../tests/test_payment_price_control.py), [security](../tests/test_payment_security.py), [audit regressions](../tests/test_payment_audit_regressions.py) |
| One transfer across doors; payer/site binding; operator review | [single-use transfer tests](../tests/test_payment_transfer_single_use.py) |
| Pending confirmations, retry and customer-order visibility | [pending API tests](../tests/test_payment_confirm_pending_api.py) |
| KOVA → SaaS; sealed quotes; actual `os._exit(9)` before/after license commit; UNI holds/refunds/fees | [SQLite/PostgreSQL recovery tests](../tests/test_payment_chain_recovery.py) |
| eSIM ambiguous supplier outcome, restart and duplicate procurement protection | [store recovery](https://github.com/alexar76/esim-operator-kit/blob/main/store/test/procurement-recovery.test.js), [rails settlement](https://github.com/alexar76/esim-operator-kit/blob/main/rails/test/settlement.test.js) |
| Hub card-payment merchant isolation, signed webhooks, once-only credit and reversals | [secret-scope integration](../tests/test_hub_card_secret_scope.py), [hub card tests](https://github.com/alexar76/aimarket-hub/blob/main/tests/test_card_topup.py) |
| HTTP/storage/RPC failure recovery; corrupt history; sealed quote fields | [Failure integration](../tests/test_payment_failure_recovery.py) |
| Real Ed25519, invalid encodings, contract-check failure; refund eligibility and rollback | [Cryptographic proofs](../tests/test_payment_claim_crypto.py), [refund guards](../tests/test_payment_refund_guards.py) |
| Quote-key backup, corruption, atomic parallel publication | [Durable key tests](../tests/test_payment_quote_key.py) |

## 5. Run locally

Run from the repository root with Python 3.12, root requirements and the local `aimarket-hub` sources
installed in the test environment. The audited default is `.venv-quality`; set `AIFACTORY_TEST_PYTHON`
for another prepared environment. See the [quality report](quality-audit-2026-10-23.md#reproduction) for setup.
The fixtures isolate stores and simulate external payments; do not copy their stub flags into production.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q -ra --timeout=60 \
  tests/test_payment_chain_recovery.py \
  tests/test_payment_failure_recovery.py \
  tests/test_payment_confirmation_boundaries.py \
  tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py \
  tests/test_payment_claim_crypto.py \
  tests/test_payment_quote_key.py \
  tests/test_payment_refund_guards.py \
  tests/test_payment_security.py \
  tests/test_payment_price_control.py \
  tests/test_payment_transfer_single_use.py \
  tests/test_payment_confirm_pending_api.py \
  tests/test_payment_audit_regressions.py
```

Without `PAYMENT_FIX_TEST_PG_URL`, the PostgreSQL cases are **skipped**, not passed.
For the original 50-case matrix and the added failure scenarios, use a disposable local PostgreSQL cluster. The fixture creates/drops schemas:
**never point it at a production database**. The following block requires PostgreSQL tools on `PATH`
and a free local port 55487; its subshell stops the cluster even on test failure.

```bash
(
  set -eu
  PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
  payment_pg_dir=$(mktemp -d /tmp/aicom-payment-pg.XXXXXX)
  initdb -D "$payment_pg_dir/db" -U aicom_test \
    --auth-local=trust --auth-host=trust --no-locale --encoding=UTF8
  pg_ctl -D "$payment_pg_dir/db" -l "$payment_pg_dir/server.log" \
    -o "-h 127.0.0.1 -p 55487 -k $payment_pg_dir" -w start
  trap 'pg_ctl -D "$payment_pg_dir/db" -m fast -w stop' EXIT
  PAYMENT_FIX_TEST_PG_URL=postgresql://aicom_test@127.0.0.1:55487/postgres \
    USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
    "$PYTHON" -m pytest -q -ra --timeout=60 tests/test_payment_chain_recovery.py \
      tests/test_payment_failure_recovery.py tests/test_payment_claim_crypto.py \
      tests/test_payment_refund_guards.py tests/test_payment_quote_key.py \
      tests/test_payment_confirmation_boundaries.py \
      tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py
)
```

Run the separate hub and eSIM scenarios as well. The Node.js cases require Node 20+ and installed dependencies from each package lockfile. Stripe and supplier responses are simulated; these tests do not charge a card or buy an eSIM.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
hub_test_python=$("$PYTHON" -c 'import sys; print(sys.executable)')
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q --timeout=60 tests/test_hub_card_secret_scope.py
(
  cd aimarket-hub
  "$hub_test_python" -m pytest -q tests/test_card_topup.py
)
node --test esim-kit/store/test/procurement-recovery.test.js
node --test esim-kit/rails/test/settlement.test.js
```

A nonzero exit, timeout, collection error or skip does not prove the corresponding scenario passed.
These commands do not broadcast blockchain transactions.

The standard Factory runners require **100% measured lines and branches for all 13 functions listed in the coverage gate**. The CI configurations now provide an isolated PostgreSQL service; the 450-case financial selection also passed against PostgreSQL 16. Local full coverage needs `PAYMENT_FIX_TEST_PG_URL` pointing to a disposable test cluster. Missing or malformed reports and absent branch data fail the gate. The project-wide percentage remains separate.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
PAYMENT_FIX_TEST_PG_URL="${PAYMENT_FIX_TEST_PG_URL:?use a disposable PostgreSQL test cluster}" \
  USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-quality \
  AIFACTORY_PYTEST_HARD_CAP_SEC=1800 \
  "$PYTHON" scripts/run_factory_pytest_ci.py --timeout-method=signal
```

## 6. Reconcile a real transaction

Preserve the network/chain ID, canonical hash, token contract or mint, recipient, raw token amount and
decimals, receipt/block/confirmations, block time, `payment_id`, `order_id`, claim door and ledger/receipt IDs.
Compare them with the issued quote and the authenticated customer; keep private keys, tokens and license
contents out of public evidence. HTTP **400/422** indicates invalid/unverified input, **401/403** an authentication
or ownership/proof issue, **409** a reuse/review conflict and **503** disabled/unavailable verification or storage.
Consult the error detail; an error response never, by itself, justifies asking the buyer to send money again.

An authorized admin can review `/api/payment/admin/claims` and approve through
`/api/payment/admin/claims/{payment_id}/approve`; quote, chain and single-use checks still run.
A software rollback does not reverse an on-chain transfer. Reconcile before refunding or creating a new payment.
Production configuration: [payment enablement](payment-enable-runbook.md), [chain networks](chain-networks.md),
[UNI and LIVE](uni-and-live.md), [hub card top-ups](https://github.com/alexar76/aimarket-hub/blob/main/docs/card-topup.md).
