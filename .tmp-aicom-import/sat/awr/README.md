# AWR — Agent Work Receipt

> 🌐 **English** · [Русский](docs/README.ru.md) · [Español](docs/README.es.md) · [Français](docs/README.fr.md) · [中文](docs/README.zh.md) · [Glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

[![AWR/2 conformance](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/alexar76/aicom/main/awr/conformance/badge.json)](conformance/)

**Version 2.0.0 · Draft standard, seeking implementation experience · MIT**

An AI output travels further than the system that produced it. It is pasted into a ticket,
forwarded to a customer, fed to another agent, entered into evidence. At every hop the same
three facts are lost: **what produced it**, **whether anyone checked it**, and **who is
answerable if it is wrong**.

AWR is a small, precisely canonicalized answer to those three questions, carried in a
standard envelope so that anyone can check it without asking anyone's permission.

- **Normative specification:** [`SPEC.md`](SPEC.md)
- **Test vectors:** [`vectors/`](vectors/) — 118 vectors, each with its expected outcome, its
  exact reason codes, and the attack it exists to catch
- **Conformance:** [`conformance/`](conformance/) — 3 implementations × 118 vectors, driven
  through the §17 CLI
- **Emitters:** [`emitters/`](emitters/) — the *producing* side. Everything else here reads
  receipts; an emitter **writes** one, so issuing a receipt costs one function call rather
  than assembling the document from the specification by hand. Python and a zero-dependency
  JavaScript build, which produce byte-identical documents.

## The three documents, the three questions

| Document | Question it answers |
|---|---|
| **`WorkReceipt`** | **What happened** — which model, over which input, producing which output, at what cost |
| **`VerificationVerdict`** | **Was it right, and who says so** — an independent verifier's signed judgement about a `WorkReceipt` |
| **`BlameAttestation`** | **Which hop failed** — attribution of a failure to one node of a multi-step work chain |

All three are [W3C Verifiable Credentials](https://www.w3.org/TR/vc-data-model-2.0/) secured
with a [W3C Data Integrity](https://www.w3.org/TR/vc-data-integrity/) proof
(`eddsa-jcs-2022`) over an [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) canonicalization,
issued by a [`did:key`](https://w3c-ccg.github.io/did-method-key/) identifier.

Verification therefore requires **no network access, no registry, no blockchain and no
issuer-specific software**. Any conformant W3C VC library can check an AWR document, and so
can a 100-line implementation.

The second document is the one that is easy to miss. A judge with no identity is a rubber
stamp: `VerificationVerdict` is a separate signed credential precisely so that the *verifier*
has a `did:key` too, and therefore something to lose. AWR makes claims **attributable**; it
does not make them true (SPEC.md §13.7).

## What AWR is not

It does not prove a model was not fine-tuned, detect AI-generated content, replace
watermarking, define a reputation algorithm, define a payment or staking mechanism, or
establish who is permitted to issue documents. It carries no economics of its own: payment,
staking and slashing appear only as **optional references** (§10.3), so the format can be
adopted by parties who will never settle a payment.

Neighbouring standards each solve a different problem, and AWR profiles rather than replaces
them (§1.1, §16): C2PA binds provenance to media assets; VC gives the right envelope but says
nothing about what an AI work claim contains; OpenTelemetry GenAI describes unsigned,
operator-owned telemetry; eval tooling emits judge scores with no identity for the judge.

## The assurance ladder

Levels are **additive**, and a level is **never granted by self-assertion** — a document may
carry an `awrProfile` hint and a verifier must ignore it (§3.3, §10).

| Level | Name | What it requires | What it costs |
|---|---|---|---|
| **L0** | Receipt | one valid `WorkReceipt` | an Ed25519 keypair |
| **L1** | Verified | L0 + a valid `VerificationVerdict` whose issuer **differs** from the receipt's issuer | a second party willing to sign a judgement |
| **L2** | Accountable | L1 + **two** verdicts from **distinct** issuers, and an accountability binding (`settlement` on the receipt, or `stake` on the verdicts) | whatever your settlement layer costs |

**Adopting L0 requires no payment, no blockchain, no account and no network.** Not "is cheap"
— requires none of them. You generate an Ed25519 keypair, sign a JSON object, and anyone can
verify it offline, forever, with no call to us and no registration with anyone. L0 is the
adoption floor and is deliberately free.

Two details that matter more than they look:

- A verdict of `fail` or `inconclusive` **still satisfies L1**. L1 asserts *that an
  independent party judged the work*, not that the judgement was favourable (§10.2).
  `inconclusive` is the honest outcome when a verifier could not reach a judgement, and
  suppressing it is what turns verifiers into rubber stamps (§3.4).
- At L2 a verifier **must not** contact a chain or an RPC endpoint to check a binding. It
  checks that the binding is present, well-formed and signed, and reports `AWR-L2-001`
  (warning) stating that on-chain existence was not checked (§10.3). Anything stronger would
  put a network dependency in the middle of an offline format.

## 60-second quickstart

Nothing here contacts a network. Run it from the repository root.

### 1. Verify a supplied receipt — zero install

The browser verifier is a plain CommonJS module with a §17 CLI adapter, and Node's crypto is
built in, so this needs nothing but `node`:

```sh
node docs/verifier/js/cli.js verify awr/vectors/valid/receipt-minimal-l0.json --profile L0
```

```json
{
  "valid": true,
  "awrVersion": "2.0.0",
  "documentType": "WorkReceipt",
  "profile": "L0",
  "reasons": [],
  "warnings": [],
  "verifiedProof": 0
}
```

(Abridged: §11.1 sets a floor of eight required members, not a closed set, and each
implementation adds a few of its own — a consumer must ignore members it does not know.)

Exit code `0` means valid, `1` means invalid **with a reason code** — see §11 for the
registry and §17 for the exit codes. Try it on a document that has been tampered with:

```sh
node docs/verifier/js/cli.js verify awr/vectors/invalid/tampered-issuer-name.json
# → "valid": false, reasons: [{"code": "AWR-PROOF-006", ...}]   exit 1
```

That file is byte-for-byte the receipt you just verified, with **one field** rewritten:
`issuer.name` went from `example-hub` to `trusted-national-audit-office`. The signature is
unchanged and the DID is unchanged. `name` carries no trust weight (§3.1) — but it is the
field a user interface actually shows, so §13.1 puts it inside the signature anyway. A field
outside the signature is a field an intermediary chooses.

### 2. Issue one

The reference implementation has exactly one dependency, the Ed25519 primitive:

```sh
python3 -m pip install ./awr/reference/python     # or: export PYTHONPATH=$PWD/awr/reference/python
```

The key file is a bare 64-character hex Ed25519 seed on one line — the interoperable form
§17 fixes. **The seed below is RFC 8032 §7.1 TEST 1: it is published in an IETF standard,
confers nothing, and must never be used for a real document.** Generate your own with
`openssl rand -hex 32`.

```sh
printf '9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60\n' > issuer.key

cat > subject.json <<'EOF'
{
  "work": {
    "modelId": "my-model@my-vendor",
    "capability": "urn:example:capability:summarise",
    "startedAt": "2026-08-01T10:15:28Z",
    "completedAt": "2026-08-01T10:15:30Z",
    "status": "succeeded"
  },
  "inputDigest": "sha256-ntYicspG8WqhUyawUlC4dTFMnG08+B5Wol6Kci8rnNo=",
  "outputDigest": "sha256-z3ZSXO7HDKRUMIrd+zvSig+hNUcug/XPmO+faJPgJak="
}
EOF

python3 -m awr issue subject.json --key issuer.key --type WorkReceipt > receipt.json
```

`inputDigest` and `outputDigest` are digests of **your application's payload bytes**, not of
AWR documents — you choose the serialization and should document it (§3.3). The two above are
real SHA-256 digests of the sample payloads recorded in
[`vectors/index.json`](vectors/index.json).

### 3. Verify what you just issued — in an implementation that did not write it

```sh
node docs/verifier/js/cli.js verify receipt.json --profile L0     # → valid: true, profile L0
awr/rust/target/debug/awr        verify receipt.json --profile L0 # → valid: true, profile L0
```

That is the whole of L0. You now hold a document that a stranger can check in a browser tab,
offline, in two years, without you.

## Conformance

An implementation conforms if it reproduces the canonical bytes, rejects every negative
vector with its recorded reason code, implements the §17 CLI, reports results in the §11.1
shape, and never touches the network while verifying (§17).

A claimed level means **every** vector in the manifest, not a subset — see
[`conformance/README.md`](conformance/README.md).

| vector group        | python-reference | rust    | browser-node |
|---------------------|------------------|---------|--------------|
| `valid/`            | 23/23            | 23/23   | 23/23        |
| `invalid/`          | 79/79            | 79/79   | 79/79        |
| `canonicalization/` | 15/15            | 15/15   | 15/15        |
| `proof/`            | 1/1              | 1/1     | 1/1          |
| **all vectors**     | 118/118          | 118/118 | 118/118      |

| implementation | language | crypto | `issue`? |
|---|---|---|---|
| [**python-reference**](reference/python/) | Python 3.9+ | cryptography (PyCA) — Ed25519 via OpenSSL | yes |
| [**rust**](rust/) | Rust 2021 | ed25519-dalek 2.2 + sha2 0.10; base58btc hand-written | yes |
| [**browser-node**](../docs/verifier/) | JavaScript (CommonJS), Node 18+ | Node crypto; WebCrypto in the browser | no — verify-only, which §17 permits |

Generated by [`conformance/run.py`](conformance/run.py); the machine-readable form is
[`conformance/results.json`](conformance/results.json) and the badge endpoint is
[`conformance/badge.json`](conformance/badge.json). Rerun with `--markdown` and paste; do not
edit the tables by hand.

The three implementations share no canonicalizer, no Ed25519 primitive, no base58btc encoder
and no author's assumptions — the Rust build was written from `SPEC.md` without reading the
Python source, which is the reason the specification had to say what it means. Where it did
not, the vectors' `specFindings` records what was closed and how.

To measure your own implementation, see
[**Submitting a third-party result**](conformance/README.md#submitting-a-third-party-result).
You need no commit access, and an implementation that fails a vector is more useful to this
specification than another green row — a vector two independent implementations read
differently is evidence that `SPEC.md` is ambiguous there.

## Layout

| Path | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | **Normative.** The specification. Everything else is derived from it |
| [`vectors/`](vectors/) | The vectors, `index.json` (the arbiter), the generator, and the checker that holds the manifest to its own contract |
| [`conformance/`](conformance/) | The §17 CLI runner, the implementation registry, the real `results.json`, the badge |
| [`reference/python/`](reference/python/) | Reference implementation |
| [`rust/`](rust/) | Independent implementation, written from the spec |
| [`schemas/`](schemas/) | JSON Schema, a convenience for tooling. **Not** normative: where a schema and `SPEC.md` disagree, the schema is a bug (Appendix B) |
| [`adoption/`](adoption/) | Adoption metric, the MCP trust-label profile, outreach drafts |
| [`CHANGELOG.md`](CHANGELOG.md), [`VERSION`](VERSION), [`LICENSE`](LICENSE) | 2.0.0, MIT |

The browser verifier lives at [`../docs/verifier/`](../docs/verifier/) because it is also a
deployed page; [`js/cli.js`](../docs/verifier/js/cli.js) is the §17 adapter around it, so the
code a stranger's browser runs is the code the matrix measures.

## The name and the namespace are ours, not yours

Two things in AWR are this project's arbitrary choices rather than technical requirements, and
they are stated plainly here so that nobody has to adopt our branding to adopt the format:

**The name "AWR".** It stands for Agent Work Receipt. Nothing depends on it.

**The namespace URI `https://verify.modelmarket.dev/ns/awr/v2`.** It is a JSON-LD context
identifier and an opaque string to a verifier: §3.1 requires that a verifier **must not
dereference it** (§13.5), so the host serves no role in verification and could stop resolving
tomorrow without invalidating a single document.

Changing the namespace is **one line per implementation** — a single constant, in one place,
in each:

| Where | Constant |
|---|---|
| [`SPEC.md`](SPEC.md) | the `Namespace:` header, and §3.1 |
| [`reference/python/awr/documents.py`](reference/python/awr/documents.py) | `AWR_CONTEXT` |
| [`rust/src/lib.rs`](rust/src/lib.rs) | `AWR_CONTEXT` |
| [`../docs/verifier/js/verifier.js`](../docs/verifier/js/verifier.js) | `AWR2_CONTEXT` |
| [`schemas/*.json`](schemas/) | the `$id` and `$ref` URIs (tooling only, non-normative) |

Be precise about the scope of that claim, because a renaming that half works is worse than
none. The **namespace** is one line. The **name** is not, wherever it has become wire format:
the property names `awrVersion`, `awrProfile` and `awrBundle` (§3.1, §3.3, §9) and the
`AWR-*` reason-code prefix (§11.2) all spell the name out, and changing those changes the
documents on the wire and every consumer that reads them. A fork wanting a different name
should change the namespace URI and keep the property names — they are just identifiers, and
§11.1 fixes reason codes as **stable across versions** for exactly this reason.

`AWR` originates in the AIMarket ecosystem and is the format its hub, verification tier and
settlement bridge exchange. It is specified, versioned, tested and licensed independently, has
no dependency on any AIMarket component, and names no AIMarket endpoint normatively (§1.4,
§16).

## Status

This is not an IETF RFC and not a W3C Recommendation. It follows RFC style for precision and
normatively depends on published standards rather than restating them.

**Implementation experience is solicited.** The most useful thing you can send is a vector
that two implementations read differently. See
[`conformance/README.md`](conformance/README.md).

MIT, © 2026 AI-Factory Project Contributors. See [`LICENSE`](LICENSE).
