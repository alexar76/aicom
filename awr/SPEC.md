# AWR — Agent Work Receipt

**Version:** 2.0.0
**Status:** Draft standard, seeking implementation experience
**License:** MIT
**Namespace:** `https://verify.modelmarket.dev/ns/awr/v2`
**This document:** `awr/SPEC.md`

---

## Abstract

AWR defines three signed, self-contained documents that answer three questions about work
performed by an AI system:

| Document | Question |
|---|---|
| `WorkReceipt` | **What happened** — which model, over which input, producing which output, at what cost |
| `VerificationVerdict` | **Was it right, and who says so** — an independent verifier's signed judgement about a `WorkReceipt` |
| `BlameAttestation` | **Which hop failed** — attribution of a failure to one node of a multi-step work chain |

All three are W3C Verifiable Credentials secured with a W3C Data Integrity proof
(`eddsa-jcs-2022`) over an RFC 8785 canonicalization, issued by a `did:key` identifier.
Verification therefore requires **no network access, no registry, no blockchain, and no
issuer-specific software**.

That last part is measured, not asserted. The unmodified `@digitalbazaar/vc` 7.3.0 stack
(`@digitalbazaar/data-integrity` 2.5.0 + `@digitalbazaar/eddsa-jcs-2022-cryptosuite` 1.0.0),
given nothing but a `did:key` resolver in its document loader, verifies every AWR/2 document
in `awr/vectors/valid/` — including the ones carrying non-BMP object keys, decomposed
Unicode, unknown extension properties and a proof array. Two caveats belong in the same
breath: that stack enforces `validFrom`/`validUntil` as *validity*, so it rejects a document
AWR considers valid but stale (§11.3, §16.1); and it does not implement the AWR/1 legacy path
at all, which is correct — those documents are out of its scope.

An earlier draft of this paragraph also claimed a 100-line implementation suffices. Nobody
has written one: in the reference implementation, canonicalization and the proof alone are
455 lines before `did:key`, digests or the reason-code registry. The claim is withdrawn
rather than defended.

AWR carries no economics of its own. Payment, staking and slashing appear only as optional
references (§10.3) so that the format can be adopted by parties who will never settle a
payment.

## Status of this memo

This is not an IETF RFC and not a W3C Recommendation. It follows RFC style for precision and
normatively depends on published standards rather than restating them. Implementation
experience is solicited; see `awr/conformance/README.md` for how to report a result.

## Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**,
**SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** are to be interpreted as described
in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

"Document" means one AWR credential. "Bundle" means a collection of documents (§9).
"Verifier" means software checking an AWR document; "issuer" means software producing one.
Byte strings are shown in lowercase hexadecimal unless stated otherwise.

---

## 1. Introduction

### 1.1 Problem

An AI output travels further than the system that produced it. It is pasted into a ticket,
forwarded to a customer, fed to another agent, entered into evidence. At every hop the same
three facts are lost: what produced it, whether anyone checked it, and who is answerable if
it is wrong.

Existing standards each solve a neighbouring problem and none solves this one:

- **C2PA / Content Credentials** binds provenance to media assets (pixels, audio, video
  frames) and is anchored in file formats. It does not describe a chain of agent invocations
  over structured input, and its manifests are not designed to be produced by a text-only
  inference call.
- **W3C Verifiable Credentials** provides exactly the right envelope, signature suites and
  identifier machinery — but says nothing about what an AI work claim contains.
- **OpenTelemetry GenAI semantic conventions** describe *telemetry*: unsigned, operator-owned,
  meaningful only inside the emitting organisation's observability stack.
- **Evaluation and guardrail tooling** emits judge scores in vendor-specific JSON with no
  signature, no identity for the judge, and no way to compare two judges' claims about the
  same output.
- **HTTP 402-style payment protocols** settle money for a call, but bind the payment to a
  request, not to a judgement about the delivered work.

AWR fills the gap by doing only the missing part: a small, precisely canonicalized claim set
inside a standard VC envelope, plus a verdict document that gives the *judge* an identity and
therefore accountability.

### 1.2 Design principles

1. **Offline-verifiable.** A document plus a conformant verifier is sufficient. No DID
   resolution over the network, no schema fetch, no revocation list, no chain RPC.
2. **Everything signed.** The signature covers the whole document, including its identifier,
   its issuer, and its links to other documents. A field outside the signature is a field an
   intermediary can rewrite (§13.1).
3. **Content-addressed links.** Chain edges reference a parent by digest, not only by
   identifier, so a chain cannot be re-pointed while remaining valid (§8).
4. **Deterministic bytes.** One document has exactly one canonical form. Where JSON permits
   ambiguity that implementations reliably get wrong — floating-point numbers above all — AWR
   forbids the ambiguity rather than specifying a resolution (§4.3).
5. **No economics at the base layer.** Levels of assurance are additive (§10); the free level
   requires nothing but a keypair.
6. **Standards over invention.** Where a published standard exists, AWR profiles it and
   states the profile precisely, rather than defining a parallel mechanism.

### 1.3 Non-goals

AWR does not: prove that a model was not fine-tuned, detect AI-generated content, replace
watermarking, define a reputation algorithm, define a payment or staking mechanism, or
establish who is permitted to issue documents. It makes claims attributable; it does not make
them true.

### 1.4 Relationship to AIMarket

AWR originates in the AIMarket ecosystem and is the format its hub, verification tier and
settlement bridge exchange. It is specified, versioned, tested and licensed independently, has
no dependency on any AIMarket component, and names no AIMarket endpoint normatively. §16
records the mappings.

---

## 2. Terminology

| Term | Definition |
|---|---|
| **Work** | One unit of AI-performed activity that produced an output from an input |
| **Work chain** | A directed acyclic graph of works linked by `parents` edges (§8) |
| **Hop** | One work within a work chain |
| **Issuer** | The party that signs a document; identified by a `did:key` (§5) |
| **Emitter** | Software on the issuing side that *produces* a document. The counterpart of a verifier, which *consumes* one. This specification constrains what an emitter may produce; it places no requirement on how it is packaged |
| **Subject digest** | SHA-256 over the canonical form of a referenced document (§8.1) |
| **Secured document** | A document including its `proof` |
| **Unsecured document** | The same document with `proof` removed |
| **Reason code** | Stable machine-readable identifier for a verification outcome (§11) |
| **Profile** | An assurance level a verifier checks against, L0/L1/L2 (§10) |
| **Bundle** | A JSON container carrying several related documents (§9) |

---

## 3. Document model

### 3.1 Common envelope

Every AWR document is a JSON object and a W3C Verifiable Credential v2.0. The following
requirements apply to all three document types.

```json
{
  "@context": [
    "https://www.w3.org/ns/credentials/v2",
    "https://verify.modelmarket.dev/ns/awr/v2"
  ],
  "id": "urn:uuid:8f14e45f-ea1c-4f38-9b8a-1c2d3e4f5a6b",
  "type": ["VerifiableCredential", "WorkReceipt"],
  "issuer": {
    "id": "did:key:z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw",
    "name": "example-hub"
  },
  "validFrom": "2026-07-31T10:15:30Z",
  "awrVersion": "2.0.0",
  "credentialSubject": { "…": "type-specific, §3.3–3.5" },
  "proof": { "…": "§6" }
}
```

- `@context` **MUST** be an array whose first element is exactly
  `https://www.w3.org/ns/credentials/v2` and which contains
  `https://verify.modelmarket.dev/ns/awr/v2`. Additional context URIs **MAY** follow.
  A verifier **MUST NOT** dereference any context URI (§13.5).
- `id` **MUST** be present and **MUST** be an absolute URI. `urn:uuid:` is **RECOMMENDED**;
  an HTTPS URL that resolves to the document is permitted. `id` is inside the signature, so it
  is a binding statement by the issuer, not a hint.
- `type` **MUST** be an array containing `VerifiableCredential` and exactly one AWR type from
  {`WorkReceipt`, `VerificationVerdict`, `BlameAttestation`}. Further types **MAY** be present.
  The array is a **set**: it **MUST NOT** contain the same value twice, and a duplicate
  **MUST** be reported as `AWR-DOC-005` — counting occurrences rather than distinct values is
  what makes a repeated AWR type a second type. This is stated because implementations
  disagreed: one counted occurrences and rejected `["VerifiableCredential","WorkReceipt","WorkReceipt"]`,
  two de-duplicated silently and accepted it. A reader that takes the first match and a reader
  that counts matches must never reach different conclusions about the same bytes.
- `issuer` **MUST** be an object with `id` (§5). `name` is **OPTIONAL** and carries no trust
  weight. A bare-string `issuer` **MUST** be rejected in AWR/2 (it is legal in VC 2.0, but
  disallowed here so that `name` has one place to live).
- `validFrom` **MUST** be an RFC 3339 `date-time` in UTC with a `Z` offset and second
  precision or finer. `validUntil` is **OPTIONAL**, same format, and **MUST** be later than
  `validFrom` if present.
- `awrVersion` **MUST** be present and **MUST** be `"2.0.0"` for documents conforming to this
  specification. Because it is inside the signed bytes, a document cannot be re-interpreted
  under a different version's rules by an intermediary. Verifiers **MUST** reject a document
  whose `awrVersion` major version they do not implement (`AWR-DOC-009`).
- `credentialSubject` **MUST** be a single object. Arrays of subjects are not used in AWR/2.
- Unknown properties **MAY** appear at any level. A verifier **MUST** ignore them semantically,
  **MUST** include them in canonicalization, and **MUST NOT** strip them when storing or
  forwarding a document — stripping invalidates the signature.

### 3.2 Digest references

Several fields reference another document or artefact by digest. A **digest reference** is:

```json
{ "id": "urn:uuid:…", "digestSRI": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=" }
```

- `digestSRI` **MUST** be a Subresource Integrity string (W3C SRI): `sha256-` followed by the
  standard base64 (with padding, `+/` alphabet) encoding of the 32-byte digest.
- That encoding **MUST** be canonical: exactly 44 characters, one `=` of padding, and the
  four unused low bits of the final character **MUST** be zero — i.e. the last character is
  one of `AEIMQUYcgkosw048`. A verifier **MUST** reject a non-canonical encoding
  (`AWR-RCPT-001` for `inputDigest`/`outputDigest`, `AWR-CHAIN-002` everywhere else) and
  **MUST NOT** normalise it.

  Base64 admits 16 spellings of any 32-byte digest, differing only in bits nothing reads.
  Accepting them would mean one digest has many strings, and a digest reference is used as an
  identity: `AWR-CHAIN-006` detects a parent claimed twice with conflicting digests by
  comparing those strings, and two spellings of the same value would slip past it while two
  spellings of *different* values would be indistinguishable from a re-spelling. Three
  independent implementations of this specification disagreed here — two accepted, one
  rejected — which is what a rule stated only as "base64" is worth.
- The hashed bytes are defined per field; unless stated otherwise they are the UTF-8 canonical
  form (§4) of the referenced **secured** document.
- `sha256` is the only algorithm defined in AWR/2. A verifier encountering another prefix
  **MUST** report `AWR-CHAIN-002` rather than ignoring the reference.
- `id` **MAY** be omitted when the reference is to a non-document artefact (a prompt payload,
  a trace file) that has no identifier of its own.

### 3.3 `WorkReceipt`

