# Evidence labels for public Base USDC receipts

`histor payer-audit` is a local, deterministic report generator. It keeps payment totals and
behavioural indications separate. It does not identify people, establish buyer intent or block
payments. This command is **unreleased source code**; it is not part of the existing PyPI 0.4.0 build.

We maintain HISTOR and AIMarket. This implementation and the textokit example were prepared with
AI assistance. The example uses public data; the source-reported labels are not independent audits.

## Run from this checkout

From the `histor/` directory, using the project's Python environment:

```sh
python -m histor payer-audit --receipts receipts.json --format json -o payers.json
python -m histor payer-audit --receipts receipts.json --format markdown -o payers.md
```

The reducer is offline and needs no production settings, database, signing keys or wallet. It
accepts a seller ledger with `network: "eip155:8453"`, `seller`, and `sales` containing `payer`,
`transaction`, integer `amountAtomic`, an ISO `at`, optional `service` and boolean `ownWallet`.
This adapter interprets amounts as Base USDC with six decimals; optional chain evidence checks
the actual token, sender, recipient and exact amount. Missing ownership flags remain unknown.
Conflicting ownership claims are rejected, identical receipt rows are deduplicated explicitly,
and one chain event cannot verify two separate receipt rows.

## Collect bounded chain evidence

Save the seller's public ledger first, then run:

```sh
python -m histor.payer_collect --receipts receipts.json \
  --rpc https://base.gateway.tenderly.co --days 14 -o chain.json
python -m histor payer-audit --receipts receipts.json --chain chain.json \
  --annotations annotations.json --format markdown -o payers.md
```

The collector checks chain ID 8453 and reads a fixed historical window ending twelve blocks
behind its initial head. It collects official USDC Transfer logs with the non-own payer
addresses as indexed senders, in ranges of at most 1,000 blocks. It also requests a transaction
receipt for each ledger transaction from those payers. The transaction sender may be a
facilitator: verification uses the USDC event's indexed sender instead.

Limits: 31 days, 100 non-own payers, two workers, a shared request pace, three attempts per read,
25-second request timeout, 16 MiB per RPC response, a 24 MiB retained-evidence budget and a
default total budget of 2,000 requests. The reducer caps each JSON input at 32 MiB.
Only five read RPC methods are allowed. There is no signing, `eth_send*`, `tools/call` or paid
API request. RPC availability and limits can change; choose an endpoint that supports the
requested history and filtering. A limited provider may make the report incomplete.

Failed ranges are explicit. Counts from an incomplete window are observed lower bounds, and
ratios describe only the collected sample. Missing chain coverage is represented as unknown,
not zero activity. A reorganisation changing the end block marks the window incomplete.
The endpoint is operator-chosen and accessed locally, not fetched by the HISTOR web service.

## Source annotations

```json
{
  "schema": "histor.payer-annotations/v1",
  "items": [
    {
      "payer": "0x1111111111111111111111111111111111111111",
      "kind": "known-probe",
      "transactions": ["0x3333333333333333333333333333333333333333333333333333333333333333"],
      "source": "https://example.org/published-research",
      "note": "The operator identifies this exact payment as its research probe."
    }
  ]
}
```

Annotations require full payer addresses, transaction references and HTTPS sources. They are
claims by the cited source; the tool cannot authenticate a publisher from a URL. Keep a
publisher's service-level statement distinct from an independently checked request payload.
Only public payment metadata is needed; do not include credentials or private request bodies.

Labels describe only the supplied receipts and window:

| Label | Basis |
|---|---|
| `operator-owned` | Seller's own-wallet flag. |
| `known-probe` | All the payer's supplied receipt transactions have a sourced known-probe annotation. |
| `reported-monitor` | All those transactions have a sourced known-monitor annotation. |
| `probe-like` | Broad small-payment pattern, or at least two transaction-associated, source-reported example-input matches. |
| `unknown` | None of the above; this does not mean genuine buyer or no demand. |

The broad-pattern rule requires at least **50 transfers to 50 distinct recipients**, at least
**90% singleton recipients**, and at least **90% of transfers at or below 0.01 USDC** in the
collected sample. Self-transfers and zero-value transfers are excluded. Recipients are token
addresses, not verified merchants. This is an explicit **uncalibrated heuristic**, not a fraud
score, a probability or proof that someone is a monitor. Automated use can be genuine use.
The JSON also exposes descriptive signals (broad recipient spread, a majority of small
transfers, a majority of singleton recipients) when the stricter combined label rule does
not pass. Those signals do not upgrade `unknown` to a confirmed purpose.

A known probe on one transaction does not permanently label that wallet. New unannotated
transactions can leave the combined observation unknown. Every payment remains in totals.
Buyer intent stays unknown, even when a behavioural label is present.

## Evidence and exit codes

JSON includes input digests, source annotations, the exact policy, observation boundaries,
per-payer metrics, transaction references and settlement-check outcomes. Chain checks trust
the selected Base RPC; they are not independently verified cryptographic chain proofs.
Ledger timestamps and ownership remain publisher claims. Neither a label nor a checked
transfer confirms delivery of the purchased service.

Reducer: exit **0** for a generated report, including unknown/incomplete evidence; **2** for
invalid input. Collector: **0** for a complete transfer window; **1** for an explicitly
incomplete window saved to disk; **2** for a fatal input/RPC error. Settlement availability is
reported independently from transfer-window completeness. Inputs are never overwritten.

[The textokit five-payer report](../../docs/growth/textokit-five-payers-2026-10-25.md) includes
the actual run and its limitations. No public API route or automatic crawler label is added.
