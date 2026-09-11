# `awr` — AWR/2 reference implementation (Python)

The reference implementation of **AWR/2** (`awr/SPEC.md`, version 2.0.0): three signed,
self-contained W3C Verifiable Credentials — `WorkReceipt`, `VerificationVerdict`,
`BlameAttestation` — secured with an `eddsa-jcs-2022` Data Integrity proof over an
RFC 8785 canonicalization and issued by a `did:key`.

This is the artefact other implementations are compared against, so it is written to be
read: every non-obvious behaviour cites the section of the spec that requires it, and every
place where the spec is ambiguous is listed in [Spec findings](#spec-findings) rather than
resolved silently.

* Pure standard library **except `cryptography`** for Ed25519. JCS, base58btc, multibase,
  SRI, `did:key` and the AWR/1 legacy dialects are implemented here.
* **Nothing is ever fetched.** Section 13.5 forbids a verifier from dereferencing
  `@context` URIs, parent documents, evidence, policies or schemas, so the package imports
  no HTTP client of any kind — `tests/test_chain.py` asserts that as a test.
* Python 3.9+.

---

## Install

```
pip install -e .            # from awr/reference/python
pip install -e '.[test]'    # plus pytest
```

## Library

```python
from awr import SigningKey, issue_work_receipt, verify_document, canonical_sri

key = SigningKey.generate()

receipt = issue_work_receipt(
    {
        "work": {
            "modelId": "claude-sonnet-5@anthropic",
            "startedAt": "2026-07-31T10:15:28Z",
            "completedAt": "2026-07-31T10:15:30Z",
            "latencyMs": 2340,
            "status": "succeeded",
        },
        "inputDigest": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
        "outputDigest": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
        "nonce": "01J9Z8QK4T7YB2N5V6W8XA3C0D",
    },
    key,
    issuer_name="example-hub",
)

result = verify_document(receipt)
assert result["valid"] and result["profile"] == "L0"
```

Entry points worth knowing:

| Function | Purpose |
|---|---|
| `canonicalize(value) -> bytes` | RFC 8785 canonical form, section 4 |
| `canonical_self_check(value, canonicalizer=...)` | proves a canonicalizer is lossless; `AWR-CANON-006` |
| `loads(text_or_bytes)` | strict parser: duplicate keys, floats and huge integers raise |
| `derive_did_key(pub32)` / `parse_did_key(did)` | section 5.1 |
| `SigningKey` | `generate` / `from_seed` / `from_jwk` / `from_key_file_text`; `.did`, `.verification_method` |
| `sign_document(doc, key, created)` | low-level: signs exactly the bytes given, no validation |
| `issue` / `issue_work_receipt` / `issue_verification_verdict` / `issue_blame_attestation` | validating issuance; refuses to emit a document it would reject |
| `document_reference(doc)` | a section 3.2 digest reference to a secured document |
| `verify_document(doc, profile=…, supporting=…, now=…)` | the section 11.1 result object |
| `verify_bundle(bundle, subject_id=…, …)` | section 9 |
| `verify(data, …)` | dispatches document vs bundle on `awrBundle` |
| `resolve_chain(receipt, supporting, reasons, …)` | section 8 walk with the section 8.2 limits |
| `make_bundle(documents)` | section 9 container (unsigned, carries no claims) |
| `legacy_canonical_form(subject, dialect)` | AWR/1 rendering, verification only |
| `REGISTRY` | the section 11.2 reason-code registry with severities |

`verify_document` accepts the *received bytes* (`bytes`/`str`) or an already-parsed object.
Prefer the bytes: section 4.2 requires canonicalizing what arrived, and passing a value
that has been through a lossy intermediate representation is the most common cause of a
valid document failing verification.

### Result shape

Exactly the section 11.1 members, plus additive ones (11.1 says "at least"):

```json
{
  "valid": true,
  "awrVersion": "2.0.0",
  "documentType": "WorkReceipt",
  "profile": "L1",
  "reasons": [],
  "warnings": [{"code": "AWR-L2-001", "severity": "warning", "detail": "…"}],
  "chain": {"resolved": 1, "unresolved": 2},

  "documentDigestSRI": "sha256-…",
  "chainEdges": {"resolved": [{"childId": "…", "parentId": "…", "digestSRI": "…"}],
                 "unresolved": []},
  "profilesEvaluated": {"L1": [], "L2": [{"code": "AWR-PROFILE-004", "…": "…"}]},
  "verifiedProof": 0,
  "proofs": [{"index": 0, "verified": true, "reasons": [], "warnings": []}]
}
```

* `valid` is true **iff** `reasons` has no `error` entry, and **all** determinable errors
  are reported, not the first (section 11.1).
* `chainEdges` exists because section 8.2 requires reporting *which* edges resolved, so
  that "chain intact" and "chain not checked" are distinguishable — the two counts alone
  cannot say that.
* `profilesEvaluated` exists because section 10.4 requires the reason codes of every
  profile evaluated and rejected, while an unrequested profile's shortfall must not make a
  plain L0 receipt invalid. Only the profile you *asked* for is promoted into `reasons`.
* `proofs` / `verifiedProof` report which proof of a proof array verified (section 6.1).
* AWR/1 results additionally carry `legacy`, `legacyDialect` and `unsignedFields`.

## CLI

Section 17's contract, as `awr …` or `python -m awr …`:

| Invocation | Behaviour |
|---|---|
| `awr verify <file> [--profile L0\|L1\|L2] [--parents <file>…] [--now <rfc3339>]` | section 11.1 result JSON on stdout |
| `awr canonicalize <file>` | section 4 canonical bytes, **no trailing newline** |
| `awr digest <file>` | `sha256-<base64>` over the canonical bytes |
| `awr hashdata <file>` | `proofConfigHash`, `transformedDocumentHash`, `hashData` as hex, one per line |
| `awr issue <subject-file> --key <file> [--type <type>]` | a signed document on stdout |

Exit codes: `0` valid / succeeded, `1` invalid document (a result was produced), `2` usage
or I/O error, `3` unimplemented subcommand. **stdout carries only the payload**; every
diagnostic goes to stderr. `--now <rfc3339>` fixes the clock so `AWR-TIME-001`/`002` are
deterministic.

Additive flags: `--subject <id>` (bundle subject, section 9), `--max-depth` / `--max-nodes`
(section 8.2 limits), and on `issue`: `--id`, `--valid-from`, `--valid-until`,
`--issuer-name`, `--include-public-key-jwk`.

`--parents` doubles as the channel for *any* supporting document — chain parents, verdicts
for L1/L2, the receipts a `BlameAttestation` refers to — and each file may be a single
document or a bundle. Section 17 defines no other way to supply a verdict.

`--key` accepts (section 17 does not specify a format):

```
{"kty":"OKP","crv":"Ed25519","d":"<base64url seed>"}   # RFC 8037 JWK
{"privateKeySeedHex":"<64 hex chars>"}
{"privateKeyMultibase":"z<base58btc(0x80 0x26 || seed)>"}
<64 hex chars>                                          # bare seed
```

`hashdata` requires the file to carry a `proof` object (its `proofValue` is ignored); a
document without one is a usage error, exit `2`.

## What this implementation is careful about

**JCS key order (section 4.1 item 1).** Property names sort as arrays of UTF-16 code units
compared as unsigned integers, *not* by code point. The two orders diverge for any name
outside the BMP: an astral character's first UTF-16 code unit is a high surrogate in
`[0xD800, 0xDBFF]`, which sorts *below* every BMP character in `[0xE000, 0xFFFF]`, while
its code point sorts above all of them. `tests/test_jcs.py` proves the divergence — the
same object canonicalizes differently under `sorted()`, and the naive bytes are asserted to
differ.

**No Unicode normalization (section 4.1 item 2).** `"é"` and `"é"` are different
documents with different signatures. `canonical_self_check` catches a canonicalizer that
normalizes, drops unknown members or coerces number types, and reports `AWR-CANON-006`.

**Escaping (section 4.1 item 3).** `\b \t \n \f \r \" \\` as two-character escapes,
**lowercase** `\u00xx` for the remaining C0 controls, everything else literal — U+007F and
U+0080 included.

**Lone surrogates terminate (section 4.1 item 4).** No U+FFFD substitution, ever.

**Duplicate names are rejected (section 4.1 item 5).** `json.loads` keeps the last
occurrence, which would let the parser decide which bytes were signed; the parser here uses
an `object_pairs_hook` and raises `AWR-CANON-004`.

**Numbers (section 4.3).** Integers only, `±(2^53−1)`. Rejection is *lexical*: any literal
with a fraction or exponent is `AWR-CANON-001`, and any Python `float` — including `2340.0`
— is refused on the way out too.

**hashData order (section 6.2 step 6).** `SHA-256(canonicalProofConfig) ||
SHA-256(transformedDocument)`, proof config first. `hashdata` exposes all three values so a
failing implementation can be localised to one step, and a test asserts a signature made
over the reversed concatenation is rejected.

**base58btc leading zeros.** Each leading `0x00` byte encodes to one explicit `1`;
otherwise an Ed25519 key beginning with `0x00` decodes to 31 bytes. Known answer:
`base58btc(b"hello world") == "StV1DL6CwTryKyV"`.

**Chains are content-addressed (section 8.1).** An edge digests the *secured* parent,
signature included, so a parent whose `proof` was stripped or whose bytes were touched
stops matching its edge.

**Attestations are opaque (section 7.3).** `environment.teeAttestation` and
`environment.zkProof` are canonicalized, never verified, always reported as
`AWR-ENV-001`, and never make a document more trustworthy.

**Age is not validity (section 11.3).** `AWR-TIME-001`/`002` are warnings; a two-year-old
receipt is exactly as sound as a fresh one.

**AWR/1 can be verified and cannot be issued (section 12).** `awr.legacy` renders and
verifies both dialects; no function anywhere in the package produces an
`Ed25519Signature2018` proof, and `issue()` refuses an `extra_properties` containing
`proof`. Tests assert the constant appears in exactly one module and that the test suite
itself has to reach for a raw Ed25519 signer to build a legacy fixture at all.

## Tests

```
python -m pytest            # 439 tests
```

Every code in the section 11.2 registry is exercised by an assertion, and the run says so:
the conftest records each code asserted through `assert_error` / `assert_warning` /
`assert_raises_code` and prints the count against the registry in the terminal summary.

```
--------------------------- AWR reason-code coverage ---------------------------
section 11.2 registry: 66 codes; exercised by assertions: 66
every registry code is exercised by at least one test
```

| File | Covers |
|---|---|
| `test_jcs.py` | section 4: UTF-16 vs code-point order, NFC, escapes, surrogates, duplicates, numbers |
| `test_didkey.py` | section 5: base58btc known answers, `did:key` derive/parse, `AWR-KEY-*`, key files |
| `test_proof.py` | section 6: hash order, round trips for all three types, signature coverage, proof arrays |
| `test_reason_codes.py` | `AWR-DOC-*`, `AWR-CANON-*`, `AWR-KEY-*`, `AWR-PROOF-*`, `AWR-RCPT-*`, `AWR-VDCT-*`, `AWR-BLAME-*`, `AWR-ENV-001`, `AWR-TIME-*` |
| `test_chain.py` | section 8: digest mismatch, id cycle, depth and node limits, conflicting digests, output/input warning, no-network |
| `test_bundle.py` | section 9: `AWR-BUNDLE-*`, subject selection |
| `test_profiles.py` | section 10: L0/L1/L2, self-verification rejection, two-distinct-issuer rule, `AWR-L2-001` |
| `test_legacy.py` | section 12: both dialects, `AWR-LEGACY-001/002`, unsigned fields, issuance impossibility |
| `test_cli.py` | section 17: all five subcommands, exit codes 0/1/2/3, stream discipline, `--now`, `python -m awr` |

---

## Spec findings

Recorded rather than resolved silently. Each names the section, what is under-specified,
and the reading this implementation adopts — a second implementation that reads differently
will diverge on exactly these points.

**Status after three-way interoperability testing.** Findings 1, 2, 3, 4, 5, 8 and 9 are no
longer open questions: `SPEC.md` now states the answer, and in every case it is the reading
below. §12.1 writes out the AWR/1 rendering as a grammar and §12.2 fixes the key source and
the AWR/1 error codes (1, 2); §12 says the §4.3 restriction does not apply to AWR/1 and
requires the lenient re-parse (3); §4.3 says the restriction is on the *literal*, so `2340.0`
is `AWR-CANON-001` (4); §8.2's "Locating a parent" paragraph requires by-digest-then-by-id
resolution, `AWR-CHAIN-003` on a mismatch, and traversal through the mismatched parent so
that `AWR-CHAIN-004` is reachable (5); §10.4 gates the `AWR-PROFILE-*` codes on a requested
profile and states that the profile of an invalid or non-receipt document is `null` (8); §6.1
puts "which proof verified" in the `verifiedProof` member and forbids reporting a sibling
proof through a reason code (9). Two changes to this module came out of that pass: a
`VerificationVerdict` or `BlameAttestation` now reports `profile: null` rather than `"L0"`,
and a document that cannot be canonicalized no longer also reports `AWR-PROOF-006` — the
`AWR-CANON-*` code is the report, because §6.3 now reserves `AWR-PROOF-006` for a signature
that was actually checked.

### 1. §12 — the AWR/1 "pipe-delimited rendering" is not defined (blocking for interop)

Section 12 says the AWR/1 signature covers "a pipe-delimited rendering of
`credentialSubject`" and then specifies only what distinguishes dialect A from dialect B
(integer vs float rendering), plus NFC and code-point key order. It never gives the layout:
no key/value separator, no rule for nested objects or arrays, no escaping for values
containing `|` or `=`, no rendering for `null`, booleans or empty containers. Two blind
implementations could not agree, so AWR/1 verification was not independently implementable
from the spec text. **Now closed**: this reading is written out as a grammar in §12.1, and a
third implementation (the browser verifier), which had implemented a completely different
rendering, was corrected against it.

**Reading implemented** (`awr/legacy.py`): flatten to dotted paths (`a.b`, arrays by index
`c.0`), render each entry as `path=value`, join with `|`, sort entries by code point,
NFC-normalize both path components and string values; `null`/`true`/`false` literal;
integers `2340` (dialect A) or `2340.0` (dialect B); non-integer floats to 10 decimals per
Appendix D; empty objects and arrays contribute nothing. Values are **not** escaped, so a
value containing `|` is ambiguous under this reading.

### 2. §12 — where the AWR/1 public key comes from is unspecified

Appendix D says the AWR/1 `issuer.id` was `did:key:` plus the first 32 characters of the
base64 public key and "named a different key than the document embedded", so the DID cannot
yield a key and the embedding member is never named.

**Reading implemented**: `issuer.publicKeyJwk` (RFC 8037), else `issuer.publicKeyBase64`,
else a genuinely valid `did:key` in `issuer.id`; otherwise `AWR-KEY-001`.

### 3. §4.3 vs §12 — the number restriction's scope

§4.3 is scoped to "any AWR document that is to be signed", but §4.4 and §17 apply section 4
to arbitrary JSON through `canonicalize`/`digest`, and an AWR/1 document predates the
restriction — dialect B exists precisely because a legacy field could be `2340.0`. A parser
that refuses non-integer numbers cannot parse the AWR/1 documents §12 requires it to verify.

**Reading implemented**: parse strictly; if and only if the strict parse fails on
`AWR-CANON-001`/`002` and a lenient re-parse yields a document with an
`Ed25519Signature2018` proof, continue on the legacy path. `canonicalize`/`digest` enforce
§4.3 (a float is `AWR-CANON-001`, exit 1).

### 4. §4.3 — is `1.0` a "non-integer JSON number"?

Its value is an integer; its lexical form is not. §4.3's own rationale ("Languages also
differ on whether a parsed `1` is an integer or a double") implies the lexical reading.

**Reading implemented**: lexical. Any literal containing `.`, `e` or `E` is
`AWR-CANON-001`, and any Python `float` is refused on serialization. An implementation
using the value reading will accept documents this one rejects.

### 5. §8.2 — a digest-level cycle is not constructible, so `AWR-CHAIN-004` needs id resolution

Edges commit to the parent's exact bytes (§8.1), so a cycle in digests would be a SHA-256
fixed point. `AWR-CHAIN-004` is therefore only reachable for a resolver that also locates
parents by `id` — which is also the only way `AWR-CHAIN-003` ("parent digest mismatch
against the supplied parent") can fire, since a by-digest lookup can never mismatch.

**Reading implemented**: locate a parent by digest first, then by `id`; report
`AWR-CHAIN-003` when the by-id candidate's canonical digest differs (and do **not** count
that edge as resolved); detect cycles over document `id`s along the resolution path. A
verifier that resolves only by digest can never emit `AWR-CHAIN-004` or `AWR-CHAIN-003`.

### 6. §11.2 — three requirements with no code of their own

* §3.5 requires `method` with a non-empty `id` on a `BlameAttestation`; the registry has
  no `AWR-BLAME-*` code for it. → reported as `AWR-VDCT-003`.
* An `evidence` entry without `digestSRI` on a `BlameAttestation` → `AWR-VDCT-007`
  (registered under the verdict's section only).
* §3.4 constrains `policy.threshold` to a decimal string in `[0,1]` with no code. →
  `AWR-VDCT-002` (the registry's "decimal string in [0,1]" code), with the detail naming
  `policy.threshold`.
* A `settlement`/`stake` object that is present but malformed has no code either;
  `AWR-PROFILE-004` says only "no … binding present". → such an object does not count as a
  binding (so L2 reports `AWR-PROFILE-004`), and a malformed `amount` inside it is reported
  as `AWR-RCPT-002` / `AWR-VDCT-002`.

### 7. §11.2 `AWR-TIME-001` — no default skew, and no CLI flag for it

"beyond the caller's skew allowance" names no default, and §17 exposes no flag, so two
conformant CLIs can disagree about whether `AWR-TIME-001` appears for identical input.

**Reading implemented**: 60 seconds, `skew_seconds=` in the library API only.

### 8. §10.4 vs §11.1 — is an unmet profile an error?

`AWR-PROFILE-00x` carry no "(warning)" marker, so they are errors and make a document
invalid; but §10.4 requires reporting the codes of "each profile it evaluated and
rejected", which would make every plain L0 receipt invalid if those codes were promoted
unconditionally.

**Reading implemented**: evaluate L1/L2 always, report them in `profilesEvaluated`, and
promote to `reasons` only the profile the caller requested.

### 9. §6.1 — proof arrays contradict §11.1's `valid` rule

"at least one proof MUST verify and every proof present MUST be either valid or reported"
cannot coexist with "`valid` iff `reasons` has no error" if a failing proof's
`AWR-PROOF-006` lands in `reasons`.

**Reading implemented**: per-proof outcomes in `proofs` (with the failing proof's reasons
inside), promoted to the document's `reasons` only when no proof verified; `verifiedProof`
names the one that verified.

### 10. §5.1 / §11.2 — the `AWR-KEY-002` vs `AWR-KEY-004` boundary is undrawn

**Reading implemented**: a well-formed base58btc payload whose multicodec is a *known*
other public-key type (`x25519-pub`, `secp256k1-pub`, `p256/384/521-pub`, `rsa-pub`,
`bls12_381-g1/g2-pub`) is `AWR-KEY-004`; bad multibase, unknown multicodec, or wrong key
length is `AWR-KEY-002`.

### 11. §3.2 vs §11.2 — which code for a bad algorithm in `inputDigest`/`outputDigest`?

§3.2 mandates `AWR-CHAIN-002` for a digest reference with a non-`sha256` prefix, but
`inputDigest`/`outputDigest` are bare SRI strings, not reference objects, and §11.2 gives
them `AWR-RCPT-001`.

**Reading implemented**: `AWR-RCPT-001` for the two bare-string fields; `AWR-CHAIN-002` for
every reference object (`parents`, `verifiedWork`, `chain`, `blamedWork`, `evidence`,
`stake.slashingPolicy`).

### 12. §11.1 — whose `awrVersion` does the result report?

The document's or the implementation's is not stated.

**Reading implemented**: the document's, and `null` for an AWR/1 document (which has no
`awrVersion`).

### 13. §12 — which AWR/2 envelope checks apply to an AWR/1 document?

An AWR/1 document has no `awrVersion` and not the AWR/2 `@context`, so running §3.1 on it
would report `AWR-DOC-002`, `-003` and `-009` on every legacy document — while §12 says it
verifies.

**Reading implemented**: for AWR/1, check only that `credentialSubject` is an object
(`AWR-DOC-008`) plus the legacy key/proof rules; report `unsignedFields` and never treat
`id`, `type`, `issuer` or `hubInfo` as attested.

### 14. §11.2 `AWR-CANON-006` — no defined trigger

The registry calls it "implementation self-check failed" and §4.1 item 2 mentions it for a
canonicalizer that applies NFC, but no self-check is specified.

**Reading implemented**: `canonical_self_check` canonicalizes, re-parses the canonical bytes
with the strict parser and requires exact structural equality (types and code points
included), which catches normalization, member loss, number coercion and key reordering.
The canonicalizer is injectable so a harness can point the check at a candidate
implementation.

### 15. §9 — subject selection is unsatisfiable for a bundle with no `WorkReceipt`

"the single `WorkReceipt` not referenced as anyone's parent" has no answer for a
verdict-only bundle, and §9 forbids guessing.

**Reading implemented**: `AWR-BUNDLE-003`, including when an explicit `--subject` id is not
present in the bundle.

### 16. §17 — `--key` file format and the verdict channel are unspecified

Section 17 names `--key <file>` without a format, and offers `--parents` as the only way to
supply other documents even though L1/L2 need verdicts, which are not parents. Both are
resolved as documented under [CLI](#cli); a conformance harness driving a different
implementation may need a different key file.

### Two spec claims that check out

* §3.2's `sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=` is exactly SRI of
  `SHA-256("")`, so §3.3's "the digest of the empty byte string … is exactly the SRI value
  shown in §3.2" holds. Asserted in `test_reason_codes.py`.
* §5.1's "the resulting method-specific identifier is 48 characters and begins `z6Mk`" is
  correct with the multibase `z` counted: base58btc of `0xed 0x01 || 32 bytes` is always 47
  characters and always begins `6Mk` (verified over 3000 random keys), so the identifier is
  48 with the prefix. Asserted in `test_didkey.py`.

---

MIT, like the specification.
