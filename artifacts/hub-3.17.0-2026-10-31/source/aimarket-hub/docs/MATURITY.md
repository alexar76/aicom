# AIMarket Hub — maturity & honest limitations

Reference implementation of [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol).
Strong **foundation**; **early** at federation scale and external adoption.

**Related:** Factory [KI-10](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md#ki-10--hub-federation--micropayments-unproven-at-adoption-scale) · [protocol ROADMAP](https://github.com/alexar76/aimarket-protocol/blob/main/ROADMAP.md)

---

## What is solid

| Area | Status |
|------|--------|
| Protocol v2 spec + schemas | Normative; test vectors in protocol repo |
| Discover → channel → invoke → settle | End-to-end on [modelmarket.dev](https://modelmarket.dev) |
| Signed manifests + receipt verification | Ed25519 hot path |
| Plugin registry | Safety, channels, reputation, provenance, oracle-gateway, … |
| Federation crawler | SSRF-hardened BFS; slash sync hooks (O-4) |
| CI | Slither on contracts; hub unit/integration tests |

---

## Known gaps (critique validated)

### Federation at scale — **unproven**

Crawler + peer trust graph work in **operator deployments**. Almost **no third-party hub mesh**
→ edge cases mostly theoretical:

- Manifest rotation mid-invoke
- Cross-hub slash disagreement
- Stale `.well-known` cache vs live channel state
- Plugin hook ordering under failure

### Micropayments — **demo-grade**

Channels + hub-bound debits are real on testnet/small mainnet demo sums. Not battle-tested at:

- High concurrency invoke/debit under real traffic (tested in-process and with two ledgers on
  one database, see below; never under production load)
- Multi-hub routing with split fees

### Money-path checks (outside review, 2026-10-23)

The review asked six questions to answer before real money. Each has tests; read them for the
exact claim, which is narrower than "proven":

| Question | Where it is tested |
|----------|-------------------|
| A retry after a timeout charges twice? | `test_invoke_idempotency.py` (Idempotency-Key, credits rail; other rails say the key does not apply) |
| Two closes of one channel settle twice? | `test_channel_ledger_races.py` — two ledgers on one database (two hub processes) |
| The process dies between reserve and settlement? | `test_ledger_crash_consistency.py` (a real process killed before the commit), `test_credit_hold_recovery.py`, `test_provider_recovery.py`, `test_verified_settlement_recovery.py` |
| A federated peer forges or reprices the result? | `test_federated_invoke.py` (price ceiling, hostile and negative prices, refusals, fee basis per peer) |
| Authorization at every money step? | `test_channel_authorization.py`, `test_channels.py` (secret on debit, hold, close, refund) |
| Refunds after a partial failure? | `test_pipeline_refunds.py`, `test_federated_invoke.py::test_provider_failure_releases_the_reservation` |

The second row found a real defect. Channel money moved read-then-write under a lock that
covers one process only: with two ledgers on one SQLite file, 240 concurrent debits answered
ok left 120 cents recorded, a close racing a 30-cent debit booked the whole deposit as owed in
59 of 60 trials, and two closes both answered "settled" in 59 of 60. Every channel move is now
one conditional statement (still open, enough balance, hold still held); the same runs give
240 of 240, 0 of 60 and 0 of 60. A single hub process was not affected.

A forged *result* from a peer (wrong content, right price) is not caught by these tests: the
hub can check what a peer charges, not whether its answer is true. Pay-on-Verified
([pay-on-verified.md](pay-on-verified.md)) is the answer to that, and only for calls bought
through it.

### Adoption ≈ 0 externally

Fair critique: without external peers and agents, **real edge cases are unobserved**. The hub is a
**reference + demo**, not a proven multi-operator marketplace.

---

## Recommended use today

| Use case | OK? |
|----------|-----|
| Self-host single hub for your agents | ✅ |
| Oracle + Factory integration demo | ✅ |
| Multi-operator federated marketplace at scale | ❌ until KI-10 drill + external peer |
| Mainnet TVL without KI-2/KI-4 | ❌ |

---

## Path to “production hardened”

1. Federation testnet playbook (2+ peers, documented drill)
2. Negative channel test vectors in `aimarket-protocol`
3. First non-operator peer hub on ecosystem map
4. External audit (KI-2) before large TVL

See [`docs/ecosystem-maturity-review.en.md`](https://github.com/alexar76/aicom/blob/main/docs/ecosystem-maturity-review.en.md).
