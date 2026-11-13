# Do AIMarket hub receipts fit Probity's evidence profiles? (2026-11-10)

Asked because Sankalp Gilda (Probity, OWASP Slack) pointed us at `probityai/agent-evidence-vectors`,
`probityai/probity` and `probityai/evidence-starter`. Read at `agent-evidence-vectors` commit
`6dd29800b017c4202831806b60def2721f5f8424` (2026-11-09). Only read: none of their code or packages was run.

## Answer

No. None of their profiles reads our receipt bytes as they are. The purpose is the same, but the bytes differ:

| Their corpus | Their format | Ours | Fits? |
|---|---|---|---|
| `vectors-receipt-signature` | `draft-farley-acta-signed-receipts-03`: Ed25519 over RFC 8785 JSON, issuer key from an external JWKS with `valid_from`/`valid_until`/`revoked_at`, `previousReceiptHash` chain link | receipt canonical v1/v2 (`aimarket-protocol/spec.md` §7.3.3–7.3.4): Ed25519 (optionally hybrid with ML-DSA) over a pipe-joined field string, key pinned from the hub's signed manifest, no validity window, no chain link | no: same idea, different signed bytes |
| Adversarial Execution Evidence, Observed Effect | in-toto Statement in a DSSE envelope | we emit neither | no |
| `vectors-agent-card-receipt` | DSSE + RFC 8785 | — | no |
| `vectors-agent-payment-mandate` | AP2 cart/intent mandate, Verifiable Intent, Stripe SPT | our mandate is the EIP-712 `DebitAuthorization` (§6.2) | no |
| `vectors-agent-audit-record` (`draft-gilda-audit-agent-audit-record-00`, Sankalp's own Internet-Draft) | `consumption` block for a paid MCP tool call over x402: payee as SHA-256 of its CAIP-10 id, CAIP-19 asset, settled terms read from the chain transaction, `upto` permits | our paid calls settle over x402 in USDC on Base; the facts the block needs (payee, asset, amount, transaction) exist in our settlement, but we write no record in that shape | closest in subject, not in format |

Their `observed-invocation-binding-candidate` binds a call by SHA-256 over the RFC 8785 bytes of
`{"method","params"}` from the JSON-RPC request. Our `receipt_binding` (§7.3.9, `aimarket_hub/receipt_binding.py`, on
main since 2026-11-11) binds the same kind of fact differently:

- what it hashes: the invoke request's `input` alone, plus the answer's output member and the buyer's nonce, not the
  JSON-RPC `method` and `params`;
- how it serializes: Python `json.dumps` with sorted keys, compact separators and non-ASCII kept as is. That is close
  to RFC 8785 but not equal to it: numbers differ (`1.0` stays `1.0`, RFC 8785 writes `1`);
- how it is signed: Ed25519 over `receipt_binding:1|<sha256 hex>`, not a DSSE envelope.

So their invocation-binding cases cannot be run against our binding either. Checked against main `ce88217fe`
(2026-11-13).

## How other formats get in

Their `interop/` folder holds readers for other projects' formats (TRACE Acta receipts, AgentAvow signed maps, APS,
AgentID and others). Each pins the producer's public commit and digest and runs the producer's own cases. For us that
would be an "AIMarket receipt v1/v2" reader fed from our normative vectors (`aimarket-protocol/test-vectors/`,
including `negative/`). The vectors would have to sit at a public commit they can pin, and their cases are discussed in
GitHub issues (the x402 consumption rows came from issue #307). Both are the owner's steps: this workspace does not
write to GitHub.
