# AWR/2 test vectors

These vectors are a **contract**, not a gallery of correct examples. Every one of the 106
entries in [`index.json`](index.json) carries the outcome it must produce: `valid` or
`invalid`, the exact set of reason codes that must be reported, the warnings that must be
reported, the profile it is meant to be checked at, and a one-line `why` naming the attack
or the interoperability divergence it exists to catch.

**The rule of this directory: a vector is only added together with its expected outcome.**
A file with no manifest entry is not a vector — [`check_vectors.py`](check_vectors.py)
fails on an unreferenced file, because a document nobody has committed an outcome for
cannot fail informatively. A manifest entry with no `why` is refused by the generator for
the same reason: if no one can name the attack or the divergence the vector catches, it is
noise that will one day be "fixed" by adjusting the expectation.

| Kind | Entries | What it holds |
|---|---|---|
| `valid/` | 22 | Documents and bundles that MUST verify, including the two AWR/1 legacy dialects |
| `invalid/` | 68 | One vector per reachable error code of SPEC.md §11.2, plus the specific attacks §13 names |
| canonicalization | 15 | Inputs plus their exact canonical bytes (9 positive, 6 negative) |
| proof | 1 | The Appendix A worked example, every intermediate value recorded separately |

---

## Regenerate

```sh
cd <repo root>
PYTHONPATH=awr/reference/python \
  aimarket-hub/.venv/bin/python awr/vectors/generate.py
```

`generate.py` writes every file in this directory except `README.md` and
`check_vectors.py`, including `index.json`. **Do not hand-edit a vector or the manifest** —
change the generator and re-run it. A hand edit is detected: the checker re-runs the
generator into a temporary tree and diffs it against this one.

The generator is deterministic by construction. There is no wall-clock read and no
randomness in it: every timestamp is a literal, every identifier comes from a counter, the
payload bytes are literals, and Ed25519 is deterministic (RFC 8032). Two runs produce
byte-identical trees, which is what makes a diff in this directory reviewable.

Every cryptographic value in every file here was **computed by running the reference
implementation**. No signature, digest, hash or canonical byte string was typed by hand.

Seven vectors carry a defect no signer can produce, because the defect means the document has
no canonical form to sign: a non-integer number, an integer-valued float literal (`2340.0`),
an integer at 2^53, a lone surrogate, a `price.amount` that is a JSON number, a duplicate
object member, and a trailing comma. Five of them are built by signing a variant that carries
a string sentinel in the defective position and then substituting the defect into the emitted
text; two are raw-text edits of a genuinely signed document, because no JSON serializer can
emit a duplicate member or a trailing comma. Each carries a `note` in the manifest saying
exactly what was signed. Nothing anywhere here is a placeholder value.

## Check

```sh
cd <repo root>
PYTHONPATH=awr/reference/python \
  aimarket-hub/.venv/bin/python awr/vectors/check_vectors.py
```

The checker walks `index.json`, drives the §17 CLI once per vector, and asserts the outcome
and the code set match. Useful flags: `--only SUBSTRING` (one vector or a family),
`--skip-regenerate` (skip the determinism phase, which costs two generator runs), `-v`.

Point it at any conformant implementation — the `--impl` command is invoked with the §17
subcommands and the vector paths, resolved relative to this directory:

```sh
(cd awr/rust && cargo build --offline)          # the independent Rust implementation
PYTHONPATH=awr/reference/python aimarket-hub/.venv/bin/python \
  awr/vectors/check_vectors.py --impl "$PWD/awr/rust/target/debug/awr"

# the browser verifier, through its §17 adapter — the same file the page loads
PYTHONPATH=awr/reference/python aimarket-hub/.venv/bin/python \
  awr/vectors/check_vectors.py --impl "node $PWD/docs/verifier/js/cli.js"
```

The phases that use the reference *library* rather than the CLI — the AWR-CANON-006
demonstration and the Ed25519 cross-check of the worked example's signature — are then
skipped and reported as skipped rather than silently passing.

## The other direction

`check_vectors.py` hands fixed bytes to an implementation and checks what comes back. That is
half of interoperability: it cannot catch an **issuer** that writes bytes nobody else accepts,
and a format with one working issuer is not a format. [`interop.sh`](interop.sh) closes the
loop — each implementation that has an `issue` subcommand issues a `WorkReceipt` with NFD
strings and a non-BMP object key, a second receipt chained to it by digest, a
`VerificationVerdict` and a `BlameAttestation`; every implementation then verifies all four at
L0 and L1; and finally the issuers' bytes are compared to each other.

```sh
awr/vectors/interop.sh
```

