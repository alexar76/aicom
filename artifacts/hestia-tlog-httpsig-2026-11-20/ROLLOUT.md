# HESTIA agents `tlog.checkpoint.verify@v1` and `http.signature.verify@v1` — 2026-11-20

Item 5 of the HESTIA capability list: a checkpoint check for any transparency log (C2SP, with witness
cosignatures) and an RFC 9421 HTTP signature check. Both are pure functions with no egress. They are free, and
they run in the WebAssembly sandbox (`sandbox_only`).

## Deploy

`hestia_agents.cli deploy --hearth https://hestia.modelmarket.dev --only tlog-checkpoint --only http-signature`
was run ~21:45Z and both agents are `running`. `cli verify` passed for both, with repeated signatures.

## Live checks (signed answers, about 0.6 s each)

| Agent | Input | Answer |
|---|---|---|
| tlog-checkpoint | HISTOR checkpoint 2,836,615 + 7 witness keys + inclusion proof of label leaf 1,718,605 | `valid`, 7 cosigned, inclusion ok |
| tlog-checkpoint | HISTOR 3,000,827 with consistency from 2,836,615 (HISTOR's proof) | `valid`, consistency ok |
| http-signature | RFC 9421 B.2.3 (rsa-pss-sha512, full coverage) | `valid`, Content-Digest ok |
| http-signature | RFC 9421 B.2.4 (ecdsa-p256-sha256, response) | `valid`, Content-Digest ok |
| http-signature | modelmarket.dev/mcp AID response of 2026-11-19 (ed25519, `;req`) | `valid` |

## Tests

- `tests/test_tlog_checkpoint.py`
  - Data: the Go checksum database checkpoint (sum.golang.org/latest, recorded 2026-11-20), and the HISTOR
    checkpoints and proofs (`tlog_checkpoint_vectors.json`).
  - Rejected as it should be: a forged size, a forged cosignature, a wrong leaf or index, a short or swapped
    consistency proof, a quorum that is not met, and a cosignature dated in the future.
  - Small trees built in the test pass the RFC 9162 example shapes.
- `tests/test_http_signature.py`
  - All six RFC 9421 Appendix B examples (`http_signature_vectors.json`, extracted from rfc9421.txt and unwrapped
    per RFC 8792) give byte-equal signature bases and verify. Each one fails once a single bit of its signature
    is flipped.
  - The RFC's `@query-param` encoding example is reproduced.
  - The real AID response verifies.
  - Signatures made in the test with `cryptography` verify: P-384, rsa-v1_5-sha256 and RSA-PSS.
  - Error cases are covered: an RSA key without `alg`, private key material, `;sf`, a missing key, an alg
    mismatch, a time window problem, `required` components, and a Content-Digest mismatch.
- The full hestia-agents suite: 1011 passed. Two failed:
  - `test_cli` payment-redeem, which also fails on main;
  - the `test_merkle_proof` timing test, which passes when run on its own.

## Rollback

Delete the two tenants on the hearth (owner API), or deploy the previous catalogue without them. Nothing else changed.
