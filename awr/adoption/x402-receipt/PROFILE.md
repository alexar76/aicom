# AWR/2 × x402 — the x402 receipt as a work receipt's settlement binding

**Profile of:** AWR/2 (`awr/SPEC.md` §10.3) and the x402 Offer and Receipt extension
(x402 Foundation, `specs/extensions/extension-offer-and-receipt.md`, v0.6, 2026-02-04)
**Version:** AWR-X402/1 (1.0.0) · **Status:** Draft. Issuer and verifier implemented in the reference hub
(aimarket-hub, `aimarket_hub/x402_offer_receipt.py`: `awr_settlement`, `check_awr_settlement`); no second
implementation yet · **License:** MIT

## 1. What this profile does

x402 settles a request: a signed **offer** states the terms on the 402, a signed **receipt**
states that the server was paid and delivered. AWR/2 states something x402 does not: **what
work was delivered** (model, input digest, output digest) and, at L1/L2, **who checked it**.
The two meet at one field. This profile defines the `settlement` binding (AWR/2 §10.3) that
carries an x402 receipt, so a single AWR `WorkReceipt` answers *what was done*, *for whom*,
*on what terms* and *was it paid*, and every part verifies offline.

It defines no new signature, no new canonicalization and no new transport. Both sides already
use Ed25519, `did:key` and RFC 8785.

## 2. The binding

```json
"settlement": {
  "scheme": "x402-offer-receipt-v1",
  "network": "eip155:8453",
  "resourceUrl": "https://modelmarket.dev/ai-market/v2/invoke",
  "receipt": "<x402 receipt, JWS compact serialization>",
  "offer": "<x402 offer the buyer accepted, JWS compact serialization>",
  "transaction": "0x…"
}
```

| Member | Rule |
|---|---|
| `scheme` | MUST be `x402-offer-receipt-v1` |
| `network`, `resourceUrl` | MUST equal the same members of the receipt's JWS payload |
| `receipt` | REQUIRED. The `signature` string of `extensions["offer-receipt"].info.receipt`, verbatim, `format` = `jws` |
| `offer` | OPTIONAL. The `signature` string of the offer whose terms the buyer paid, verbatim |
| `transaction` | OPTIONAL. The settlement transaction hash, copied from the x402 SettlementResponse. Absent by default for the same privacy reason the x402 receipt omits it (extension §5.2) |

The x402 artefacts are embedded **verbatim** — never re-encoded — because they are signed
over their own bytes and the extension (§9) designs them to be lifted into attestation
formats unchanged. Only JWS-format artefacts are admitted: an EIP-712 receipt recovers a
secp256k1 address, which AWR/2 has no key model for.

## 3. Verification

An AWR/2 verifier that recognises this scheme, in addition to AWR/2 §10.3:

1. Parses `receipt` (and `offer`, if present) as a compact JWS whose header has `alg`
   `EdDSA` and a `kid` that is a `did:key` URL; resolves the key offline from the `did:key`.
2. Verifies the JWS over the JCS payload with the strict Ed25519 rule of AWR/2 §6.
3. Checks the payload `version` is `1`, and that `network` and `resourceUrl` equal the
   binding's.
4. If `offer` is present: verifies it the same way, and checks the offer's `resourceUrl` and
   `network` equal the receipt's and that `validUntil` (when non-zero) is not before the
   receipt's `issuedAt`.
5. **Signer binding.** If the receipt's `kid` key equals the `WorkReceipt`'s `issuer.id`
   key, reports `issuer-bound`: the party that says the work was done is the party that says
   it was paid for. Otherwise reports `issuer-unbound` — still valid, but the verifier has
   not established that the two keys belong to one service.
6. Does **not** contact a chain, the resource server, or any network service (AWR/2 §10.3):
   `transaction`, when present, is reported as an unchecked reference.

Result codes, as warnings or errors under AWR/2 §11:

| Code | Severity | Meaning |
|---|---|---|
| `AWR-X402-001` | error | `receipt` missing, not a JWS, or not `EdDSA` with a `did:key` kid |
| `AWR-X402-002` | error | `receipt` or `offer` signature does not verify |
| `AWR-X402-003` | error | `network` / `resourceUrl` disagree between binding, receipt and offer |
| `AWR-X402-004` | warning | `issuer-unbound`: the receipt's key is not the work receipt's issuer key |
| `AWR-X402-005` | warning | `transaction` present and not checked (always, by design) |

## 4. Signer authorization outside AWR

The x402 extension requires a verifier to establish that the receipt's key may sign for the
`resourceUrl` (§4.5.1) and leaves the mechanism open. The reference hub signs with the key it
publishes as `signer_public_key` in its discovery document, so an online verifier can check
that the `kid`'s key equals the `signer_public_key` served at the `resourceUrl`'s origin under
`/.well-known/agent-marketplace` (draft-artamokhov-dawn-marketplace-discovery) or
`/.well-known/ai-market.json`. That check is outside AWR (it needs the network) and outside
this profile's conformance; it is how a reader gets from "a key signed this" to "the service
signed this".

## 5. What the reference hub does today

- Every 402 carries `extensions["offer-receipt"].info.offers[]` (JWS, EdDSA, `kid` = the hub's
  `did:key`), in the `PAYMENT-REQUIRED` header (x402 v2) and in the body (v1).
- A call paid over x402 directly to the seller and delivered returns the x402
  SettlementResponse in the `PAYMENT-RESPONSE` header and as `x402_settlement` in the body,
  with the receipt in `extensions["offer-receipt"].info.receipt`.
- The same receipt is embedded in the call's AWR `WorkReceipt` as `credentialSubject.settlement`
  (§2): `scheme`, `network`, `resourceUrl` and `receipt`, verbatim. `offer` is not included (the hub
  does not keep the offer it put on the 402), and `transaction` is not included (§2, privacy). For
  any other call the work receipt keeps the settlement it had before (the hub's own ledger hold, or
  none).
- `check_awr_settlement` runs the §3 checks offline and returns the result codes.
- **The hub's own receipts report `AWR-X402-004` (`issuer-unbound`).** The x402 receipt is signed
  with the hub key published as `signer_public_key`; the work receipt is signed by the provenance
  plugin's own key (`AIMARKET_PROVENANCE_KEY_PATH`). The two keys differ, so a verifier cannot tell
  from the document alone that one service signed both. An operator who sets both to one key
  gets `issuer-bound`.
- The AWR reference verifier sees the binding as an ordinary §10.3 settlement: the receipt is valid
  and carries `AWR-L2-001` (present, well-formed and signed; nothing looked up).

Tests: `aimarket-hub/tests/test_x402_offer_receipt.py` (`test_the_work_receipt_settlement_is_the_x402_receipt`,
`test_awr_settlement_checks`, `test_a_work_receipt_with_the_binding_verifies`).