```json
"credentialSubject": {
  "work": {
    "modelId": "claude-sonnet-5@anthropic",
    "capability": "urn:example:capability:summarise",
    "startedAt": "2026-07-31T10:15:28Z",
    "completedAt": "2026-07-31T10:15:30Z",
    "latencyMs": 2340,
    "status": "succeeded"
  },
  "inputDigest": "sha256-Yn5Nw…=",
  "outputDigest": "sha256-9pFhK…=",
  "parents": [
    { "id": "urn:uuid:…", "digestSRI": "sha256-…=", "role": "retrieval" }
  ],
  "price": { "currency": "USD", "amount": "0.15" },
  "nonce": "01J9Z8QK4T7YB2N5V6W8XA3C0D",
  "environment": {
    "teeAttestation": { "…": "opaque, §7.3" },
    "zkProof": { "…": "opaque, §7.3" }
  },
  "settlement": { "…": "optional, §10.3" },
  "awrProfile": "L0"
}
```

- `work.modelId` **MUST** be present and non-empty. The form `<model>@<vendor>` is
  **RECOMMENDED** but not constrained; it is an opaque label chosen by the issuer.
- `work.status` **MUST** be one of `succeeded`, `failed`, `refused`, `timeout`, `partial`.
  A receipt for work that did not succeed is a first-class document: an unverifiable failure is
  the case a dispute most often turns on.
- `work.completedAt` **MUST** be present, **MUST** be an RFC 3339 UTC `date-time`, and **MUST
  NOT** be earlier than `work.startedAt` when both are present (`AWR-RCPT-003`).
- `work.latencyMs` **MUST**, if present, be a non-negative integer (§4.3).
- `inputDigest` and `outputDigest` **MUST** be present and **MUST** be SRI strings as in §3.2.
  They are digests of **application payload bytes**, not of AWR documents: the issuer chooses
  the payload serialization and **SHOULD** document it. When the payload is JSON, the canonical
  form of §4 **SHOULD** be used so that an independent party can reproduce the digest.
  A receipt for `status: "failed"` **MUST** still carry an `outputDigest`; the digest of the
  empty byte string is permitted and is exactly the SRI value shown in §3.2.
- `parents` is **OPTIONAL**; when present it **MUST** be an array of digest references (§3.2),
  each **MAY** carry a `role` string (e.g. `retrieval`, `tool`, `subagent`, `input`).
  Chain rules are in §8.
- `price` is **OPTIONAL**. `currency` **MUST** be an ISO 4217 alphabetic code or a
  `urn:`-prefixed URI for non-fiat units. `amount` **MUST** be a decimal string matching
  `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`. It **MUST NOT** be a JSON number (§4.3).
- `nonce` is **OPTIONAL** but **RECOMMENDED**: it is what makes two receipts over identical
  input and output distinguishable, and what a replay check keys on.
- `environment` is **OPTIONAL**; its members are opaque to AWR/2 (§7.3).
- `awrProfile` is **OPTIONAL** and is a non-binding hint about the level the issuer intended
  (§10). A verifier **MUST NOT** grant a level because a document claims it.

### 3.4 `VerificationVerdict`

```json
"credentialSubject": {
  "verifiedWork": { "id": "urn:uuid:…", "digestSRI": "sha256-…=" },
  "verdict": "pass",
  "score": "0.93",
  "method": {
    "id": "urn:example:method:grounded-council-v1",
    "name": "grounded council, 3 jurors",
    "modelIds": ["claude-opus-5@anthropic"]
  },
  "policy": { "threshold": "0.80" },
  "evidence": [ { "kind": "trace", "digestSRI": "sha256-…=" } ],
  "stake": { "…": "optional, §10.3" }
}
```

- `verifiedWork` **MUST** be a digest reference (§3.2) with both `id` and `digestSRI` present,
  digesting the **secured** `WorkReceipt`. Referencing a receipt by identifier alone would let
  the same verdict be re-pointed at a different receipt (§13.2).
- `verdict` **MUST** be one of `pass`, `fail`, `inconclusive`. `inconclusive` is not a
  failure and **MUST NOT** be treated as one; it is the honest outcome when a verifier could
  not reach a judgement, and suppressing it is what turns verifiers into rubber stamps.
- `score` is **OPTIONAL**; when present it **MUST** be a decimal string in the closed unit
  interval `[0,1]` matching `^(0(\.[0-9]+)?|1(\.0+)?)$` (`AWR-VDCT-002`). It **MUST NOT** be a
  JSON number (§4.3).
- `method` **MUST** be present with a non-empty `id`. The identifier is opaque; two verdicts
  are comparable only if they name the same method. `modelIds` is **OPTIONAL**.
- `policy.threshold`, if present, **MUST** be a decimal string in `[0,1]`. A verifier
  **SHOULD** report `AWR-VDCT-006` (warning) when `verdict` and the `score`/`threshold`
  relation disagree — the issuer's stated verdict is authoritative, but the inconsistency is
  evidence in itself.
- `evidence` entries **MUST** each carry `digestSRI`; `kind` is a free-form label. Evidence
  bytes are not carried in the document and need not be available for verification to succeed;
  the digest makes them producible on demand and non-substitutable.
- The verdict's issuer is the verifier's identity. Profile L1 requires it to differ from the
  receipt's issuer (§10.2).

### 3.5 `BlameAttestation`

```json
"credentialSubject": {
  "chain": { "id": "urn:uuid:…", "digestSRI": "sha256-…=" },
  "blamedWork": { "id": "urn:uuid:…", "digestSRI": "sha256-…=" },
  "failureClass": "wrong-output",
  "confidence": "0.90",
  "method": { "id": "urn:example:method:hop-bisect-v1" },
  "evidence": [ { "kind": "replay", "digestSRI": "sha256-…=" } ]
}
```

- `chain` **MUST** be a digest reference to the receipt of the work whose *result* was
  unacceptable — the chain's terminal hop, the observable failure.
- `blamedWork` **MUST** be a digest reference to the receipt of the hop held responsible. It
  **MAY** equal `chain`. It **SHOULD** be reachable from `chain` through `parents` edges; a
  verifier that has the intermediate receipts **MUST** report `AWR-BLAME-001` when it is not.
- `failureClass` **MUST** be one of: `wrong-output`, `malformed-output`, `unavailable`,
  `timeout`, `policy-violation`, `upstream-input`, `cost-overrun`, `unknown`.
  `upstream-input` is how a hop is exonerated: the blame is recorded against it while stating
  that its input was already wrong.
- `confidence` is **OPTIONAL**, decimal string in `[0,1]`, same rule as `score`.
- `method` **MUST** be present with a non-empty `id`.

---

## 4. Canonicalization

### 4.1 Base

The canonical form of an AWR document or fragment is its **RFC 8785 JSON Canonicalization
Scheme (JCS)** serialization, encoded as UTF-8 with no trailing newline.

Implementations **MUST** follow RFC 8785 exactly, and in particular:

1. Object property names are sorted as **arrays of UTF-16 code units compared as unsigned
   integers** (RFC 8785 §3.2.3). Sorting by Unicode code point is *not* equivalent and
   diverges for names containing characters outside the Basic Multilingual Plane.
2. **No Unicode normalization is applied.** RFC 8785 §3.1 requires string data to be preserved
   as-is. An implementation that applies NFC (or any other form) produces a different
   canonical form and therefore a different signature (`AWR-CANON-006`).
3. Strings use the two-character escapes `\b \t \n \f \r \" \\` where defined, and
   **lowercase** `\uXXXX` for the remaining C0 controls; all other characters are emitted
   literally (RFC 8785 §3.2.2.2).
4. Lone surrogates and other data that cannot be represented as valid Unicode **MUST** cause
   the implementation to terminate with an error, not to substitute a replacement character
   (`AWR-CANON-003`).
5. Duplicate object property names **MUST** be rejected (`AWR-CANON-004`). JSON parsers that
   silently keep the last occurrence **MUST** be configured or wrapped to detect this, because
   the parser's choice would otherwise decide which bytes were signed.

### 4.2 No serialization round-trip

A verifier **MUST** canonicalize the document as received, i.e. from the parsed JSON of the
received bytes. A verifier **MUST NOT** re-serialize through any lossy intermediate
representation (a typed struct that drops unknown fields, a map that coerces integers to
floats, a database column). This is the single most common cause of a valid document failing
verification, and it is why §3.1 requires unknown properties to be preserved.

### 4.3 Number restriction

Inside any AWR document that is to be signed:

- JSON numbers **MUST** be integers in the closed range `[-(2^53-1), 2^53-1]`.
- Non-integer JSON numbers **MUST NOT** appear. An issuer **MUST NOT** produce one; a verifier
  **MUST** reject a document containing one with `AWR-CANON-001`.
- Integers outside the permitted range **MUST** be rejected with `AWR-CANON-002`.

The restriction is on the **number literal**, not on the value it denotes. A literal
containing a fraction part or an exponent part is forbidden even when its value is a whole
number: `2340.0`, `2340.00` and `2.34e3` are all `AWR-CANON-001`, and only `2340` is
permitted. The check is therefore **lexical** and **MUST** be applied to the received bytes,
before or during parsing, and **MUST NOT** be delegated to a numeric type that cannot
distinguish the literals — an IEEE-754 double parses `2340` and `2340.0` to the same value,
so an implementation that decides after parsing accepts a document no conformant issuer can
have produced and canonicalizes it to bytes that differ from the ones its issuer signed. This
is not hypothetical: `2340` vs `2340.0` is the exact divergence that split AWR/1 into two
incompatible dialects (§12, Appendix D).

Rationale: RFC 8785 specifies non-integer numbers precisely, but implementations disagree in
practice, and the disagreement is silent — it surfaces as a signature that verifies in one
language and fails in another. Languages also differ on whether a parsed `1` is an integer or
a double, which changes the canonical bytes. AWR therefore removes the class of problem
instead of arbitrating it: every quantity that is not a whole count is carried as a decimal
**string** (`price.amount`, `score`, `confidence`, `policy.threshold`). Comparison of such
values **MUST** be performed as decimal arithmetic, never by parsing to a binary float.

### 4.4 Deterministic profile summary

A conforming implementation's canonicalizer, given the vectors in
`awr/vectors/canonicalization/`, **MUST** produce the exact byte strings recorded there, and
**MUST** fail with the recorded reason code on each negative vector.

---

## 5. Issuer identity and keys

### 5.1 `did:key`

`issuer.id` **MUST** be a `did:key` DID for an Ed25519 public key, in the form
`did:key:z<base58btc(0xed 0x01 || publicKey)>` where:

- `0xed 0x01` is the unsigned-varint multicodec identifier for `ed25519-pub`,
- `publicKey` is the 32-byte raw Ed25519 public key,
- `base58btc` uses the Bitcoin alphabet `123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz`,
- `z` is the multibase prefix for base58btc.

The resulting method-specific identifier is 48 characters and begins `z6Mk`. A verifier
**MUST** derive the public key from the DID by decoding and **MUST** check the multicodec
prefix and the 32-byte length. The two failures are reported distinctly:

- `AWR-KEY-002` — the value is **malformed**: the `did:key:` prefix or the `z` multibase
  prefix is absent, the base58btc payload does not decode, or the key that follows a
  `0xed 0x01` prefix is not exactly 32 bytes.
- `AWR-KEY-004` — the value is **well-formed but names another key type**: the multibase
  decodes and its leading multicodec is a recognised one that is not `ed25519-pub`, for
  instance `0xec 0x01` (`x25519-pub`) or `0xe7 0x01` (`secp256k1-pub`).

`issuer.id` **MUST NOT** be reported as both. The distinction matters operationally: a
`AWR-KEY-002` document is corrupt, while a `AWR-KEY-004` document is a correct DID for a key
AWR/2 does not sign with, which is a version-negotiation problem and not a transmission one.
A multicodec the verifier does not recognise at all is `AWR-KEY-002`.

Other DID methods and HTTPS issuer identifiers are **NOT** supported in AWR/2, because every
one of them makes verification depend on a network lookup. Support may be added in a later
version as an explicit profile.

### 5.2 Optional JWK

