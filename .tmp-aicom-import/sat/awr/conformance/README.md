# AWR/2 conformance

This directory holds the suite that decides whether an implementation conforms to
[`awr/SPEC.md`](../SPEC.md), and the real output of the last run.

It drives implementations through the **§17 CLI contract** and nothing else. It does not
import an implementation, read its source, or know what language it is written in. That is
the point: a format with one implementation has no interoperability, and a conformance
suite that can only measure its own author's code cannot tell a specification from a file
format.

The arbiter is not this runner and is not the reference implementation. It is
[`awr/vectors/index.json`](../vectors/index.json), which records, for each of the 118
vectors, the expected outcome, the **exact** set of reason codes that must be reported, and
the attack or divergence the vector exists to catch. When two implementations disagree, they
disagree with the manifest — which means one of them has a defect, or the specification is
ambiguous. The second case is the interesting one and is why this suite exists.

## The rule about levels

**A claimed conformance level means every vector in the manifest, not a subset.**

There is no "conforms except for chains", no "conforms for the vectors we run in CI", and no
partial credit. An implementation that reproduces 117 of 118 vectors does not conform to
AWR/2; it is an implementation with one known defect, and the honest way to describe it is
by naming the defect.

Three consequences, all enforced by `run.py`:

- `--only` narrows what is *run*, and when it is used the runner refuses to write
  `results.json` or `badge.json` and says so. A subset measurement is not a result.
- `unsupported` never means "waived". It means the measurement could not be taken: the
  implementation could not be driven at all, or an **OPTIONAL** §17 subcommand is not
  provided. An implementation that cannot be driven is reported as a row of `n/a` with the
  reason, not omitted — deleting the row would hide the difference between "we measured it
  and it passed" and "we never measured it".
- The only subcommand that may be absent is `issue`. §17 makes it OPTIONAL for verify-only
  implementations, so a browser verifier holding no private key is fully conformant without
  it. Every other subcommand missing is a conformance gap, and `verify` exiting 3 is
  recorded as a failure, not as `unsupported`.

## Running it

```sh
# every registered implementation
awr/conformance/run.py

# one of them, quietly
awr/conformance/run.py --impl rust --quiet

# the matrix as markdown, for a README
awr/conformance/run.py --markdown

# a subset while you debug (writes nothing)
awr/conformance/run.py --impl rust --only canonicalization
```

Standard library only, Python 3.9+. No third-party dependency, by design: someone who has
just written an AWR verifier in Go should be able to measure it without first installing a
Python toolchain around it.

Exit code `0` when no vector failed for any implementation, `1` otherwise. An
implementation that could not be driven does **not** turn the run red — it is an absent
measurement, not a failed one.

### What it produces