Given the same key, `--id` and `--now`, two conformant issuers must produce **byte-identical
documents including the `proofValue`**, because Ed25519 is deterministic (RFC 8032). That
equality is a much stronger statement than "it verifies": it says the two canonicalize
identically, over a document whose strings and keys were chosen so that an NFC normalization
or a code-point key sort would change them.

What the checker asserts, beyond the per-vector outcome:

- **exit codes** per §17: `0` valid, `1` invalid with a result produced;
- **`valid` iff no error reason** (§11.1) — checked against the result the implementation
  itself printed, so an implementation cannot report a code and still claim validity;
- **severity** of every reported code against the §11.2 table, parsed out of `SPEC.md`;
- **`SPEC.md` §11.2 vs the reference registry** — the code sets and every severity must
  agree, so a code the reference forgot to transcribe is a failure here;
- **coverage** — every code in §11.2 is either exercised by a vector or declared in
  `unreachableCodes`/`partiallyCoveredCodes` with a stated reason;
- **test keys** — every signing seed in the manifest is a published RFC 8032 §7.1 test
  vector (see below);
- **`codeIndex`** in the manifest matches the vectors it indexes;
- **no orphan files**, in either direction.

## When a vector fails

A failure means one of four things, and the order to consider them in is:

1. **the implementation** is wrong — the ordinary case;
2. **the vector** is wrong — it does not contain the defect it claims to;
3. **the manifest** is wrong — the vector is right and the expectation is not;
4. **the specification** is wrong, ambiguous or silent — the interesting case.

Work out which before changing anything. **Never adjust the manifest to make a failing
implementation pass.** That converts the contract into a description of one
implementation's behaviour, which is precisely what this directory exists to prevent. If
the specification turns out not to decide the question, the resolution is an entry in
`specFindings` in `index.json` plus, where two readings are both conformant,
`allowedExtraCodes`/`allowedExtraWarnings` on the affected vector — narrow permission,
recorded with its reason, rather than a silently weakened assertion.

A permission recorded that way is a **holding position, not an outcome**. The right end state
is a sentence in `SPEC.md` that decides the question and a permission withdrawn: that is what
happened to the six `AWR-PROOF-006` permissions once §6.3 said which code to use, and the
vectors then caught all three implementations disagreeing. When you close a finding, say so in
its `closedBy` and delete the permission in the same edit.

The vectors are laid out to localise a failure rather than merely report one:

- if `canonicalization/*` fails, the canonicalizer is wrong and nothing else can be trusted;
- if every canonicalization vector passes and `proof/worked-example` fails, the defect is in
  the §6.2 proof steps. `hashdata` prints `proofConfigHash`, `transformedDocumentHash` and
  `hashData` separately, so the failing step is one of three rather than "a signature did
  not verify";
- if both pass and `invalid/*` vectors are accepted, the semantic checks of §3 and §8 are
  missing or too weak.

## Manifest entries

`index.json` documents every field in its own `fields` object; the load-bearing ones:

| Field | Meaning |
|---|---|
| `expect` | `valid` / `invalid` — the value of `valid` in the §11.1 result |
| `expectedCodes` | Error codes that MUST be reported. The set is **exact**: an extra code is a failure unless listed in `allowedExtraCodes` |
| `expectedWarnings` | Warning codes that MUST be reported, same exactness rule |
| `allowedExtraCodes` / `allowedExtraWarnings` | Codes an implementation MAY additionally report because the specification does not settle the question. Every use is explained by an entry in `specFindings` |
| `profile` | Passed as `--profile`. `null` means run with no profile argument and assert nothing about the reported profile |
| `now` | Passed as `--now`, so `AWR-TIME-001`/`002` are deterministic |
| `supporting` | Files to pass as `--parents`: chain parents, verdicts, the receipts a `BlameAttestation` refers to |
| `subjectId` | The bundle subject, for the explicit-argument branch of §9. Passed as `--subject`, which §17 now names normatively — a harness that has to guess the flag cannot drive two implementations from one manifest |
| `maxNodes` / `maxDepth` | Passed as `--max-nodes` / `--max-depth` (§17), overriding the §8.2 defaults of 1024 and 64. This is what makes the node-count half of `AWR-CHAIN-005` reachable without a 1025-document bundle |
| `why` | Mandatory. The attack or divergence caught |
| `note` | How the file was built when signing alone could not produce it, and what was actually signed |
| `canonicalFile` / `canonicalHex` / `canonicalLength` / `digestSRI` | Canonicalization vectors: the expected bytes as a file **and** as hex, so a mismatch is diagnosable byte-for-byte from the manifest alone |

## Test keys

Every document here is signed with an Ed25519 key whose seed is one of the **published test
vectors of RFC 8032 §7.1**. They were chosen precisely because they are already in an IETF
standard: writing this vector set created no secret and disclosed none, and the seeds can be
printed in a manifest without a warning being a lie.

