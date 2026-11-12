# x402 example-replay aggregate

This local pilot provides a versioned aggregate and two synthetic fixtures for the export discussed by YuTao. The fixtures verify exact example equality under public and restricted comparison modes. The production export and review of any attributed figures are pending. [Hub #23 reply](https://github.com/alexar76/aimarket-hub/issues/23#issuecomment-6789700463) · [x402 #2833 reply](https://github.com/x402-foundation/x402/issues/2833#issuecomment-6789705166)

## Run the fixtures

Use Python 3.9+ with `rfc8785==0.1.4` and `jsonschema==4.25.1`. The verifier uses local files and makes no network calls.

```sh
python3 docs/evidence/x402-aggregate-comparison-2026-11-11/verify.py
python3 docs/evidence/x402-aggregate-comparison-2026-11-11/verify.py --validate /path/to/aggregate.json
```

Each fixture wraps an example aggregate, a reference input and synthetic payments. Export only the `aggregate` object. Both fixtures recompute every count, accept reordered keys, detect a one-field mutation and reject a match under a different resource scope. The private fixture also checks the key, window and nonce. The standalone validator checks structure and count constraints. The fixture replay checks the pinned digest or tag against the supplied input.

## Count definitions

The unit is one deduplicated settled payment. Scope a report to one public resource ID, one Base network (`eip155:8453`), one immutable example version and a half-open UTC date window `[fromDate, untilDate)`. Agree on the resource and example IDs with the operator before comparing. For the public mode, record the exact published example URL and revision in the review notes.

| Field | Meaning |
| --- | --- |
| `settledPayments` | All settled payments observed in scope. |
| `externalSettledPayments` | Settled payments whose payer the seller classified as external. The remaining payments can include operator-owned or ownership-unknown payments. |
| `externalPayers` | Distinct external payer identifiers in the seller's local data. |
| `exampleMatches` / `exampleMismatches` | External settled payments with a comparable input that matched or differed. |
| `unclassified` | External settled payments for which no comparable input was available. The three categories sum to `externalSettledPayments`. |
| `exampleMatchedPayers` | Distinct external payer identifiers with at least one matching payment. A payer may have several such payments. |

Treat a real report as a seller assertion. Example equality alone cannot establish payment settlement, delivery, buyer intent or independence of different payers. Keep those sources of evidence separate. `histor payer-audit` can still work offline on records held by their owner. It applies transaction-scoped labels and retains all settlement totals. The aggregate lacks the transaction references that its annotation format requires. [HISTOR payer audit](https://github.com/alexar76/histor/blob/main/docs/payer-audit.md)

## Comparison bytes

The compared input is the parsed JSON request body chosen for the exact example, without headers or transport metadata. Use I-JSON and RFC 8785 (JCS). Preserve array order and string values. Duplicate keys and invalid numeric values fail rather than being silently normalized. Both constructions prefix an ASCII domain string followed by the single byte `00`, then append the UTF-8 JCS encoding of the stated object. [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) · [x402 measurement discussion](https://github.com/x402-foundation/x402/issues/4127)

| Mode | Envelope and output |
| --- | --- |
| `public-jcs-sha256` | Domain `aimarket.x402-example-replay/public/v1`. Canonicalize `{network, resourceId, exampleId, input}` and compute SHA-256. `publicExampleSha256` is the lowercase 64-character hex encoding of the raw digest for the **published example only**. Keeping the window outside this preimage lets the same published example be recognized across reports for the same resource. Candidate hashes stay local. |
| `private-jcs-hmac-sha256` | Domain `aimarket.x402-example-replay/private/v1`. Canonicalize `{scope, exampleId, nonceHex, input}` and compute HMAC-SHA-256 with a 32-byte secret. The reference and candidate in one comparison use the same fresh 16-byte random nonce, represented as lowercase hex in the envelope. Provision the key only to the authorized verifier. Keep the key, nonce and tags within the private comparison; only the mode, example ID and counts enter the aggregate. The fixture values are public test data. |

An unsalted public hash permits equality testing and guessing against its preimage. Use it for inputs already published as examples. Authorized holders of the private HMAC key can still test guesses. HMAC provides integrity under the shared key and does not establish an independently authenticated publisher. These modes concern input equality within an aggregate pilot. Any signed measurement record would require its own signer binding, signature bytes and verification scope.

## Operator review

Share the scope, methodology, aggregate and proposed wording with the operator before publication. Discuss the effect of small counts and overlapping windows, which can reveal activity through differencing. An export carries no payer addresses, raw EIP-712 receipts, transaction-linked request digests or dates for individual payers. The fixtures contain no data from OracleInsight, PriorSeal or another real seller.