| File | Contents |
|---|---|
| stdout | the human-readable matrix; `--markdown` for a table you can paste |
| [`results.json`](results.json) | per implementation, per vector: `pass` / `fail` / `unsupported`, with every failed assertion spelled out, plus the resolved command and runtime version |
| [`badge.json`](badge.json) | [shields.io endpoint](https://shields.io/badges/endpoint-badge) format: `passed/total` over all (implementation, vector) pairs |

`results.json` and `badge.json` are **generated**. Do not hand-edit them; rerun the runner.

### Building the implementations first

```sh
# Rust
cd awr/rust && cargo build --offline        # or: cargo build

# Python reference — one dependency, `cryptography`
python3 -m pip install ./awr/reference/python
#   or, without installing:  export PYTHONPATH=$PWD/awr/reference/python

# browser verifier under Node — nothing to build
node docs/verifier/js/cli.js --help
```

## What each vector is held to

Per vector, by kind, all through §17:

**`document` / `bundle`** — `verify <file>` with the manifest's `--profile`, `--now`,
`--subject`, `--max-depth`, `--max-nodes` and `--parents`:

- the §17 exit code (`0` valid, `1` invalid);
- stdout is the §11.1 result JSON and carries all eight required members;
- `valid` equals the manifest's expectation, **and** equals "no `reasons` entry of severity
  `error`";
- the set of error codes is **exactly** `expectedCodes`, and the set of warnings exactly
  `expectedWarnings` — a missing code fails, and so does an extra one unless the manifest
  lists it in `allowedExtraCodes` because the specification does not settle the question;
- every reported code carries the severity SPEC.md §11.2 gives it, in the member §11.1
  assigns to that severity — a code has exactly one severity and exactly one home;
- §10.4 profile reporting: the highest profile satisfied, `null` for an invalid document,
  `null` for a document that is not a `WorkReceipt`;
- the §11.1 result invariants, asserted for **every** vector rather than recorded per
  vector, because §11.1 states them as rules about the result: `verifiedProof` is a function
  of the codes reported in both directions; `awrVersion` and `documentType` report what the
  *document* carries and are both `null` when it has no canonical form; `chain` counts §8.1
  `parents` edges and nothing else.

**`canonicalization`** — `canonicalize <file>` must emit bytes identical to the recorded
`.canonical` file *and* to the manifest's `canonicalHex`, with no trailing newline, and
`digest <file>` must print the recorded `digestSRI`. A negative vector must make the
canonicalizer itself exit `1`, name its reason code on **stderr**, and write nothing to
stdout.

**`proof`** — `hashdata` must print `proofConfigHash`, `transformedDocumentHash`, `hashData`
in the §6.2 step 6 order (**proof config first** — the most frequent interoperability error
in Data Integrity implementations), `canonicalize` must reproduce both byte strings the
hashes are taken over, and the secured document must verify.

**`issue` (OPTIONAL)** — a round trip: sign the probe subject with the RFC 8032 §7.1 TEST 1
seed as a bare 64-character hex key file (the interoperable form §17 fixes), then verify what
came out with the same implementation and require `valid: true` at L0. Exit `3` is recorded
as `unsupported` with the implementation's own explanation.

Every signing seed used anywhere in this suite is a published RFC 8032 §7.1 test vector. No
secret was created to measure conformance, and none of these keys confers authority.

## Current matrix

Generated by `awr/conformance/run.py` from the run recorded in `results.json`. **Do not edit
by hand** — rerun with `--markdown` and paste.

| vector group        | python-reference | rust    | browser-node |
|---------------------|------------------|---------|--------------|
| `canonicalization/` | 15/15            | 15/15   | 15/15        |
| `invalid/`          | 79/79            | 79/79   | 79/79        |
| `proof/`            | 1/1              | 1/1     | 1/1          |
| `valid/`            | 23/23            | 23/23   | 23/23        |
| **all vectors**     | 118/118          | 118/118 | 118/118      |

| section 17 subcommand | python-reference | rust | browser-node |
|-----------------------|------------------|------|--------------|
| `verify`              | yes              | yes  | yes          |
| `canonicalize`        | yes              | yes  | yes          |
| `digest`              | yes              | yes  | yes          |
| `hashdata`            | yes              | yes  | yes          |
| `issue` (OPTIONAL)    | yes              | yes  | not provided |

| implementation       | language                                       | crypto                                                   | command                                |
|----------------------|------------------------------------------------|----------------------------------------------------------|----------------------------------------|
| **python-reference** | Python 3.9+                                    | cryptography (PyCA) — Ed25519 and SHA-256 via OpenSSL    | `aimarket-hub/.venv/bin/python -m awr` |
| **rust**             | Rust 2021                                      | ed25519-dalek 2.2 + sha2 0.10; base58btc hand-written    | `awr/rust/target/release/awr`          |
| **browser-node**     | JavaScript (ES5-compatible CommonJS), Node 18+ | Node crypto (Ed25519, SHA-256); WebCrypto in the browser | `node docs/verifier/js/cli.js`         |

354 of 354 (implementation, vector) pairs pass; `browser-node` provides no `issue`, which
§17 permits. The three implementations do not share a canonicalizer, an Ed25519 primitive, a
base58btc encoder, or an author's assumptions — the Rust build was written from SPEC.md
without reading the Python source, which is the reason the specification had to say what it
means.

## Submitting a third-party result

You do not need commit access to measure your implementation, and you do not need to modify
this directory to run it.

**1. Run the suite against your build.** A descriptor is a claim about a command, not about
a codebase:

```sh
awr/conformance/run.py --add-impl '{
  "name": "acme-go",
  "language": "Go 1.23",
  "cryptoLibrary": "crypto/ed25519, crypto/sha256",
  "command": ["/path/to/your/awr"]
}' --impl acme-go
```

Descriptor fields are documented in [`implementations.json`](implementations.json) under
`$fields`. `commandCandidates` takes a list of argv prefixes and uses the first whose
executable exists; `env` adds environment variables; `optionalSubcommands` declares that you
implement no `issue`; `runtimeVersionCommand` is recorded as provenance and is **not** part
of §17.

**2. Read the failures.** Every failing assertion prints the expectation, the actual value
and the section of SPEC.md it comes from. Start with `canonicalization/` — an implementation
whose canonical bytes are wrong fails signatures everywhere else for reasons that look
unrelated.

**3. Send it.** Open an issue or a pull request containing:

- the descriptor you ran, verbatim;
- the `results.json` your run produced (it records the vector-by-vector outcome, your
  command, and your runtime version);
- the commit of this repository you ran against, and a link to your implementation;
- for anything you could not implement, **which vector and why** — a named gap is useful
  and a rounded-up number is not.

To be added to `implementations.json` and to the matrix above, an implementation must pass
**every** vector in the manifest. If yours does not yet, say so plainly and send the result
anyway: a vector that two independent implementations read differently is evidence that
SPEC.md is ambiguous there, and closing that ambiguity is worth more to this specification
than another green row.

**If you believe a vector is wrong**, say that instead of working around it. The manifest is
the contract and it can have bugs; each entry carries a `why` naming what it is for, and an
entry whose `why` does not survive contact with an independent implementation is the defect.

## Related

- [`awr/SPEC.md`](../SPEC.md) — normative. §17 is the CLI contract this runner speaks; §11
  is the result shape it checks.
- [`awr/vectors/`](../vectors/) — the vectors and the manifest that is the arbiter.
- [`awr/vectors/check_vectors.py`](../vectors/check_vectors.py) — holds the *manifest* to
  its own contract: §11.2 code coverage, generator determinism, no orphan vectors, and the
  two properties no CLI can show. It answers "is the manifest honest?"; this runner answers
  "which implementations conform?".
- [`awr/vectors/interop.sh`](../vectors/interop.sh) — the reverse direction: every
  implementation **issues**, all of them verify, and the issuers' bytes are compared. This
  runner hands fixed bytes to an implementation, which cannot catch an issuer that writes
  bytes nobody else accepts.