```
hub         9d61b19d…  RFC 8032 §7.1 TEST 1          did:key:z6Mktwupdm…  issues WorkReceipts
verifierA   4ccd089b…  RFC 8032 §7.1 TEST 2          did:key:z6MkiaMbhX…  issues verdicts
verifierB   c5aa8df4…  RFC 8032 §7.1 TEST 3          did:key:z6MkwSD8dB…  issues verdicts
attributor  f5e5767c…  RFC 8032 §7.1 TEST 1024       did:key:z6Mkh7U7jB…  issues blame
upstream    833fe624…  RFC 8032 §7.1 TEST SHA(abc)   did:key:z6MkvLrkgk…  issues upstream hops
```

**These keys confer nothing and MUST NOT be used to issue a real AWR document.** A verifier
must not treat these DIDs as trustworthy; anyone can sign anything with them. The checker
enforces the rule in the only direction it can: a seed in `index.json` that is *not* a
published RFC 8032 test vector is a failure, so a fresh secret cannot quietly become a test
fixture.

## The worked example (Appendix A)

`proof/worked-example.json` records one complete signing operation over
`valid/receipt-minimal-l0.json`: the key, the unsecured document, the proof options, both
canonical byte strings as text *and* as hex, both hashes, `hashData`, the raw signature and
the `proofValue`. The five companion files are what the §17 CLI is run against.

```
proofConfigHash          79a4102bee5e3580a76cfa00c761a3f2b00efde8dc94106c71693b21b5398f42
transformedDocumentHash  dbdfb02c2a15fcba66147b54b705105df41c0f55aee27a555a3f9a1c9935e7aa
hashData                 <proofConfigHash> || <transformedDocumentHash>     (§6.2 step 6)
```

Reproduce it with the CLI alone:

```sh
cd awr/vectors
awr hashdata     proof/worked-example-secured.json      # the three hex values, in order
awr canonicalize proof/worked-example-unsecured.json    # transformedDocument
awr canonicalize proof/worked-example-proof-config.json # canonicalProofConfig
awr verify       proof/worked-example-secured.json --now 2026-07-31T12:00:00Z
```

The order in §6.2 step 6 is the most frequent Data Integrity interoperability error, and
both halves are 32 bytes, so a reversed concatenation is indistinguishable by length.
`invalid/hashdata-halves-swapped.json` is a **genuine** signature over the reversed
`hashData`: it is a correct Ed25519 signature by the right key over the wrong 64 bytes, so
an implementation that concatenates in the wrong order accepts it and every conformant one
reports `AWR-PROOF-006`. The checker additionally asserts that the worked example's
signature does *not* verify over the reversed bytes, which is what makes that vector
meaningful rather than decorative.

## Coverage of §11.2, and what is not covered

65 of the 66 reason codes in §11.2 are exercised by a vector. The gaps are declared in the
manifest rather than left to be discovered:

- **`AWR-CANON-006`** is unreachable from any input. It reports that the implementation's
  *own* canonicalizer is lossy (§4.1 item 2, §4.4), which is a property of the code, not of
  a document. `canonicalization/no-nfc-normalization` and `valid/receipt-decomposed-unicode`
  are what make a normalizing implementation fail — it produces canonical bytes different
  from the recorded ones and then fails a signature its own issuer made. The checker proves
  the code itself fires by pointing the reference self-check at a deliberately NFC-applying
  canonicalizer, and fails if that canonicalizer is accepted.
`AWR-CHAIN-005` used to be half-covered: the depth limit was exercised (66 receipts against
the default 64) and the node-count limit, which shares the code, was not, because a vector
for it needed 1025 documents. §17 now defines `--max-nodes`, so
`invalid/chain-node-limit-exceeded` breaches a limit of two with a four-hop chain, and
`partiallyCoveredCodes` is empty.

`index.json` also carries `specFindings`: 17 places where the specification was ambiguous,
incomplete or self-contradictory, each with the section, the problem, and what was done about
it. Twelve now say **SETTLED IN THE SPEC** and name the text that settles them; they are the
output of this work that matters most, because a vector set that quietly picked a reading
would have hidden them. Five vectors still carry `allowedExtraCodes`/`allowedExtraWarnings`,
and each one is a case where §8.3 or §11.1 deliberately permits two behaviours rather than
leaving them undecided:

- `invalid/number-non-integer`, `invalid/number-integer-valued-float`,
  `invalid/number-integer-2pow53` and `invalid/price-amount-json-float` permit the
  field-level code (`AWR-RCPT-004`/`AWR-RCPT-002`) alongside the required `AWR-CANON-*` one.
  §11.1 says a verifier reports every error **it can determine**, and a strict lexical parser
  never sees the field: the Rust build reports both, the reference and the browser verifier
  report only the canonicalization code, and §11.1 now states that both are conformant.
