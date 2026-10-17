# AICOM: purchasing external diagnostics

> 🌐 [English](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.md) · [Русский](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.ru.md) · [Español](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.es.md) · [Français](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.fr.md) · [中文](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.zh.md)

AICOM builds products with its own agents. It can now buy a bounded diagnostic service through AIMarket before another internal repair. The external provider returns advice; AICOM's developer edits the code and the existing QA gates decide whether the product can progress.

This feature is **off by default**. Installing it does not enable live purchases, fund an account, register a provider or send source code.

## Decision algorithm

1. Before a developer task, inspect high/critical QA findings that name a source file.
2. Record the finding's identity (file + title) against the latest completed developer task. Replaying a task does not count again. After three observations—initial generation plus two completed internal repairs—the finding is eligible.
3. Skip products with a hard stop, an existing stuck/budget condition, no generated output, or `external_diagnostics_allowed: false`. Existing operator holds and repair limits remain authoritative.
4. Build a small request from **one approved source file**, the finding and acceptance rules. Hash the request, including its source and contract.
5. Verify the Hub's signed well-known document against operator-pinned keys. Search for explicitly approved capabilities, exclude demos, unavailable offers and incompatible required inputs, then prefer the lowest quoted price.
6. Atomically reserve the price, provided the product, daily and completion-reserve limits permit it. Only one unresolved purchase per product and two supplier attempts per finding are allowed. The same supplier is not retried for that finding. Another purchase requires a newly completed internal repair, even after a rejected report.
7. Invoke once, verify the billing receipt and validate the report. A timeout or uncertain payment retains the reservation; there is no automatic paid retry.
8. Deliver accepted advice to the internal developer as untrusted evidence. After a successful developer task, record the next QA outcome. Advice never advances a pipeline state or relaxes a gate.

If there is no compatible offer, permission or budget, the ordinary internal repair continues under its existing limits. Accepted advice is not purchased again for the same finding. Before local execution it can be recovered from the journal only when the request fingerprint still matches.

## Enable and configure