`issuer.publicKeyJwk` **MAY** be present as a convenience for JOSE-based tooling. If present
it **MUST** be an RFC 8037 OKP/Ed25519 JWK whose `x` decodes to exactly the same 32 bytes as
the `did:key`. A mismatch **MUST** be reported as `AWR-KEY-003` and **MUST** invalidate the
document: two disagreeing statements of the signing key inside one signed document is a
downgrade attack surface, not a redundancy.

### 5.3 `verificationMethod`

`proof.verificationMethod` **MUST** be `<issuer.id>#<method-specific-id>`, i.e. the DID
followed by `#` and the same multibase string that follows `did:key:`. Any other value
**MUST** be reported as `AWR-PROOF-007`. This is the `did:key` specification's own
verification method identifier, and requiring it means a verifier never has to choose a key.

### 5.4 Key management

Out of scope, with two requirements: an issuer **MUST NOT** use one keypair for both issuing
receipts and issuing verdicts about its own receipts if it intends its verdicts to satisfy
profile L1 (§10.2), and an issuer **SHOULD** publish key rotation as a new `did:key` rather
than re-using an identifier, since AWR has no revocation mechanism (§13.6).

---

## 6. Proof

AWR/2 uses exactly one cryptosuite: **`eddsa-jcs-2022`** from W3C Verifiable Credential Data
Integrity EdDSA Cryptosuites, with W3C Data Integrity as the containing specification.

### 6.1 Proof object

```json
"proof": {
  "@context": [
    "https://www.w3.org/ns/credentials/v2",
    "https://verify.modelmarket.dev/ns/awr/v2"
  ],
  "type": "DataIntegrityProof",
  "cryptosuite": "eddsa-jcs-2022",
  "created": "2026-07-31T10:15:30Z",
  "verificationMethod": "did:key:z6Mk…#z6Mk…",
  "proofPurpose": "assertionMethod",
  "proofValue": "z<base58btc(64-byte signature)>"
}
```

- `@context` **MUST** be present and **MUST** equal the document's `@context`, whenever the
  document has one (`AWR-PROOF-008`). It is a property of the emitted proof, not only of the
  proof configuration that gets hashed; §6.2 step 9 says why, and §6.3 step 4 says what a
  verifier does with a proof that omits it.
- `type` **MUST** be `DataIntegrityProof` (`AWR-PROOF-002`).
- `cryptosuite` **MUST** be `eddsa-jcs-2022` (`AWR-PROOF-003`).
- `proofPurpose` **MUST** be `assertionMethod` (`AWR-PROOF-004`).
- `created` **MUST** be present, RFC 3339 UTC.
- `proofValue` **MUST** be multibase base58btc (`z` prefix) of exactly 64 bytes
  (`AWR-PROOF-005`). Base64, hex, or an unprefixed value **MUST** be rejected — including the
  legacy base64 form of AWR/1 (§12).
- Exactly one `proof` object is defined for AWR/2. An array of proofs **MAY** be present; if
  it is, **at least one** proof **MUST** verify under these rules and every proof present
  **MUST** be either valid or reported. A verifier that accepts an array **MUST** report which
  proof it verified, as the `verifiedProof` member of the result (§11.1) holding the
  zero-based index of that proof. A failing sibling proof **MUST NOT** by itself make the
  document invalid, and it **MUST NOT** be reported through a `reasons` or `warnings` entry:
  the reason codes of §11.2 carry one severity each, and re-using an error code at warning
  severity to describe a sibling makes the result unparseable. Report the sibling in
  `verifiedProof`'s company — an implementation-defined member — or not at all.

### 6.2 Signing

Given an unsecured document `D` and proof options `O` (the proof object of §6.1 without
`proofValue`):

1. If `D` has `@context`, set `O.@context` to the same value. This is
   `eddsa-jcs-2022` Create Proof step 2, not a Data Integrity proof property: Data Integrity
   §2.1 does not list `@context` among the members of a proof at all, the cryptosuite adds it.
2. `canonicalProofConfig = JCS(O)` per §4.
3. `transformedDocument = JCS(D)` per §4, where `D` is the document **with `proof` removed**.
4. `proofConfigHash = SHA-256(canonicalProofConfig)`.
5. `transformedDocumentHash = SHA-256(transformedDocument)`.
6. `hashData = proofConfigHash || transformedDocumentHash` — 64 bytes, **proof config first**.
7. `signature = Ed25519-Sign(privateKey, hashData)` — pure EdDSA per RFC 8032, 64 bytes.
   Signing has no variants; verification does, and §6.3 step 6 pins the one AWR/2 uses.
8. `proofValue = "z" + base58btc(signature)`.
9. The emitted proof object is `O` — **including the `@context` set in step 1** — with
   `proofValue` added. An issuer **MUST** emit `proof.@context` whenever `D` has one, and
   **MUST NOT** emit any other value for it (`AWR-PROOF-008`).

The order in step 6 is normative and is the most frequent interoperability error in
Data Integrity implementations. `awr/vectors/proof/` records `proofConfigHash`,
`transformedDocumentHash` and `hashData` separately so that a failing implementation can be
localised to a single step.

Step 9 is the second such error, and AWR/2 shipped it. An AWR verifier reconstructs the proof
configuration the way step 1 describes — from the document's `@context` — so it never notices
a proof that omits the member. An off-the-shelf `eddsa-jcs-2022` verifier does not: Verify
Proof takes the proof configuration to be a copy of the received proof minus `proofValue`, and
adds nothing to it. A proof that omits `@context` therefore makes that verifier hash a
*different* configuration and report a signature failure over bytes that are perfectly
correct. Measured, on the worked example of Appendix A against `@digitalbazaar/vc` 7.3.0 +
`@digitalbazaar/data-integrity` 2.5.0 + `@digitalbazaar/eddsa-jcs-2022-cryptosuite` 1.0.0:
without `proof.@context` the library computes `hashData` = `d5638620…` and returns
`Invalid signature.`; with it, `79a4102b…`, which is what AWR computes and what the shipped
64 signature bytes were made over, and the library returns verified. Step 9 costs nothing
cryptographically: the signature is unchanged, because step 1 put the same value into the
hashed configuration all along. `awr/vectors/proof/worked-example-secured.json` is that same
document with that same `proofValue`.

**Repairing documents issued before step 9.** Insert the member. The proof still verifies, so
no key is needed. One consequence is not local, though, and an operator repairing a corpus has
to plan for it: §3.2 digest references hash the canonical form of the referenced **secured**
document, and the secured document is what just gained a member. Repairing a document
therefore changes its `digestSRI`, and every document that points at it — a child's
`parents[].digestSRI`, a verdict's `verifiedWork.digestSRI`, a `BlameAttestation`'s `chain` —
now points at bytes that no longer exist and reports `AWR-CHAIN-003`, `AWR-VDCT-005` or
`AWR-BLAME-001`. Those referring documents **MUST** be re-issued by their own issuers, with
their own keys, in reference order: leaves first, then everything that names them. A corpus of
standalone receipts needs no keys at all; a work chain has to be re-signed from the root
outward. Regenerating `awr/vectors/` measured exactly this shape — 62 files whose every
`proofValue` is byte-identical, and 30 that carry a digest reference and were re-signed.
An issuer that cannot re-sign a chain **SHOULD** leave that chain as issued: §6.3 step 4 keeps
it verifiable under AWR, and it is only the third-party W3C path that it stays outside of.

### 6.3 Verification

1. Parse the received bytes. Reject duplicate keys (§4.1).
2. Check the envelope (§3.1) and the type-specific subject (§3.3–3.5).
3. Derive `publicKey` from `issuer.id` (§5.1) and check `verificationMethod` (§5.3) and any
   `publicKeyJwk` (§5.2).
4. Remove `proof` to obtain `D`; build `O` from `proof` minus `proofValue`, carrying
   `@context` per §6.2 step 1 — from the document, whether or not the received proof
   carried the member. If the received proof did carry it and it differs from the
   document's, that is `AWR-PROOF-008` and step 6 is not reached. If it did not carry it,
   the document was issued before §6.2 step 9 and the verifier **MUST NOT** reject it on
   that ground; it is the issuer that fails §6.2 step 9, and the remedy is to insert the
   member, which §6.2 shows costs no re-signing.
5. Recompute `hashData` as in §6.2 steps 2–6.
6. Verify the Ed25519 signature over `hashData` with `publicKey`, under the **strict**
   verification rules of §6.3.1. Failure is `AWR-PROOF-006`.
7. Apply chain checks (§8), semantic checks (§3), and the requested profile (§10).

A verifier **MUST** perform steps 1–6 before evaluating any semantic content of the document,
and **MUST NOT** report any subject field of an unverified document as a fact.

`AWR-PROOF-006` means **the signature was checked and did not verify**. When an earlier step
makes step 6 impossible — the document cannot be canonicalized (step 1, `AWR-CANON-*`), no
public key can be derived (step 3, `AWR-KEY-*` or `AWR-DOC-010`), the proof configuration is
not the one AWR/2 defines or `proofValue` does not decode to 64 bytes (step 4,
`AWR-PROOF-002`…`005`, `007`…`009`) — the verifier **MUST** report that step's code and
**MUST NOT** additionally report `AWR-PROOF-006`. Two implementations of this section
disagreed on precisely these documents, one calling an underivable key a signature failure and
the other not, which made their outputs impossible to compare. The registry has no code for
"the signature could not be checked" because it needs none: the step that prevented the check
has one, and it is more specific.

This does not weaken the outcome. A verifier **MUST NOT** report `valid: true` unless step 6
was performed and succeeded; every condition that prevents step 6 is itself an error of
severity `error`, so such a document is invalid under §11.1 regardless. An implementation that
finds it has skipped step 6 with no error recorded has a bug and **MUST** report
`AWR-PROOF-006` rather than a valid result.

#### 6.3.1 Which RFC 8032 verification rule

"Pure EdDSA per RFC 8032" does not name a verification rule. RFC 8032 defines a family of
them, and two implementations that both follow it to the letter can disagree about the same
64 bytes. §5.1.7 requires the cofactored group equation `[8][S]B = [8]R + [8][k]A'`, and then
says in the same sentence that it is "sufficient, but not required, to instead check
`[S]B = R + [k]A'`" — the cofactorless equation. The two disagree on a small set of
signatures, and the RFC additionally does not require rejecting a public key of small order.
A document format that inherits that openness has no single answer to the only question it
exists to answer.

AWR/2 pins one rule. To verify a 64-byte signature `R‖S` over `hashData` with public key `A`,
a verifier **MUST** apply all four of the following, and **MUST** report `AWR-PROOF-006` if
any one of them fails:

1. **Canonical encodings.** `A` and `R` **MUST** each decode to a curve point by RFC 8032
   §5.1.3: clear the top bit of the 32nd octet to obtain the y-coordinate as a little-endian
   integer; that integer **MUST** be strictly less than p = 2²⁵⁵−19; and the recovered
   x-coordinate **MUST** match the sign bit, so `x = 0` with the sign bit set is a failure.
   A y-coordinate ≥ p **MUST** be rejected, **not** reduced mod p.
2. **Canonical `S`.** `S` **MUST** satisfy 0 ≤ S < L. A signature with a reduced-modulo-L
   twin is not that twin.
3. **No small-order `A` or `R`.** A verifier **MUST** reject the signature if `A` is a point
   of order dividing 8 — the identity and the seven other torsion points — and **MUST**
   likewise reject it if `R` is.
4. **The cofactorless equation.** Verification succeeds only if `[S]B = R + [k]A'`, where
   `k = SHA-512(R‖A‖hashData) mod L`.

