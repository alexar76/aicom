# Changelog

## 2.0.1 — 2026-11-03

- **Security:** Ed25519 signatures under a small-order public key, or with a small-order
  `R`, are refused on every backend (AWR/2 section 6.3.1 rule 3). The 2026-10-12 fix
  applied only to the tweetnacl fallback; WebCrypto, the default in Node and current
  browsers, and the built-in BigInt verifier accepted such a signature for every message.
  `test-ed25519-small-order.js` checks both against the vector the SDKs share
  (`aimarket-sdks/test-vectors/ed25519_small_order.json`).

## 2.0.0 — 2026-08-03

First release on npm.