Copy [the example](https://github.com/alexar76/aicom/blob/main/config/procurement.example.json) to `<AIFACTORY_DATA_ROOT>/config/procurement.json`. Configure:

| Setting | Meaning / initial value |
|---|---|
| `enabled` | Set to `true` after configuring a tested provider |
| `hub_url` | HTTPS Hub; redirects are not followed |
| `hub_public_key` | Independently verified, pinned base64 Ed25519 key |
| `hub_pq_public_key` | Pinned ML-DSA-65 key for hybrid-signing Hubs; empty for classical-only Hubs |
| `providers` | Approved `product_id` / `capability_id` pairs; up to 10 |
| `share_globs` | Explicitly approved source paths relative to each product's code directory |
| `per_call_usd` | $0.25 ceiling |
| `per_product_usd` | $0.50 total external exposure |
| `per_day_usd` | $2.00 across the worker's shared journal, UTC day |
| `completion_reserve_usd` | $0.50 left for internal completion and QA |

Supply a dedicated funded credits account through `AIFACTORY_PROCUREMENT_API_KEY`. Configure its balance/permissions on the Hub. This version uses credits and does not create or sign a mandate. A mandate-required account will refuse this client. Configure a positive `AIFACTORY_MAX_PIPELINE_COST_USD`; a disabled total guard does **not** allow unlimited purchases.

Configuration is read on each eligible task. Never put an API key in the JSON file. All workers of this company must use the same data root/journal for the daily cap. Separate installations have separate caps.

The first version supports offers executed by the configured Hub (`source_hub: local`), including external endpoints that the Hub executes. It does not route federated offers or give providers onward spending allowances.

Search must explicitly return `credits_eligible: true`. Wallet sellers requiring direct on-chain payment are excluded. Older Hubs without this field produce no eligible offers; deploy the matching Hub update first. Credits compatibility and the diagnosis contract must both be tested for the chosen provider.

## Source sharing and provider contract

A provider must implement **`aicom.diagnosis/1`**. An arbitrary `code.review@v1` listing is not automatically compatible; test the provider before approving its identity.

The input contains `contract`, `issue`, `fingerprint`, `finding`, `files` and `acceptance`. The `files` object contains one UTF-8 source file, at most 16,000 bytes. Supported extensions: py, ts, tsx, js, jsx, go, rs, java, cs, html, css. Hidden paths, secret directories, symlinks, traversal and common credential patterns are refused. No full repository, credentials, specification or runtime logs are sent.

`share_globs` uses Python fnmatch: `*` can match a slash. Use narrow paths. Credential detection is heuristic; the operator must approve shareable source trees.

QA paths relative to the product, prefixed with `code/<product_id>/` or `data/code/<product_id>/`, and absolute paths within that product's code directory are normalized to the same identity. Paths outside that directory are refused.

The Hub's `result` must have this form (example source line: `return 1 / x`):
```json
{
  "contract": "aicom.diagnosis/1",
  "issue": "COPY_FROM_REQUEST",
  "fingerprint": "COPY_FROM_REQUEST",
  "diagnosis": [{
    "file": "app/main.py",
    "line": 2,
    "evidence": "return 1 / x",
    "explanation": "Zero input divides by zero.",
    "suggested_check": "Test divide(0) against the required error contract."
  }]
}
```

The response must echo the request identifiers and provide 1–5 findings. Each citation must point to an exact non-empty fragment on the stated line of a supplied file. Explanation and suggested check are required and limited to 2,000 characters each. The factory rejects stale source versions. Suggestions are never executed as shell commands.

Acceptance means structurally valid, source-grounded advice—not proof that the diagnosis is correct. The developer must check it and normal tests/QA still apply. Billing receipts authenticate billing fields, not diagnosis text. Both Ed25519 and a present/required ML-DSA-65 layer are verified with pinned keys.

## Money, failure and recovery

`state/procurement.sqlite3` persists orders, request fingerprints, reports, reservations and QA outcomes. Execution (`in_flight`, `accepted`, `rejected`, `unresolved`) and payment (`unknown`, `paid`, `not_charged`) are separate.

An accepted or rejected delivery can still be paid. This credits path does **not** promise Pay-on-Verified refunds. HTTP errors, missing/invalid receipts, disconnection and interrupted workers leave the charge unknown. They block further purchases for the product; internal work may continue if its remaining budget permits it.

Inspect and explicitly reconcile after checking the Hub's billing:
```bash
.venv/bin/python scripts/procurement_orders.py list --product PRODUCT_ID
.venv/bin/python scripts/procurement_orders.py reconcile \
  --order PURCHASE_ID --charged-usd 0.10 \
  --evidence "Hub billing reference and reconciliation reason"
```

Amounts shown by `list` are micro-USD: 100,000 = $0.10. Use `--data-root PATH` before the command when operating another installation. Reconciliation records the observed charge and evidence, releases the reservation and never retries the provider or fabricates an accepted report. Use zero only after confirming that nothing was charged.

The product cost guard now includes **observed LLM costs + charged purchases + unresolved reservations**. Purchase reservations are serialized in SQLite, including concurrent products. Outstanding reservations from previous days still consume the daily allowance. The total guard uses observed LLM cost; an already-running LLM request can exceed its remaining estimate. This is not a hard pre-authorized ceiling on all model token usage.

## Verification and limits

Tests use the actual Hub signer and a simulated HTTP transport, with no live payments. They cover executor handoff, signature parity, stale reports, unsafe paths, disabled policies, concurrent reservations, ambiguous payments, restart recovery, reconciliation and unchanged internal QA gates.

The journal records the next QA's pass/fail and remaining finding count. It does not claim causal savings or automatically learn supplier rankings. Automated reconciliation, general code outsourcing, federated purchases, onward subcontracting and long-running job protocols are outside this first version.

Implementation: [policy/contract](https://github.com/alexar76/aicom/blob/main/core/procurement_contract.py), [journal](https://github.com/alexar76/aicom/blob/main/core/procurement_store.py), [orchestration](https://github.com/alexar76/aicom/blob/main/orchestrator/procurement.py), [receipt verification](https://github.com/alexar76/aicom/blob/main/core/procurement_receipt.py).

## Live-call check — 2026-10-11

[Saved evidence](https://github.com/alexar76/aicom/blob/main/docs/evidence/factory-subcontracting-live-2026-10-11.json) covers real HTTPS calls to a disposable Hub and a real `minimax/minimax-m3` call through the factory's configured OpenRouter account. The accepted report was source-bound, its Ed25519 + ML-DSA-65 billing signature verified, the **test** balance moved from $0.50 to $0.40, and replay made no network request. The successful model call reported $0.00033588. No production account or catalogue was modified; this was not a production marketplace payment or a complete product build.

Two earlier runs exposed a provider timeout and an incorrectly shaped report. The first retained its reservation without retry; the second was correctly recorded as paid but rejected. The request now explicitly specifies an array of 1–5 findings. The timed-out model call has no usage receipt, so the total model bill is not reconciled.

The live `modelmarket.dev` preflight returned HTTP 200, but its deployed search lacked `credits_eligible` and no compatible diagnostic provider was found. Production purchasing remains unverified until the Hub update and a contract-compatible provider are deployed.

Repeat the isolated check with [the probe](https://github.com/alexar76/aicom/blob/main/scripts/procurement_live_probe.py):
```bash
.venv/bin/python scripts/procurement_live_probe.py \
  --ssh-host YOUR_FACTORY_SSH_ALIAS --container aicom-app-1 \
  --output /tmp/procurement-live-result.json
```
Each run may bill one real model request; the metadata-based estimate must be at most $0.25. Keys remain in the remote container. The Hub, TLS keys, catalogue and test credits are temporary.

## Production enabled — 2026-10-11

The production factory now buys `aicom.diagnose@v1` from the approved `aicom-diagnostics` service through `https://modelmarket.dev`. This first provider is operator-owned, runs separately from the factory and uses the configured `minimax/minimax-m3` model. Its request-bound Ed25519 response is verified by the Hub; the factory verifies the Hub’s Ed25519 + ML-DSA-65 receipt. Existing Metis calls remain at the architect and methodologist stages, separate from repeated code-defect diagnosis.

Limits: $0.25 per call, $0.50 per product, $2 per UTC day, and $0.50 reserved for internal completion. The existing total pipeline cap remains $40. Only `backend/app/*.py` and `frontend/src/*.tsx` may be shared. The dedicated account received a one-time $2 operator credit grant, with no automatic top-up. One successful production purchase charged $0.10; the verified remaining balance was $1.90. These are operator-issued Hub credits, not evidence of a fiat deposit or revenue from an independent customer.

The production canary used a synthetic defect and a real model-generated report. The successful signed delivery reused the report cached during the preceding signature probe; it did not make another model call. Repeating the accepted factory task made no network request. Five earlier rejected invokes were reconciled against released Hub holds at zero charge. The adapter now handles a whole JSON code fence and the model’s `suggest_check` spelling, while source citations and the public contract remain strictly validated. Forty-five focused tests passed. This does not claim a complete real-product repair.

[Production evidence](https://github.com/alexar76/aicom/blob/main/docs/evidence/procurement-production-2026-10-11/README.md). To stop new purchases, set `enabled: false` in the production `data/config/procurement.json`; no restart is required. Deployment and rollback are saved under `/root/procurement-release-20261011/`. No GitHub push was performed.