Rule 4 is the stricter of RFC 8032's two equations, not a departure from it: multiplying both
sides by 8 gives the cofactored equation, so anything AWR accepts, a cofactored verifier
accepts too. Rule 4 alone is *not* enough, which is why rule 3 is stated separately. Take
`A` = the identity element (`0100…00`), `R` = the encoding of the base point
(`5866…66`), `S` = 1. Then `[S]B = B = R`, and `[k]A' = [k]·identity = identity` for every
possible `k`, so `[S]B = R + [k]A'` holds for **every message**, under both equations, with no
private key in existence. Rule 3 is the only one of the four that stops it.

The cost of getting this wrong is not theoretical for AWR specifically. §5.1 derives
`issuer.id` from `A`, and the eight small-order points encode to eight *distinct* `did:key`
values — the identity gives `did:key:z6MkeXATEjyXENzBXBxgC5EHk2JE5aqd7qMGGtDpLUH1e2Sj`, the
order-2 point (0, −1) gives `did:key:z6MkvQQfodDS9hpfvSLcFA5f2iCB9tBXk3PE5b1P8VVsjtRt`. A
verifier missing rule 3 therefore hands out not just forged receipts but forged *independence*:
§10.2's "verdict issuer differs from receipt issuer" and §10.3's "two valid verdicts from
distinct `issuer.id` values" are both satisfiable by a party holding no key at all, and the
document that comes out the other side is labelled `L2` — "Accountable". The two shipped
implementations of AWR/2 diverged on exactly this: one used a strict verifier and rejected the
forgery, the other used its language's default permissive verify and awarded `L2`.

Nothing legitimate is lost. A signature produced by RFC 8032 §5.1.6 over a key derived by
§5.1.5 satisfies all four rules by construction: `A = [s]B` with `s` a clamped 255-bit scalar
is never small-order, both `A` and `R` come out of the encoder canonical, `S` is computed
mod L, and `R = [r]B` is small-order only if `r ≡ 0 (mod L)`, which the signing procedure
reaches with probability about 2⁻²⁵². The negative case belongs in `awr/vectors/invalid/`,
not in an implementation's judgement.

**Implementation note.** Rules 2, 3 and 4 are what a library calls "strict" verification and
are available off the shelf. Rule 1 usually is not: the widely used Ed25519 libraries load a
32-byte point by masking the top bit and reducing the remainder mod p, so they accept the
non-canonical encoding of a low-y point instead of rejecting it, and RFC 8032 §5.1.3 says to
reject. Only y-coordinates below 19 have a second encoding at all — `y` and `y + p` both have
to fit in 255 bits — and only twelve of those nineteen are on the curve, so no honestly
generated key is affected and this rule buys determinism rather than security. It still has to
be implemented, and it is one comparison: read the 32 bytes little-endian with the top bit
cleared and reject a value ≥ p, before handing them to the library. Doing it in AWR rather
than waiting for the libraries is the point of pinning a rule at all.

### 6.4 Algorithm agility

`cryptosuite` is the only agility point in AWR/2, and this version registers exactly one
value. A future version adding a post-quantum suite will do so by registering a new
`cryptosuite` value and a new `awrVersion` major; verifiers **MUST** reject unknown
cryptosuites rather than skipping the proof.

---

## 7. Optional attestations

### 7.1 Purpose

`environment.teeAttestation` and `environment.zkProof` let a receipt carry hardware- or
proof-based evidence about the execution that produced it.

### 7.2 Signature coverage

Both members are inside `credentialSubject` and therefore inside the AWR signature. Their
*internal* signatures are separate artefacts with separate trust roots.

### 7.3 Opacity

AWR/2 deliberately treats both as **opaque objects**. A verifier:

- **MUST** include them in canonicalization,
- **MUST NOT** claim to have verified them unless it implements the relevant platform's
  attestation verification,
- **MUST** report `AWR-ENV-001` (warning) when an attestation is present and unverified,
- **MUST NOT** report a document as more trustworthy because an unverified attestation is
  present.

An earlier implementation verified a TEE attestation's inner signature with the *receipt
issuer's* key. That check is worse than no check: it proves only that the party making the
claim also wrote it down, while presenting as hardware evidence. Verifying an attestation
requires the platform's certificate chain (AWS Nitro, Intel TDX, AMD SEV, Azure CC), which is
a network- and vendor-dependent operation and therefore outside AWR's offline-verifiable core.
A profile for it may be added; until then `AWR-ENV-001` is the correct and honest outcome.

---

## 8. Work chains

### 8.1 Edges

A `parents` entry (§3.3) is a digest reference whose `digestSRI` digests the UTF-8 canonical
form (§4) of the **secured** parent `WorkReceipt` — including its `proof`. A chain edge is
therefore a commitment to the parent's exact bytes and its signature.

### 8.2 Rules

- Edges form a DAG. A verifier resolving a chain **MUST** detect cycles and report
  `AWR-CHAIN-004`.
- A verifier **MUST** enforce a maximum resolution depth and a maximum node count, both
  configurable, defaulting to **64** and **1024** respectively, reporting `AWR-CHAIN-005`.
  Chain resolution is attacker-influenced work; an unbounded walk is a denial-of-service.
- When the parent document is available, a verifier **MUST** recompute its digest and report
  `AWR-CHAIN-003` on mismatch. When it is not available, the edge is `unresolved`: this is
  **not** an error, and a verifier **MUST** report which edges it resolved so that a caller can
  tell "chain intact" from "chain not checked".
- Two entries with the same `id` and different `digestSRI` **MUST** be reported as
  `AWR-CHAIN-006`: it is a direct statement that one of the two is forged. The comparison is
  over **every edge the resolution observed**, not only over one `parents` array: two receipts
  in the same bundle naming the same parent `id` with different digests is the same claim, and
  the more interesting one, because it means the conflict survived a hop.
- A verifier **MUST NOT** fetch a parent document from the network as part of verification.
  Chain resolution operates over documents the caller supplied (§9).

**Locating a parent.** A verifier resolves an edge against the documents the caller supplied,
**by digest first**: the parent is the supplied document whose canonical digest (§8.1) equals
the edge's `digestSRI`, and only such an edge counts as `resolved`. If no supplied document has
that digest but one carries the edge's `id`, then:

1. the verifier **MUST** report `AWR-CHAIN-003` — a document with that identifier is in hand
   and its bytes are not the ones the child committed to;
2. the edge **MUST** count as `unresolved`, since nothing the child signed has been confirmed;
3. the verifier **MUST** nevertheless continue the walk through that document for the purposes
   of cycle detection, `AWR-CHAIN-006` conflict detection and the §8.2 limits.

Point 3 is normative because without it `AWR-CHAIN-004` is unreachable. An edge commits to the
parent's exact bytes, so a cycle in the digests would be a SHA-256 fixed point: every
constructible cycle runs through at least one edge whose digest does not match, and a resolver
that declines to walk past a failed edge never sees one. Cycle detection therefore keys on
document `id` — the field an attacker controls and the field AWR/1 left unsigned (§13.1) — and
a verifier reports `AWR-CHAIN-003` **and** `AWR-CHAIN-004` for a cyclic bundle rather than
stopping at the first. The alternative reading is what a verifier with no cycle detection at
all looks like from the outside, which is the reason this paragraph exists.

### 8.3 What a chain does and does not prove

A resolved chain proves that each hop's issuer committed to its parent's exact bytes. It does
not prove that the parent's output was actually the child's input — only that the child's
issuer said so. Binding input to output across a hop requires `outputDigest` of the parent to
equal `inputDigest` of the child; a verifier **SHOULD** check this when both receipts are
available and **MUST** report `AWR-CHAIN-007` (warning, not invalidity) when they differ,
because a legitimate hop often transforms its input.

---

## 9. Bundles

Profiles L1 and L2, and chain resolution, require more than one document. A **bundle** is:

```json
{
  "awrBundle": "2.0",
  "documents": [ { "…": "an AWR document" } ]
}
```

- `awrBundle` **MUST** be `"2.0"`.
- `documents` **MUST** be a non-empty array of AWR documents.
- A bundle is **not** signed and carries no claims of its own; it is a transport container.
  Every claim inside it is verified individually.
- A verifier that finds an `awrBundle` value it does not support **MUST** report
  `AWR-BUNDLE-001` and **MUST NOT** process `documents` — it reports `documentType: null`
  and `verifiedProof: null` (§11.1) and verifies nothing inside. `awrBundle` is the only
  statement of the container's schema, so a verifier that reaches into an unknown version
  to pull out things it *assumes* are documents is deciding for itself which bytes to read,
  which is the failure §4.2 and §13.5 forbid elsewhere. This is the same fail-closed gate
  §3.1 puts on `awrVersion` (`AWR-DOC-009`): an unsupported major version is rejected, not
  partially interpreted. Two implementations verified the contents of an `awrBundle: "1.0"`
  container and reported the enclosed receipt's type and proof index; a third refused. All
  three reported `AWR-BUNDLE-001`, so no code set revealed the disagreement.
- Duplicate `id` values with differing content **MUST** be reported as `AWR-BUNDLE-002`.
- **Subject selection runs only when a profile is requested.** Verifying a bundle without a
  profile means verifying every document in it individually; the result is valid if and only
  if every document is valid. A bundle holding one `VerificationVerdict` and no receipt is
  therefore **valid** with no profile and `AWR-BUNDLE-003` at any profile. Three
  implementations produced three answers here — valid, `AWR-BUNDLE-003`, and
  `AWR-BUNDLE-003` — because the old text described selection without saying when it applies.

- When a profile **is** requested, a verifier **MUST** select the subject by this algorithm,
  in order, and **MUST NOT** depend on document order in the array:

  1. If the caller named a subject `id`, use the document with that `id`. If no document has
     it, or more than one does, report `AWR-BUNDLE-003`.
  2. Otherwise let *R* be the `WorkReceipt`s in the bundle. If *R* is empty, report
     `AWR-BUNDLE-003`.
  3. Remove from *R* every receipt whose `id` appears in the `parents` of any receipt in the
     bundle. A parent is a hop someone else's work was built on, never the work being judged.
  4. If exactly one receipt remains, it is the subject. Otherwise report `AWR-BUNDLE-003`.

  Step 3 uses `id` and not `digestSRI` on purpose: a bundle may legitimately carry a parent
  whose bytes differ from what the child committed to — that is `AWR-CHAIN-003`, a finding
  about the chain, and it must not silently change which document the profile was evaluated
  against.

---

## 10. Profiles

A profile is checked by a verifier on request; it is never granted by self-assertion (§3.3).

### 10.1 L0 — Receipt

A single valid `WorkReceipt` (§3.3, §6). Requires only an Ed25519 keypair. No payment, no
verdict, no network, no third party. L0 is the adoption floor and is deliberately free.

### 10.2 L1 — Verified

L0, plus at least one valid `VerificationVerdict` whose `verifiedWork` digest matches the
receipt, and whose `issuer.id` **differs** from the receipt's `issuer.id`.

- No verdict → `AWR-PROFILE-001`.
- Verdict issued by the receipt's own issuer → `AWR-PROFILE-002`. Self-verification is the
  failure mode this level exists to exclude.
- A verdict of `fail` or `inconclusive` still satisfies L1 structurally: L1 asserts *that an
  independent party judged the work*, not that the judgement was favourable. Callers evaluate
  `verdict` themselves.

### 10.3 L2 — Accountable

L1, plus **both**:

1. At least **two** valid verdicts from **distinct** `issuer.id` values, neither equal to the
   receipt's issuer (`AWR-PROFILE-003`).
2. An accountability binding: the receipt carries `settlement`, or each verdict carries
   `stake`, or both (`AWR-PROFILE-004`).

