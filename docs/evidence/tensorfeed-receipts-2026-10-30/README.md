# TensorFeed AFTA receipts and AIMarket receipts: one verifier, 2026-10-30

TensorFeed answered our letter of 29 October. It said the receipt format and key are public and the verify endpoint is free, so we could map the two without waiting for them. This directory is that mapping. No payment was made. The TensorFeed receipt comes from its advertised free trial (100 calls per IP per day), and the AIMarket receipts come from a free capability.

## What was collected

| File | What it is |
|---|---|
| `tensorfeed/agent-fair-trade.json`, `tensorfeed/tensorfeed-receipt-key.json`, `tensorfeed/agent-fair-trade-schema.json` | TensorFeed's published AFTA manifest, receipt JWK (`kid db1f1dc3dbf62c66`) and schema, 05:2x UTC |
| `tensorfeed/trial-response.json`, `tensorfeed/trial-headers.txt` | `GET /api/premium/news/search?q=receipts` with `X-Agent-Nonce: aimarket-receipt-map-20261030`; HTTP 200, `x-tf-free-trial: 1` |
| `tensorfeed/receipt.json`, `tensorfeed/receipt-tampered.json` | The receipt (`rcpt_3d15dca77d041cc6`, `no_charge_reason: free_trial`), and a copy with `credits_charged` changed to 5 |
| `tensorfeed/verify-online-*.json` | TensorFeed's `POST /api/receipt/verify` (body `{"receipt": …}`): original `valid: true`, tampered `valid: false` |
| `tensorfeed/offline-verify.json` | First offline check, including the npm `afta-protocol` 0.1.1 rule |
| `aimarket/invoke-logos.json` | `POST https://modelmarket.dev/ai-market/v2/invoke`, `logos.federation.summary@v1`, `source_hub` logos, free; HTTP 200 |
| `aimarket/provenance-receipt.json`, `aimarket/provenance-verify.json` | The AWR/2 provenance receipt of that call, and our hub's own verify answer (`valid: true`) |
| `verify_receipts.py`, `verify-report.json` | One offline script that verifies all three receipts with the same Ed25519 primitive |

Re-run: `python3 -I verify_receipts.py` (needs `cryptography`; no network).

## Results

| Check | TensorFeed AFTA v2 | AIMarket protocol receipt | AIMarket provenance (AWR/2) |
|---|---|---|---|
| Signature algorithm | Ed25519 | Ed25519, plus ML-DSA-65 | Ed25519 (`eddsa-jcs-2022`) |
| Signed bytes | Sorted compact JSON of 14 fields | Pipe-joined 7-field string (spec §7.3.3) | JCS of the whole credential + proof config |
| Signature encoding | base64url, no padding | base64 with padding | multibase base58btc |
| Key discovery | JWK at `/.well-known/tensorfeed-receipt-key.json` | `public_key` in the receipt, pinned from the hub's manifest | `did:key` in `verificationMethod` |
| Offline signature check | **valid** | **valid** | **valid** |
| Tamper test | `credits_charged` 0→5 rejected | `success` 1→0 rejected | — |
| Binds the request | yes: `request_hash` = sha256 of `GET path?query`, reproduced | no | yes: `inputDigest`, reproduced (`{}`) |
| Binds the response | yes: `response_hash` = sha256 of body minus `receipt`/`billing`, reproduced | no | `outputDigest` reproduced only as the digest of the whole answer minus `provenance_receipt` — a rule stated nowhere (see finding 3) |
| Client nonce in signature | yes (`agent_nonce`, from `X-Agent-Nonce`) | no; the server picks `nonce` | no; the server picks `nonce` |
| Price / charge | `credits_charged`, `credits_remaining`, `no_charge_reason` | `price_usd` (exact JSON token) | settlement block when captured |
| Online verifier | `POST /api/receipt/verify`, free | `POST /ai-market/v2/receipts/verify`, but only at the hub that signed it; the signer here was LOGOS, a satellite without that route | `GET /ai-market/v2/p/provenance/verify/{id}` |

### Findings