- `invalid/chain-cycle-three-node` permits `AWR-CHAIN-007`, because §8.3 makes performing the
  input/output binding check a SHOULD while making the report of its outcome a MUST.

## Cross-implementation status

Three implementations, all driven through the §17 CLI, all passing every vector:

| Implementation | Written from | Vectors | Assertions |
|---|---|---|---|
| `awr/reference/python` | the spec, alongside it | 106 / 106 | 3450 |
| `awr/rust` | `SPEC.md` alone, blind | 106 / 106 | 3449 |
| `docs/verifier` (browser, via `js/cli.js`) | the spec, for the page | 106 / 106 | 3447 |

The Rust and browser counts are lower only because two phases need the reference *library*
rather than a CLI (the `AWR-CANON-006` demonstration and the Ed25519 cross-check of the
worked example's recorded signature); the checker reports them as skipped instead of silently
passing.

Getting there took 12 spec changes and 11 implementation fixes. The first three-way run
produced **16 differing outcomes for the Rust build and 109 for the browser verifier**, and
every one was traced to a cause before anything was changed:

- **The browser verifier had a §4.3 hole of exactly the AWR/1 kind.** It checked numbers
  after `JSON.parse`, where `2340` and `2340.0` are the same IEEE-754 double, so it accepted
  `2340.0`, canonicalized it to `2340`, and would have verified a signature over bytes no
  issuer produced. §4.3 now says the restriction is on the literal and that the check must be
  lexical; the file enforces it in its pre-parse scanner, and
  `invalid/number-integer-valued-float` plus `canonicalization/neg-integer-valued-float` hold
  every implementation to it.
- **The browser verifier reported error-severity codes at warning severity** —
  `AWR-PROFILE-001` on every receipt verified without `--profile`, `AWR-PROOF-006` to say
  which proof of an array verified, `AWR-BUNDLE-002` for a bundled document that was itself
  invalid, `AWR-CHAIN-001` for AWR/1 parent strings. §11.1 now states that a code has exactly
  one severity, §6.1 puts "which proof verified" in `verifiedProof`, and §10.4 gates the
  profile codes on a requested profile.
- **The browser verifier implemented a different AWR/1 rendering entirely** (`key:value`
  pairs, JSON-quoted nested blobs, Python-style `True`/`None`) and therefore verified neither
  AWR/1 vector. §12.1 writes the rendering out as a grammar and §12.2 fixes the key source
  and the AWR/1 error codes; all three now agree.
- **The Rust build reported `profile: "L0"` (once `"L1"`) on 14 documents it had declared
  invalid**, and `"L0"` on AWR/1 documents whose `type` is outside the signature. §10.4 now
  states the three cases outright.
- **`AWR-CHAIN-004` was dead code in two implementations**, because every constructible cycle
  runs through an edge whose digest does not match — an edge commits to the parent's exact
  bytes, so a digest cycle would be a SHA-256 fixed point — and a resolver that declines to
  walk past a failed edge never sees one. §8.2's new "Locating a parent" paragraph requires
  the traversal, and cross-receipt `AWR-CHAIN-006` with it.
- **The three implementations disagreed three ways about `AWR-PROOF-006`** when an earlier
  step made the signature check impossible. §6.3 now reserves the code for a signature that
  was actually checked, requires the preventing step's code instead, and adds a fail-closed
  rule; the `allowedExtraCodes` permission that had been papering over it is withdrawn.

Reverse-direction interoperability is checked separately from the vectors, because a
one-directional check proves nothing: the Rust build and the reference each **issue** a
`WorkReceipt` with NFD strings and a non-BMP object key, a second receipt whose `parents` edge
commits to the first, a `VerificationVerdict` and a `BlameAttestation`, and each set is then
verified by all three implementations at L0 and L1. Given the same key, `--id` and `--now`,
the two issuers produce **byte-identical documents down to the `proofValue`** — Ed25519 is
deterministic (RFC 8032), so that is the strongest available statement that both canonicalize
identically.

## Adding a vector

1. Add it to `generate.py`, next to the vectors that share its section.
2. Give it an expected outcome and a `why` in the same edit. The generator refuses a vector
   with no `why`, and refuses one that expects `invalid` while naming no code.
3. Regenerate, then run the checker. If the new vector does not behave as claimed, work
   through the four-way diagnosis above before touching the expectation.
4. If it closes a spec ambiguity, add the finding to `SPEC_FINDINGS` in the generator and
   reference the vector from it.