```json
"settlement": {
  "scheme": "escrow-evm-v1",
  "chainId": 8453,
  "contract": "0x0000000000000000000000000000000000000000",
  "holdId": "0x…",
  "amount": { "currency": "USD", "amount": "0.10" }
}
"stake": {
  "scheme": "stake-evm-v1",
  "chainId": 8453,
  "contract": "0x…",
  "amount": { "currency": "USD", "amount": "5.00" },
  "slashingPolicy": { "id": "urn:example:policy:v2", "digestSRI": "sha256-…=" }
}
```

- `scheme` is an opaque label; AWR/2 defines no scheme semantics.
- A verifier **MUST NOT** contact a chain, an RPC endpoint, or any other network service to
  check a binding. It checks that the binding is **present, well-formed and signed**, and
  reports `AWR-L2-001` (warning) stating that on-chain existence was not checked. Anything
  stronger is a settlement-layer concern, and pretending otherwise would put a network
  dependency in the middle of an offline format.
- `slashingPolicy` is a digest reference so that the policy a verifier staked under cannot be
  rewritten after the fact.

### 10.4 Profile reporting

A verifier **MUST** report the highest profile satisfied and the reason codes for each
profile it evaluated and rejected. "Valid" without a profile means L0 only. Three cases that
this left implicit, and that two implementations answered differently, are settled here.

**The profile of an invalid document is `null`.** Every profile in §10 is defined over a
*valid* document — L0 is "a single **valid** `WorkReceipt`" — so a document whose `valid` is
`false` satisfies none of them, whatever its shape. A verifier **MUST** report `profile: null`
whenever `valid` is `false`, including when the only errors are semantic or chain-level and the
signature verified. A caller that reads `profile` alone must never see an assurance level on a
document that failed verification.

**The profile of a document that is not a `WorkReceipt` is `null`.** The levels are levels of
assurance *about a unit of work*; a `VerificationVerdict` or a `BlameAttestation` is valid or
invalid on its own terms and is not a receipt, so it satisfies no level. `profile: null` with
`valid: true` is the correct result for one, and does not mean "below L0".

**`AWR-PROFILE-*` codes are reported only for a profile the caller requested.** A profile "is
checked by a verifier on request" (§10), and the codes for a rejected profile carry severity
`error` (§11.2), so emitting them for a level nobody asked about would make every plain L0
receipt invalid. A verifier **MAY** evaluate higher levels unrequested in order to report the
highest one satisfied, but **MUST NOT** report an `AWR-PROFILE-*` code for a level that was not
requested, and **MUST NOT** re-emit an `error`-severity code at `warning` severity to work
around this — a code has exactly one severity (§11.1).

`AWR-L2-001` is not gated this way. It is a *(warning)* about the document rather than about a
level: a `settlement` or `stake` member is present and its on-chain existence was not checked
(§10.3). A verifier **MUST** report it whenever such a binding is present, at any requested
profile and at none, exactly as it reports `AWR-ENV-001` for an unverified attestation.

---

## 11. Verification result and reason codes

### 11.1 Result shape

A conforming implementation's `verify` output **MUST** be a JSON object with at least:

```json
{
  "valid": false,
  "awrVersion": "2.0.0",
  "documentType": "WorkReceipt",
  "profile": null,
  "reasons": [ { "code": "AWR-PROOF-006", "severity": "error", "detail": "…" } ],
  "warnings": [ { "code": "AWR-ENV-001", "severity": "warning", "detail": "…" } ],
  "chain": { "resolved": 1, "unresolved": 2 },
  "verifiedProof": null
}
```

- `valid` **MUST** be `true` if and only if `reasons` contains no entry of severity `error`.
- `detail` is human-readable, unstable, and **MUST NOT** be parsed.
- Codes are stable across versions of this specification: a code is never re-used for a
  different meaning; retired codes are marked retired.
- Every code has **exactly one** severity, the one §11.2 gives it. A code listed as `error`
  **MUST NOT** appear in `warnings`, and a code listed as *(warning)* **MUST NOT** appear in
  `reasons`. A result that moves a code between the two is not comparable with any other
  implementation's, and `valid` stops being a function of the codes reported.
- `profile` is `null` unless a profile is satisfied; see §10.4 for the three cases that
  settles.
- `awrVersion` reports the **document's** `awrVersion` property (§3.1) as received, and is
  `null` when the document does not carry one or the verifier could not determine it. It is
  **NOT** the version the verifier implements: a verifier that prints its own version there
  reports `"2.0.0"` for a document that is not an AWR/2 document at all, which is the one
  question the member exists to answer. A verifier **MUST NOT** report a value the document
  does not carry — an AWR/1 document (§12) has no `awrVersion`, so the answer is `null` and
  `AWR-LEGACY-001` is what names the dialect.
- `documentType` reports the AWR type drawn from the document's `type` array (§3.1), and is
  `null` when the verifier could not determine it — including when `type` names **more than
  one** AWR type (`AWR-DOC-005`), where no single type is the document's and picking the
  first would make the answer depend on member order. As with `awrVersion`, a verifier **MUST
  NOT** substitute a value the document does not carry. For an AWR/1 document `type` is
  outside the signature and **MUST NOT** be reported as attested (§12); reporting it here is
  reporting what was received, not what was signed.
- Both members are `null` whenever any `AWR-CANON-*` code is reported. A document that has
  no canonical form (§4) has no confirmed content at all: §4.3 exists precisely because the
  bytes such a document canonicalizes to are not the bytes its issuer signed, so quoting its
  `awrVersion` and `type` back to the caller states as received something that was never
  received intact. This is also the only way the two members can be made a property of the
  *document* rather than of the verifier's parser architecture: a strict lexical parser
  rejects `2340.0` before it sees `type` while a parser that carries the literal to the
  subject validator reads both, and the reverse holds for a lone surrogate — so left free,
  three conformant verifiers answered three different things about the same five documents.
  The permission to differ, below, is about *how many codes* a verifier can determine, and it
  stays; it never extended to these two members.
- `chain` counts **§8.1 `parents` edges** — nothing else. `resolved` is the number of edges
  the resolution matched to a supplied document by digest, `unresolved` the number it did not
  (§8.2). A `VerificationVerdict`'s `verifiedWork` and a `BlameAttestation`'s `chain` and
  `blamedWork` are digest references (§3.2) but are **not** chain edges, and **MUST NOT** be
  counted here: their outcome is `AWR-VDCT-005` and `AWR-BLAME-001`. A standalone verdict
  therefore reports `{ "resolved": 0, "unresolved": 0 }`, not `{"resolved": 0, "unresolved":
  1 }` — the latter tells a caller a hop went unchecked when the document names no hop, and
  "chain intact" versus "chain not checked" (§8.2) is exactly the distinction the member is
  for. A `parents` entry that is not a well-formed digest reference (`AWR-CHAIN-001`,
  `AWR-CHAIN-002`) is reported through its own code and is counted in **neither** total: it
  never entered resolution, so calling it `unresolved` would conflate "I could not find this
  parent" with "this edge names no parent I could look for".
- `verifiedProof` holds the zero-based index of the proof that verified — `0` for the single
  proof of §6.1 — and is `null` when no proof verified. It is **REQUIRED** whenever §6.3
  step 6 was performed and succeeded, whether `proof` was one object or an array. It was
  **OPTIONAL** in the single-proof case in an earlier revision, which meant two conformant
  verifiers reported `0` and `null` for the same valid document and a caller could not read
  the member without knowing which implementation produced it.

  When the input is a **bundle verified without a profile** (§9) there is no subject
  document, so `verifiedProof` reports the value from `documents[0]`. That is deterministic,
  and it is the only reading that stays correct for the single-document bundle, which is the
  common case. A caller needing per-document detail verifies the documents individually —
  the container result deliberately reports the conjunction, not a per-member breakdown.

  Because §6.3 gives every condition that prevents step 6 a code of its own, the member is
  a **function of the codes reported**, in both directions:

  > A verifier **MUST** report `verifiedProof: null` when the result carries any code that
  > §6.3 names as preventing step 6 — every `AWR-CANON-*`, every `AWR-KEY-*`, every
  > `AWR-PROOF-*`, `AWR-DOC-001` and `AWR-DOC-010` — or when no §6.1 proof was checked at
  > all: for an AWR/1 document (`AWR-LEGACY-001`), whose signature is not a §6.1 proof; for
  > a document the §12.3 version gate rejected (`AWR-LEGACY-003`) or whose AWR/1 rules the
  > caller declined (`AWR-LEGACY-005`), neither of which is verified under any rule set;
  > and whenever no subject document was identified, which is a bundle whose version is
  > unsupported (§9) or whose subject is ambiguous (`AWR-BUNDLE-003`).
  >
  > Conversely, when a §6.1 proof was checked and verified, a verifier **MUST** report its
  > index and **MUST NOT** report `null`.

  `documentType: null` is **not** a signal that no proof was checked, and the two must not
  be conflated: a document naming two AWR types (`AWR-DOC-005`) has no determinable type
  while its proof verifies perfectly well, so its result is `documentType: null` with
  `verifiedProof: 0`.

  The blocking codes are exactly §6.3's steps 1–5 plus step 6's own failure: a document with
  no canonical form was never hashed, a document with no authoritative public key — one that
  is not an object at all (`AWR-DOC-001`), one with no `issuer.id` (`AWR-DOC-010`), or one
  whose `publicKeyJwk` contradicts its `did:key` (`AWR-KEY-003`, §5.2) — was never checked
  against a key, and a proof configuration that is not the one AWR/2 defines
  (`AWR-PROOF-002`…`005`, `007`…`009`) is not a proof this specification knows how to verify.
  Reporting `verifiedProof: 0` beside `AWR-PROOF-002` asserts that proof 0 verified, for a
  proof AWR/2 does not accept; reporting `null` beside a signature that did verify hides the
  one fact the member carries. Every code **outside** that set — a semantic error, a chain
  error, a profile error — leaves the signature check untouched, so `verifiedProof` stays
  non-`null` on an otherwise invalid document, which is the whole point of separating §6.3
  step 6 from §6.3 step 7.
- Additional members **MAY** appear, both at the top level and inside `chain`: "at least"
  above is a floor, not a closed set, and an implementation reporting *which* edges resolved
  (§8.2) needs somewhere to put them. A consumer **MUST** ignore members it does not know,
  and an implementation **MUST NOT** use an additional member to carry a reason code, whose
  only two homes are `reasons` and `warnings` at the severity §11.2 gives it.
- A verifier **MUST** report **all** errors it can determine, not only the first. Diagnosing
  an interoperability failure from a single early error is what makes independent
  implementation expensive. Implementations legitimately differ in *how much* they can
  determine, and the difference is permitted rather than arbitrated: a strict lexical parser
  rejects `"amount": 0.15` with `AWR-CANON-001` (§4.3) and never sees a `price`, while a
  parser that carries the value to the subject validator determines `AWR-RCPT-002` as well and
  **MAY** report both. What is *not* permitted is reporting only the field-level code: the
  document has no canonical form, so the canonicalization code is the one that says why nothing
  else about it can be trusted.

### 11.2 Registry

**Document (`AWR-DOC-*`)**

| Code | Meaning |
|---|---|
| `AWR-DOC-001` | Not a JSON object |
| `AWR-DOC-002` | `@context` missing, not an array, or first element is not the VC 2.0 context |
| `AWR-DOC-003` | AWR namespace URI absent from `@context` |
| `AWR-DOC-004` | `type` missing `VerifiableCredential` |
| `AWR-DOC-005` | No AWR document type, or more than one, in `type` |
| `AWR-DOC-006` | `id` missing or not an absolute URI |
| `AWR-DOC-007` | `validFrom` missing or malformed; or `validUntil` not later than `validFrom` |
| `AWR-DOC-008` | `credentialSubject` missing or not a single object |
| `AWR-DOC-009` | `awrVersion` missing, malformed, or major version not implemented |
| `AWR-DOC-010` | `issuer` missing, not an object, or missing `id` |