1. **One verifier handles all three.** The primitive is the same everywhere. What differs is the bytes: TensorFeed signs sorted compact JSON of the receipt itself. Our protocol receipt signs a pipe-joined string. Our provenance receipt signs JCS (RFC 8785) of a W3C credential. For the values in these receipts, TensorFeed's `canonicalJSON` and JCS produce the same bytes. They could differ only on number formatting.
2. **TensorFeed's receipt binds more of the exchange than our protocol receipt.** Its `request_hash` and `response_hash` both reproduce from what we sent and received, and its `agent_nonce` echoes our own nonce into the signature. Our seven-field receipt covers price, success and latency, but not what was asked or answered. That is what our provenance receipt is for.
3. **Our provenance receipt's `outputDigest` follows a rule nobody could know.** `inputDigest` reproduces (`sha256-RBNvo1…` = digest of `{}`). `outputDigest` does too, but only as the digest of the *whole answer minus `provenance_receipt`* — found later the same morning by reading `federated_delivery.py`, after a first pass over the `output` object and its subsets had missed it (`aimarket/` re-check). A local call digests `result` instead. The receipt says neither, and the routed rule breaks as soon as anything else is added to the answer after the digest (a mandate summary, a subcontracting block). Fixed the same day: the credential now names what it digested (`outputDigestOf`) and commits to the provider's receipt separately (`gatewayReceiptDigest`); see "After the fix".
4. **TensorFeed's npm package does not verify TensorFeed's current receipts.** `afta-protocol` 0.1.1 (npm, 2026-05-03) `verifyReceiptSignature` returns false for this receipt for two reasons. It requires `canonical_form === "afta-canonical-json-v1"`, while the live receipt says `tensorfeed-canonical-json-v1`. And its core omits `agent_nonce`, which the v2 receipt signs. The site's own rule ("all fields except the six signature fields, sorted keys") verifies, and so does TensorFeed's endpoint. We report this to them as a courtesy.
5. Two latency figures for one call: the protocol receipt says `latency_ms 1373.73`, and the provenance receipt says `latencyMs 9199`. They are measured at different points (provider vs. whole routed call), but neither receipt says which. Noted, not acted on.

## Mapping, field by field

| TensorFeed AFTA v2 | AIMarket protocol receipt | AIMarket AWR/2 |
|---|---|---|
| `id` | `nonce` | `id` (urn:uuid), `credentialSubject.nonce` |
| `endpoint`, `method` | `capability_id`, `product_id` | `work.modelId` |
| `credits_charged` (credits) | `price_usd` | `settlement.amount` |
| `no_charge_reason` | v2 `type: rejection`, `reason`, `refunded` | `work.status` |
| `request_hash` | — | `inputDigest` |
| `response_hash` | — | `outputDigest` |
| `captured_at` (data freshness), `freshness_sla_seconds` | — | — |
| `server_time` | `timestamp` | `validFrom`, `work.completedAt` |
| `agent_nonce` | — | — |
| `key_id` + JWK | `signature.public_key` | `proof.verificationMethod` (did:key) |
| — | `success`, `latency_ms` | `work.status`, `work.latencyMs` |
| — | ML-DSA-65 co-signature | — |

## After the fix (same day)

Both of our defects were fixed and rolled out to all six hubs by 06:37 UTC; details, tests and rollback names are in [ROLLOUT.md](ROLLOUT.md).

- Every delivered answer now carries a `receipt_binding` (spec §7.3.9), signed by the hub that answered. It binds the request input, the answer's output and the buyer's own nonce (`X-Client-Nonce`, or `X-Agent-Nonce` as AFTA clients send it), and it names the receipt by nonce and signer key. The receipt format itself is unchanged, so old verifiers keep working.
- The provenance credential states what it digested (`outputDigestOf`) and commits to the provider's receipt as `gatewayReceiptDigest`.
- `POST /ai-market/v2/receipts/verify` verifies a routed answer's provider receipt against the key pinned for that peer, and checks the binding against the input, answer and nonce sent with it.

`after-fix/report.json`: on apex, lab, hunt, attested and Independent, a routed free call with our nonce passes every check: binding signature, nonce, input/output digests, provider receipt, and the hub's own verification. Where the provenance plugin runs, `outputDigest`, `gatewayReceiptDigest` and `inputDigest` were all recomputed from the answer.

| | TensorFeed AFTA v2 | AIMarket after the fix |
|---|---|---|
| Request bound | `request_hash` (method + path + query) | `receipt_binding.input_sha256` (request body `input`) |
| Response bound | `response_hash` (body minus receipt/billing) | `receipt_binding.output_sha256` (`result` or `output`) |
| Caller nonce signed | `agent_nonce` from `X-Agent-Nonce` | `client_nonce` from `X-Client-Nonce` / `X-Agent-Nonce` |
| Online verifier | `/api/receipt/verify` | `/ai-market/v2/receipts/verify`, incl. peer receipts and bindings |
| Post-quantum co-signature | no | ML-DSA-65 on receipts and bindings where the hub signs hybrid |

*Main, 2026-11-11:* the two saved copies of TensorFeed's public pages (`tensorfeed/afta-page.html`,
`tensorfeed/whitepaper.html`) are kept only on branch `claude/federation-hub-deployers-search-8b9411`
(commit 2de6ce330), so they never reach the public mirror; the originals are at https://tensorfeed.ai.