**Canonicalization (`AWR-CANON-*`)**

| Code | Meaning |
|---|---|
| `AWR-CANON-001` | Non-integer JSON number present |
| `AWR-CANON-002` | Integer outside ±(2^53−1) |
| `AWR-CANON-003` | Invalid Unicode (lone surrogate) in string data |
| `AWR-CANON-004` | Duplicate object property name |
| `AWR-CANON-005` | Input is not well-formed JSON |
| `AWR-CANON-006` | Canonical form mismatch — implementation self-check failed |

**Keys (`AWR-KEY-*`)**

| Code | Meaning |
|---|---|
| `AWR-KEY-001` | `issuer.id` is not a `did:key`; or an AWR/1 document yields no usable key (§12.2) |
| `AWR-KEY-002` | `did:key` malformed: bad multibase, undecodable payload, unrecognised multicodec, or key length other than 32 bytes (§5.1) |
| `AWR-KEY-003` | `publicKeyJwk` inconsistent with `did:key`; or, in AWR/1, the key the signature was checked against is not the key `issuer.id` names (§12.4) |
| `AWR-KEY-004` | Well-formed `did:key` naming a recognised key type other than `ed25519-pub` (§5.1) |

**Proof (`AWR-PROOF-*`)**

| Code | Meaning |
|---|---|
| `AWR-PROOF-001` | `proof` missing |
| `AWR-PROOF-002` | `proof.type` is not `DataIntegrityProof` |
| `AWR-PROOF-003` | Unsupported `cryptosuite` |
| `AWR-PROOF-004` | `proofPurpose` is not `assertionMethod` |
| `AWR-PROOF-005` | `proofValue` not multibase base58btc of 64 bytes |
| `AWR-PROOF-006` | Ed25519 signature verification failed |
| `AWR-PROOF-007` | `verificationMethod` does not match `issuer.id` |
| `AWR-PROOF-008` | `proof.@context` inconsistent with document `@context` |
| `AWR-PROOF-009` | `proof.created` missing or malformed |

**Receipt (`AWR-RCPT-*`)**

| Code | Meaning |
|---|---|
| `AWR-RCPT-001` | `inputDigest` or `outputDigest` missing or not a valid SRI string |
| `AWR-RCPT-002` | `price` malformed (currency or decimal-string amount) |
| `AWR-RCPT-003` | `work` timestamps missing or inconsistent |
| `AWR-RCPT-004` | `work.latencyMs` negative or not an integer |
| `AWR-RCPT-005` | `work.modelId` missing or empty |
| `AWR-RCPT-006` | `work.status` missing or not in the enumeration |

**Verdict (`AWR-VDCT-*`)**

| Code | Meaning |
|---|---|
| `AWR-VDCT-001` | `verifiedWork` missing, or missing `id`/`digestSRI` |
| `AWR-VDCT-002` | `score` not a decimal string in [0,1] |
| `AWR-VDCT-003` | `method` missing or `method.id` empty |
| `AWR-VDCT-004` | `verdict` not in the enumeration |
| `AWR-VDCT-005` | `verifiedWork.digestSRI` does not match the supplied receipt |
| `AWR-VDCT-006` | *(warning)* `verdict` inconsistent with `score`/`threshold` |
| `AWR-VDCT-007` | `evidence` entry without `digestSRI` |

**Blame (`AWR-BLAME-*`)**

| Code | Meaning |
|---|---|
| `AWR-BLAME-001` | `blamedWork` not reachable from `chain` through available receipts |
| `AWR-BLAME-002` | `failureClass` not in the enumeration |
| `AWR-BLAME-003` | `chain` or `blamedWork` missing or malformed |
| `AWR-BLAME-004` | `confidence` not a decimal string in [0,1] |

**Chain (`AWR-CHAIN-*`)**

| Code | Meaning |
|---|---|
| `AWR-CHAIN-001` | `parents` entry missing `digestSRI` |
| `AWR-CHAIN-002` | Digest reference format or algorithm invalid |
| `AWR-CHAIN-003` | Parent digest mismatch against the supplied parent |
| `AWR-CHAIN-004` | Cycle detected |
| `AWR-CHAIN-005` | Depth or node limit exceeded |
| `AWR-CHAIN-006` | Same parent `id` with conflicting digests |
| `AWR-CHAIN-007` | *(warning)* Parent `outputDigest` ≠ child `inputDigest` |

**Bundle (`AWR-BUNDLE-*`)**

| Code | Meaning |
|---|---|
| `AWR-BUNDLE-001` | `awrBundle` missing or unsupported, or `documents` empty |
| `AWR-BUNDLE-002` | Duplicate document `id` with differing content |
| `AWR-BUNDLE-003` | Subject document ambiguous |

**Profile (`AWR-PROFILE-*`, `AWR-L2-*`)**

| Code | Meaning |
|---|---|
| `AWR-PROFILE-001` | L1: no valid verdict for the receipt |
| `AWR-PROFILE-002` | L1: verdict issuer equals receipt issuer |
| `AWR-PROFILE-003` | L2: fewer than two distinct verdict issuers |
| `AWR-PROFILE-004` | L2: no settlement or stake binding present |
| `AWR-L2-001` | *(warning)* Accountability binding present but not checked on-chain |

**Environment, time, legacy**

| Code | Meaning |
|---|---|
| `AWR-ENV-001` | *(warning)* Attestation present and not verified |
| `AWR-TIME-001` | *(warning)* `validFrom` in the future beyond the caller's skew allowance |
| `AWR-TIME-002` | *(warning)* `validUntil` in the past |
| `AWR-LEGACY-001` | *(warning)* Document verified under the AWR/1 legacy rules (§12) |
| `AWR-LEGACY-002` | AWR/1 document whose two legacy canonical dialects both failed |
| `AWR-LEGACY-003` | Version signals disagree: the document carries both an AWR/2 signal and an AWR/1 proof suite, and is verified under neither (§12.3) |
| `AWR-LEGACY-004` | *(warning)* The AWR/1 signature was checked against key material carried by the document, which the AWR/1 signature does not cover; no issuer identity is attested (§12.4) |
| `AWR-LEGACY-005` | AWR/1 verification declined: §12 support is OPTIONAL and this verifier was asked not to apply it (§12.3) |

### 11.3 Freshness is policy, not validity

Age is **not** a validity property. A verifier **MUST NOT** invalidate a document because it is
old; `AWR-TIME-001`/`002` are warnings and any age threshold belongs to the caller's policy. A
receipt from two years ago is exactly as cryptographically sound as one from today, and an
audit is the main reason old receipts are read.

---

## 12. Annex: AWR/1 legacy documents (informative-normative)

Documents issued before this specification carry `Ed25519Signature2018`, a base64 `proofValue`,
and a signature over a pipe-delimited rendering of `credentialSubject` only. They are
designated **AWR/1**.

An implementation **MAY** support AWR/1 verification. If it does:

- It **MUST** decide *before verifying anything* whether this section applies at all, by §12.3.
  A document that presents itself as AWR/2 is never verified under this section, whatever its
  `proof.type` says.
- It **MUST** report `AWR-LEGACY-001` on every AWR/1 document.
- It **MUST NOT** issue AWR/1 documents.
- It **MUST** treat `id`, `type`, `issuer`, and any `hubInfo` as **unsigned** in AWR/1 and
  **MUST NOT** report them as attested (§13.1). §12.4 states what the §11.1 result must
  therefore carry, and what it must not: an AWR/1 result names a **key**, never an issuer.
- It **MUST NOT** apply the AWR/2 rules that postdate AWR/1 to a legacy document: the §3.1
  envelope, the §3.3–3.5 subject shapes, the §5.1 `did:key` form and the §4.3 number
  restriction are all AWR/2 rules, and applying them would make every AWR/1 document invalid
  for reasons this section does not state. In particular a verifier whose parser enforces §4.3
  lexically **MUST** re-read the bytes with the number restriction lifted when the strict parse
  failed only on a number, and continue on this path if what comes out is an AWR/1 document.
  An AWR/1 document therefore reports `AWR-LEGACY-001`, the outcome of the signature check,
  and nothing derived from the AWR/2 subject rules.
- It **MUST** try both known dialects of the legacy canonical form and accept either:

  - **dialect A (integer-preserving):** a JSON integer renders as `2340`
  - **dialect B (float-coercing):** the same integer renders as `2340.0`

  The two dialects exist because the reference issuer was written in a language that
  distinguishes integers from floats and the reference verifier in one that does not. They
  produce different bytes for the same document, so signatures made under one do not verify
  under the other. Both are accepted for legacy documents only; failure under both is
  `AWR-LEGACY-002`.

- The legacy form also applied NFC normalization to strings and sorted keys by code point.
  Both deviate from RFC 8785 (§4.1) and are part of the AWR/1 dialect definition, not of AWR/2.

### 12.1 The AWR/1 pipe-delimited rendering

Earlier revisions of this section said only "a pipe-delimited rendering of `credentialSubject`",
which is not enough to verify a single document: two implementations written from that sentence
produced different bytes and neither could read the other's receipts. The layout is therefore
written out here. It is **descriptive of AWR/1** — nothing in it applies to AWR/2, which uses
§4.

```text
form   = [ entry *( "|" entry ) ]
entry  = path "=" leaf
path   = segment *( "." segment )
segment = <member name, NFC-normalized> / <decimal array index, no leading zeros>
```

The entries are the **leaves** of `credentialSubject`, one per leaf:

1. Traverse `credentialSubject`. An object contributes its members, visited in ascending
   Unicode **code-point** order of the member name; an array contributes its elements in index
   order, each path segment being the element's decimal index. Segments are joined with `.`.
2. An **empty** object or array has no leaves and therefore contributes **no entry**. An empty
   member is thus indistinguishable from an absent one in AWR/1.
3. Collect the `path=leaf` entries and sort them by `path`, compared as sequences of Unicode
   code points. The sort is over whole paths, not per level, and is observable: for members
   `a` (an object holding `z`) and `a!` (a string), per-level order gives `a.z` before `a!`
   while path order gives `a!` first, because `!` (U+0021) precedes `.` (U+002E).
4. Join with `|` and encode as UTF-8. An empty `credentialSubject` renders as the empty string.

Leaf rendering:

| Leaf | Rendering |
|---|---|
| string | its characters after **NFC** normalization, unquoted and unescaped |
| `true` / `false` | `true` / `false` |
| `null` | `null` |
| integer, dialect A | its decimal digits: `2340` |
| integer, dialect B | the same integer as an IEEE-754 double, with a `.0` suffix: `2340.0` |
| number with an integral value written with a fraction or exponent | as an integer, per dialect |
| any other number | exactly ten fractional digits, correctly rounded, trailing zeros **kept**: `0.5` → `0.5000000000` |

Because leaves are unquoted, a string containing `|` or `=` makes the rendering ambiguous. That
is not a defect to be repaired here; it is one of the reasons §4 exists.

The rendering is defined only for numbers whose magnitude is below 10^15 and integers within
±(2^53−1). An AWR/1 document carrying a number outside that range has **no** defined legacy
canonical form, and a verifier **MUST** report `AWR-LEGACY-002` rather than choose a rendering.

### 12.2 The AWR/1 signing key, and AWR/1 error codes

Appendix D records that an AWR/1 `issuer.id` was `did:key:` followed by the first 32 characters
of a base64 public key, which names no recoverable key. A verifier therefore takes the key
from, in order: `issuer.publicKeyJwk` (RFC 8037 OKP/Ed25519), `issuer.publicKeyBase64`, or
`issuer.id` when it happens to be a genuine `did:key`. When none of the three yields 32 bytes
the document cannot be checked at all and the verifier **MUST** report `AWR-KEY-001`.

`proofValue` is base64 in AWR/1 (§6.1 rejects it in AWR/2). A value that is not base64, or that
does not decode to exactly 64 bytes, is `AWR-PROOF-005` — not `AWR-LEGACY-002`, which means
specifically that both dialects were tried against a usable key and signature and both failed.

Migration guidance: an issuer **SHOULD** switch to AWR/2 for all new documents in one step,
retaining AWR/1 verification for stored documents. Re-signing historical documents as AWR/2
**MUST NOT** be done, since the issuer cannot honestly re-attest a `created` timestamp.

### 12.3 Which rule set applies: the version gate

Earlier revisions of this annex said which *bytes* an AWR/1 signature covers but never said how
a verifier decides that a document is AWR/1 at all. Every implementation written from that text
answered the same way — "the proof suite is `Ed25519Signature2018`" — and that answer is a
complete authentication bypass, because AWR/1 signs neither `proof.type` nor `issuer`. An
attacker takes a target issuer's DID, writes any `credentialSubject` at all, adds
`awrVersion: "2.0.0"` and the AWR/2 `@context` so the document reads as a current receipt,
attaches an `Ed25519Signature2018` proof over the §12.1 rendering signed with a key **they**
hold, and every verifier reports `valid: true` for a document whose `issuer.id` names someone
else. §3.1 says a document "cannot be re-interpreted under a different version's rules by an
intermediary" because `awrVersion` is inside the signed bytes; that guarantee is only real if
version selection actually reads it.

**Version signals.** A document carries an **AWR/2 signal** if any of the following is present.
The list is closed: an implementation **MUST** use exactly these and **MUST NOT** add signals of
its own, since a signal one verifier honours and another ignores is a document two verifiers
disagree about.

1. a top-level `awrVersion` member, whatever its value or JSON type;
2. a top-level `@context` — array or string — containing
   `https://www.w3.org/ns/credentials/v2` or `https://verify.modelmarket.dev/ns/awr/v2`;
3. a proof object, in `proof` or at any index of a `proof` array, whose `type` is
   `DataIntegrityProof`;
4. a top-level `validFrom` or `validUntil` member (AWR/1 used VC 1.1's `issuanceDate`);
5. a `credentialSubject.settlement` member (§10.3).

`credentialSubject.parents` is deliberately **not** a signal, though it is an AWR/2 member:
Appendix D records that AWR/1 also carried `parents`, as identifier strings rather than digest
references, so treating it as an AWR/2 claim would reject part of the honest legacy corpus. The
test for membership of this list is "AWR/1 could not have carried it", not "AWR/2 defines it".

A document carries an **AWR/1 signal** if `proof`, or any index of a `proof` array, is an object
whose `type` is `Ed25519Signature2018`.

**The gate.** A verifier **MUST** classify before it verifies:

- **AWR/2 signal present, no AWR/1 signal** → an AWR/2 document. §12 does not apply.
- **AWR/1 signal present, no AWR/2 signal** → an AWR/1 document. §12 applies.
- **Both present** → *the signals disagree*. The verifier **MUST** report `AWR-LEGACY-003` at
  severity error, **MUST** report `valid: false`, and **MUST NOT** verify the document under
  either rule set. It **MUST NOT** fall back to §12 because the AWR/2 proof failed, and
  **MUST NOT** fall back to §6 because the AWR/1 proof failed: a verifier that tries the other
  rule set after one fails hands the attacker back the choice this gate takes away. The
  position of a proof within a `proof` array **MUST NOT** affect the outcome — three
  implementations that read `proof[0]`, `proof[0]`, and "any element" gave two different
  answers to the same bytes, and the attacker picked the order.
- **Neither present** → an AWR/2 document with no proof this specification recognises. §12 does
  not apply; §6.3 reports `AWR-PROOF-001` or `AWR-PROOF-002` as usual.

A verifier **MUST NOT** select the legacy path by any other means. In particular it **MUST NOT**
infer AWR/1 from the *shape* of `credentialSubject` (the presence of AWR/1-era member names such
as `inputHash`/`outputHash`, or the absence of AWR/2 ones), from `issuanceDate`, or from any
other heuristic: a heuristic is a signal the attacker can raise at will, and one verifier that
carried such a heuristic routed documents to the legacy path with no legacy proof present at all.

Note what this rule does and does not buy. A genuine AWR/2 document cannot be pushed onto the
legacy path, because `awrVersion`, `@context` and `type` are inside its signature and removing
them breaks it. An AWR/1 document cannot be pushed onto the AWR/2 path, because it has no
`DataIntegrityProof`. But **an AWR/1 document has no signed self-description at all** — the
signature covers `credentialSubject` and nothing else — so the classification of an AWR/1
document is always a statement about bytes an attacker could have written. That is not a defect
in the gate; it is the reason §12.4 exists, and the reason AWR/1 support is **OPTIONAL**.

A verifier that supports §12 **MUST** provide a way for the caller to decline it, and **MUST**
report `AWR-LEGACY-005` at severity error when a document is classified AWR/1 and the caller has
declined. §17's CLI spells this `--no-legacy`. A deployment that has no AWR/1 corpus of its own
is strictly better off refusing the whole path, and until now no implementation offered the
option even though this section has always said support is optional.

### 12.4 What an AWR/1 verification establishes — and what it does not

The AWR/1 signature covers a rendering of `credentialSubject` only (§12.1). `issuer` is
therefore **written by whoever handed you the file**, and every key the document carries —
`issuer.publicKeyJwk`, `issuer.publicKeyBase64`, `issuer.id` — is outside the signature. A
signature checked against a key taken from the same unsigned object proves only that the file is
internally consistent: it says "whoever wrote this document also signed this subject", and the
attacker is happy to sign their own forgery. It says nothing whatever about the party named in
`issuer.id`.

Accordingly, for any document verified under this section:

- The verifier **MUST NOT** report an issuer identity as attested, in `reasons`, in `warnings`,
  or in any member of the §11.1 result. Where an implementation's result carries an issuer
  member for AWR/2 documents, that member **MUST** be `null` on the legacy path. Echoing
  `issuer.id` back to a caller beside `valid: true` is the whole exploit: the caller reads a
  boolean and a DID and concludes the DID's owner signed something.
- The verifier **MUST** report, in the §11.1 result, an object member `legacy` carrying at
  least:

  ```json
  "legacy": {
    "dialect": "A",
    "keySource": "document",
    "issuerAttested": false,
    "verifiedKey": "did:key:z6Mki…",
    "unsignedFields": ["id", "type", "issuer", "hubInfo"]
  }
  ```

  `keySource` is `"caller"` when the key came from the caller out of band and `"document"` when
  it came from the document. `issuerAttested` is `false`; it is a constant because AWR/1 can
  never attest an issuer, and it is present because a member that is always `false` is read,
  while a member that is merely absent is not. `verifiedKey` is the `did:key` form (§5.1) of the
  key the signature actually verified under, or `null` when no signature verified — it is the
  only honest answer to "who signed this", and it puts the decision of whose key that is where
  it belongs, with the caller. `dialect` is `null` when no signature verified.
- A verifier **MUST** accept an **expected public key supplied by the caller out of band**, and
  when one is supplied it **MUST** be the only key the signature is checked against; key
  material carried by the document **MUST NOT** be substituted for it, and **MUST NOT** be tried
  as a fallback when the caller's key fails. §17's CLI spells this `--expected-key`, taking a
  `did:key` or a 64-character hex Ed25519 public key. Failure under the caller's key is
  `AWR-LEGACY-002` as usual.
- When no expected key was supplied and the key was taken from the document, the verifier
  **MUST** report `AWR-LEGACY-004` at severity warning, whether or not the signature then
  verifies. `valid: true` beside `AWR-LEGACY-004` means exactly "the §12.1 rendering of
  `credentialSubject` is signed by the key in `legacy.verifiedKey`" and **MUST NOT** be read by
  a caller as an attestation by any named party.

  This is deliberately a warning and not an error. Making it an error would invalidate the
  entire honest AWR/1 corpus, which is the corpus this annex exists to keep readable, and would
  push deployments to disable checking rather than to supply a key. The forgery is closed
  instead by removing the thing the forger wanted: after this section, no result derived from an
  AWR/1 document names an issuer.

- Two disagreeing statements about the signing key are an error, not a preference. When
  `issuer.id` is a string beginning `did:key:` whose value up to any `#` fragment is a
  well-formed `did:key` (§5.1), that DID **names a key**; if the key the verifier used is not
  that key, the verifier **MUST** report `AWR-KEY-003` at severity error and **MUST NOT** report
  the document valid. This **MUST** hold for the fragment form `did:key:z6Mk…#z6Mk…` — the §5.3
  `verificationMethod` string — as well as for the bare form. An implementation that parsed only
  the bare form let an attacker keep the victim's DID as a literal prefix of `issuer.id` while
  supplying their own `publicKeyJwk`, and reported `valid: true`. An `issuer.id` that is *not* a
  well-formed `did:key` — including `did:key:` followed by 32 base64 characters, which
  Appendix D records as the AWR/1 norm — names no key, so there is nothing to disagree with; the
  document is then unanchored and `AWR-LEGACY-004` is the whole of what can be said.

**Order of operations.** Two verifiers that check the same things in a different order report
different codes for the same document, so the order is fixed here, and every step is terminal:
when a step reports its code, the steps after it are not performed and `legacy.dialect` and
`legacy.verifiedKey` are `null`.

1. Classify (§12.3): `AWR-LEGACY-003`, or `AWR-LEGACY-005` if the caller declined.
2. Report `AWR-LEGACY-001` and check that `credentialSubject` is an object (`AWR-DOC-008`).
3. Select the key: the caller's if supplied, otherwise the document's, in the §12.2 order.
   No key at all is `AWR-KEY-001`. A key taken from the document adds the `AWR-LEGACY-004`
   warning, which is not terminal.
4. Cross-check `issuer.id` against the selected key: `AWR-KEY-003`.
5. Decode `proofValue` as 64 base64 bytes: `AWR-PROOF-005`.
6. Try dialect A, then dialect B: `AWR-LEGACY-002` if neither verifies, and
   `AWR-LEGACY-002` also when the subject holds a value §12.1 defines no rendering for.

`AWR-LEGACY-001` is reported in every case from step 2 onward — it says the document *was*
read under the AWR/1 rules, so it is reported however step 6 turns out, and it is **not**
reported for a document step 1 rejected, which was read under no rules at all.
`verifiedProof` is `null` throughout: an AWR/1 signature is not a §6.1 proof (§11.1).

---

## 13. Security considerations

### 13.1 Signature coverage

The signature covers the entire document. This is not a stylistic choice: in AWR/1, `id` was
outside the signature while `parents` referenced ids, so an intermediary could rename a valid
receipt and re-point a chain without breaking any signature. Any field an implementation
leaves out of the canonical form is a field an intermediary controls.

The same principle decides how a verifier may *choose* its rule set. AWR/1 leaves `issuer` and
`proof.type` outside the signature, so a verifier that reads `proof.type` to select the AWR/1
rules and then reads `issuer` for the key has authenticated nothing at all — the attacker wrote
both. §12.3 therefore makes AWR/2's signed self-description win over the unsigned proof suite,
and §12.4 forbids reporting an issuer identity from an AWR/1 document. Support for AWR/1 remains
**OPTIONAL**, and declining it (`AWR-LEGACY-005`) removes the class outright.

### 13.2 Reference substitution

Verdicts and blame attestations reference receipts by digest as well as identifier (§3.2)
precisely so that a favourable verdict cannot be detached from the work it judged and attached
to different work with the same identifier.

### 13.3 Self-verification

A verdict signed by the receipt's issuer proves only self-consistency. Profile L1 excludes it
structurally (§10.2). Verifiers exposing a single boolean to users **SHOULD** surface the
distinction, because "verified" that means "verified by itself" is worse than no claim.

### 13.4 Denial of service

Chain resolution, bundle processing and canonicalization all consume attacker-influenced work.
Limits in §8.2 and §9 are mandatory. Implementations **SHOULD** additionally bound total input
size and reject documents with unreasonable nesting depth before canonicalizing.

### 13.5 No dereferencing

A verifier **MUST NOT** fetch `@context` URIs, parent documents, evidence bytes, policies, or
schemas during verification. Beyond privacy (§14), a fetching verifier lets a document author
choose which bytes the verifier reads at verification time.

### 13.6 No revocation

AWR/2 has no revocation or status list, because both require a network lookup. A compromised
key cannot be un-said; it can only be superseded (§5.4). Deployments needing revocation
**SHOULD** implement it at their own trust layer and **MUST NOT** represent an unrevoked
document as revocation-checked.

### 13.7 What a valid document does not mean

A valid AWR document means: *this issuer signed these claims, and the bytes are intact.* It
does not mean the model ran, the digests correspond to real payloads, the price was paid, or
the output is correct. Everything AWR provides is attribution. Interfaces that render validity
as a green check without the issuer identity misrepresent the format.

---

## 14. Privacy considerations

- Documents carry **digests**, never payloads. Inputs and outputs are not disclosed by
  publishing a receipt — but a digest of a low-entropy payload is a confirmation oracle, so
  issuers handling short or enumerable inputs **SHOULD** include a secret salt in the hashed
  bytes and document that they do.
- `did:key` is a stable pseudonymous identifier and is fully correlatable across all documents
  it signs. An issuer needing unlinkability **MUST** rotate keys; AWR provides no other
  mechanism.
- Offline verification means a verifier learns nothing about the reader, and the issuer learns
  nothing about verification. This is a deliberate property and §13.5 protects it.
- `work.modelId`, `method.modelIds` and `issuer.name` are voluntary disclosures. AWR requires
  none of them to be truthful or complete, and they **SHOULD** be omitted where they leak
  vendor relationships that need not be public.

---

## 15. Media type and file conventions

- Media type: `application/vc` (W3C VC 2.0), optionally with
  `profile="https://verify.modelmarket.dev/ns/awr/v2"`.
- Bundles: `application/json`.
- File extensions: `.awr.json` for a document, `.awrb.json` for a bundle. Non-normative.
- HTTP: servers **SHOULD** send `Cache-Control: immutable` for documents addressed by digest,
  and **MUST NOT** require authentication for a document they intend to be independently
  verifiable.

---

## 16. Mappings to other standards

| Standard | Relationship |
|---|---|
| **W3C VC Data Model 2.0** | AWR documents *are* VCs; §3.1 profiles the envelope |
| **W3C Data Integrity + `eddsa-jcs-2022`** | The only proof mechanism (§6); off-the-shelf VC libraries verify AWR documents |
| **RFC 8785 (JCS)** | Canonicalization (§4), with the number restriction of §4.3 as an AWR profile |
| **RFC 8032 (EdDSA)** | Pure Ed25519 signatures |
| **`did:key`** | Issuer identity (§5); chosen because it resolves offline |
| **W3C SRI** | Digest reference encoding (§3.2) |
| **RFC 8037 (OKP JWK)** | Optional `publicKeyJwk` (§5.2) |
| **C2PA** | Complementary: a C2PA manifest describes an asset, an AWR receipt describes the invocation that produced it. A C2PA assertion **MAY** carry an AWR document's `id` and `digestSRI`; AWR defines no C2PA assertion label of its own |
| **OpenTelemetry GenAI** | Complementary: a span is unsigned telemetry, a receipt is a signed claim. `gen_ai.request.model` maps to `work.modelId`; a span **MAY** carry the receipt `id` as an attribute |
| **HTTP 402 / x402-style payments** | Complementary: payment protocols settle a request; a `VerificationVerdict` supplies the *condition* a conditional settlement can reference (§10.3) |
| **AIMarket Protocol v2** | One consumer; its `receipt.verification` field references AWR verdicts |

### 16.1 What an off-the-shelf VC library does differently

Verified by running `@digitalbazaar/vc` 7.3.0 over `awr/vectors/valid/`. Two divergences are
real and an adopter must be told about them rather than discovering them:

1. **Temporal validity.** VC 2.0 treats `validFrom`/`validUntil` as validity, so that stack
   reports a stale or not-yet-valid document as **invalid**. AWR/2 §11.3 deliberately makes
   age a *warning*: a receipt from two years ago is exactly as cryptographically sound as one
   from today, and audit is the main reason old receipts are read. Both positions are
   defensible; they are not the same position. An issuer that wants third-party VC libraries
   to accept its receipts indefinitely **SHOULD** omit `validUntil`, and a consumer that reads
   old receipts **SHOULD NOT** rely on a general VC library for that judgement.
2. **The legacy path.** A VC library implements no part of AWR/1 (§12) and will reject those
   documents outright. That is correct behaviour, not a gap.

Everything else — the proof, the canonicalization, the `did:key` resolution, unknown extension
properties, non-BMP object keys, decomposed Unicode and proof arrays — the library handles with
no AWR-specific code. The one thing it needs is a `did:key` resolver in its document loader,
which is offline and about ten lines.

The AWR namespace URI in `@context` is **not** dereferenced by the `eddsa-jcs-2022` path,
because JCS canonicalizes the JSON rather than expanding the JSON-LD. A verifier **MUST NOT**
fetch it (§13.5).

A JSON-LD-*expanding* consumer is the other case, and it is now served: the context document
is [`awr/ns/v2/context.json`](ns/v2/context.json), published at the namespace URI. Every
document in `awr/vectors/valid/` expands cleanly under it with the `jsonld` processor. Five
terms — `digestSRI`, `evidence`, `status`, `nonce` and `name` — are deliberately **not**
defined there because the VC 2.0 context already defines and protects them; redefining a
protected term makes expansion fail outright, and three of those five were found only after
expansion failed on 12 of 15 valid vectors.

Until that document existed the namespace URI answered with the verifier's HTML page from an
SPA fallback — a `200` and `text/html` where a consumer asked for a context, which is worse
than a `404` because it looks like success.

---

## 17. Conformance

An implementation conforms to AWR/2 if it:

1. Implements §4 canonicalization, reproducing `awr/vectors/canonicalization/` byte-for-byte;
2. Implements §6 verification and rejects every negative vector with its recorded reason code;
3. Implements the CLI contract below, so it can be driven by `awr/conformance/`;
4. Reports results in the shape of §11.1;
5. Never fetches the network during verification (§13.5).

**CLI contract.** A conforming implementation provides an executable accepting:

| Invocation | Behaviour |
|---|---|
| `<impl> verify <file> [--profile L0\|L1\|L2] [--parents <file>…] [--now <rfc3339>] [--subject <id>] [--max-depth <n>] [--max-nodes <n>] [--expected-key <key>] [--no-legacy]` | Prints the §11.1 result JSON to stdout |
| `<impl> canonicalize <file>` | Prints the §4 canonical bytes of the JSON in `<file>`, no trailing newline |
| `<impl> digest <file>` | Prints `sha256-<base64>` over the canonical bytes |
| `<impl> hashdata <file>` | Prints `proofConfigHash`, `transformedDocumentHash`, `hashData` as hex, one per line |
| `<impl> issue <subject-file> --key <file> [--type <type>]` | Prints a signed document (**OPTIONAL** for verify-only implementations) |

- `<file>` is one AWR document or one bundle (§9); an implementation **MUST** accept either.
- `--parents` names supporting documents: chain parents, the verdicts L1/L2 need, the receipts a
  `BlameAttestation` refers to. Each named file is itself a document or a bundle. The flag takes
  one or more paths.
- `--subject <id>` is the "explicit caller argument" §9 requires for identifying the subject of a
  bundle. The name is normative here because a harness that has to guess the flag cannot drive
  two implementations with one manifest.
- `--max-depth` and `--max-nodes` override the §8.2 defaults of 64 and 1024. They are the only
  way to exercise `AWR-CHAIN-005`'s node-count limit without a 1025-document bundle.
- `--now <rfc3339>` fixes "now" so that `AWR-TIME-001`/`002` are deterministic.
- `--expected-key <key>` supplies the signing key **out of band**, as a `did:key` (§5.1) or a
  64-character hex Ed25519 public key. §12.4 requires it of every implementation that supports
  AWR/1, because an AWR/1 signature checked against a key the document itself carries attests
  no identity. An implementation **MAY** also honour it on the AWR/2 path.
- `--no-legacy` declines §12 entirely, so an AWR/1 document reports `AWR-LEGACY-005`. §12 support
  is OPTIONAL and a deployment with no AWR/1 corpus **SHOULD** use this.
- `issue` reads its `--key` from a file. §17 does not fix the key file's format; an
  implementation **MUST** accept a bare 64-character hex Ed25519 seed on one line, which is the
  interoperable form, and **MAY** accept others (an RFC 8037 OKP JWK with `d`, a multibase
  private key).

Exit codes: `0` = valid / operation succeeded, `1` = invalid document (a result was produced),
`2` = usage or I/O error, `3` = unimplemented subcommand. A document that cannot be parsed or
canonicalized exits `1`, not `2`: it is an invalid document with a reason code, and the code
goes to stderr when no result JSON can be produced.

Implementations **MUST** write only the specified payload to stdout; diagnostics go to stderr.

---

## Appendix A — Worked example

Byte-level intermediate values for a complete signing operation are generated, not transcribed,
so that they cannot drift from the implementations: see `awr/vectors/proof/worked-example.json`
(document, key, `canonicalProofConfig`, `transformedDocument`, the three hashes, `proofValue`)
and `awr/vectors/README.md` for how to regenerate and cross-check it.

## Appendix B — Schemas

`awr/schemas/`: `work-receipt-v2.json`, `verification-verdict-v2.json`,
`blame-attestation-v2.json`, `bundle-v2.json`, `common-v2.json`.

JSON Schema is a convenience for tooling and is **not** the normative definition; this document
is. Where they disagree, the schema is a bug.

## Appendix C — Vectors

`awr/vectors/index.json` lists every vector with its expected outcome and reason codes. See
`awr/conformance/README.md`.

## Appendix D — Change log against AWR/1

| Change | Reason |
|---|---|
| Whole-document signing (was: `credentialSubject` only) | `id`, `issuer`, `type` were unsigned; chain edges were forgeable (§13.1) |
| RFC 8785 JCS, exactly (was: a JCS-labelled variant with NFC, code-point sort, and 10-decimal float truncation) | Two implementations of the same format disagreed on the bytes for any integer field |
| Integers only in signed documents; decimals as strings (§4.3) | Removes the int/float divergence class instead of arbitrating it |
| `eddsa-jcs-2022` + `DataIntegrityProof` (was: `Ed25519Signature2018`, base64 `proofValue`) | Deprecated suite; the current one is a W3C Recommendation with off-the-shelf verifiers |
| Real `did:key` derivation (was: `did:key:` + first 32 chars of base64 public key) | The legacy value was not a valid DID and named a different key than the document embedded |
| `parents` as digest references (was: identifier strings) | Content-addressed edges (§8.1) |
| Verdict and blame as separate signed documents | The verifier and the blame attributor get their own identity, hence accountability |
| Attestations explicitly opaque, `AWR-ENV-001` | The legacy verifier checked a TEE attestation with the receipt issuer's key, which proved nothing while presenting as hardware evidence (§7.3) |
| Age is a warning, not invalidity (§11.3) | The legacy verifier hard-failed documents older than 90 days |
| Reason-code registry, all errors reported | Independent implementation is not feasible against a boolean |
