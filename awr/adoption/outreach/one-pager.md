DRAFT — NOT SENT. Requires the maintainer to review and send.

# AWR/2 — Agent Work Receipt

A signed, offline-verifiable claim about work an AI system performed. Draft standard, MIT,
`awr/SPEC.md` v2.0.0.

## The three questions

| Document | Question it answers |
|---|---|
| `WorkReceipt` | **What happened** — which model, over which input digest, producing which output digest, at what cost, and whether it succeeded (`succeeded`/`failed`/`refused`/`timeout`/`partial`) |
| `VerificationVerdict` | **Was it right, and who says so** — a verifier's signed judgement about one specific receipt, bound to it by digest. The document names the key that signed it; whether that key is a different *party* is something only the consumer can decide (see below) |
| `BlameAttestation` | **Who says which hop failed** — a signed, method-named attribution of a failure to one node of a multi-step chain, including exoneration (`failureClass: upstream-input`). AWR does not compute the attribution and does not check it beyond reachability; it makes whoever asserts it nameable |

All three are W3C VC 2.0 credentials with a Data Integrity proof (`eddsa-jcs-2022`) over an
RFC 8785 canonicalization, issued by a `did:key`. AWR invents the claim set and nothing else.

## Why the standards you already have do not answer them

- **C2PA / Content Credentials** binds provenance to media assets and is anchored in file
  formats. It does not describe a chain of agent invocations over structured input. It is
  complementary: a C2PA assertion may carry an AWR document's `id` and `digestSRI`.
- **OpenTelemetry GenAI semantic conventions** describe telemetry — unsigned, operator-owned,
  meaningful inside the emitting organisation's observability stack. Nobody downstream can
  check a span. Also complementary: `gen_ai.request.model` maps to `work.modelId`, and a span
  may carry a receipt `id` as an attribute.
- **Judge / eval JSON**, *where it is unsigned*, carries a score with no identity for the judge
  and no way to compare two judges' claims about the same output. This is the gap AWR aims at.
  We have not surveyed the eval and observability market and make no claim about any specific
  product — some may already sign or scope their output differently (**TO VERIFY** per vendor
  before this line is used in a conversation with one).
- **W3C Verifiable Credentials** is the right envelope and says nothing about what an AI work
  claim contains. AWR is a profile of it, not a competitor.

## What adopting L0 costs

An Ed25519 keypair and a JSON document.

No payment, no chain, no account, no network, no registry, no revocation list, no schema
fetch, no DID resolution. §13.5 forbids a conformant verifier from dereferencing anything
during verification — including `@context`.

Measured in this repository on 2026-07-31, with the commands that reproduce it:

```bash
PYTHONPATH=awr/reference/python python -c \
  "import json; from awr import jcs; \
   print(len(jcs.canonicalize(json.load(open('awr/vectors/valid/receipt-minimal-l0.json')))))"
# 980
wc -l awr/reference/python/awr/*.py | tail -1
# 3839 total
```

The smallest L0 receipt in the shipped vector set, `awr/vectors/valid/receipt-minimal-l0.json`,
canonicalizes to **980 bytes** — of which 510 (52%) are contributed by `@context`, `type` and
`proof`, and 369 by the `proof` block alone. The Python reference implementation is **3839
lines** with exactly one third-party dependency (`cryptography>=41`, for Ed25519), and **no
module in the package imports a networking library**: verified by auditing every `import`
statement in `awr/reference/python/awr/*.py`, which resolve to the standard library plus
`cryptography`. That is a property of the source, not an enforced sandbox — there is no runtime
egress assertion.

Both the Python and the Rust tree are under active development in this repository, so re-run
the commands above before quoting either number.

## The one thing AWR has that the alternatives do not

**The verifier gets an identity, so a verdict is attributable.**

A `VerificationVerdict` is signed by the judge's own `did:key`, references the receipt by
digest as well as identifier, and names its method by an opaque id. Four consequences that a
convention over unsigned JSON cannot produce:

1. A consumer **that recomputes the digest** can detect a favourable verdict detached from the
   work it judged and re-attached to different work carrying the same identifier (§13.2).
   Without that recomputation by the consumer the substitution is undetectable and every
   signature check still passes — this is the primary attack on the format, not a corner case.
2. Self-issuance is structurally detectable: profile L1 requires the verdict's issuer DID to
   differ from the receipt's issuer DID, and reports `AWR-PROFILE-002` when it does not. Note
   what that is and is not: two distinct DIDs are two distinct **keys**. One operator holding
   two keypairs satisfies L1, and AWR has no mechanism that tells the two cases apart. A
   consumer who needs two *parties* must allow-list the DIDs as separately operated and settle
   that question out of band.
3. Two verdicts are comparable only when they name the same `method.id` — the format states
   this rather than leaving it implied by a vendor's schema.
4. `inconclusive` is a first-class verdict that MUST NOT be treated as a failure. Suppressing
   it is how judges become rubber stamps.

## Honest status, as of this draft

- `SPEC.md` v2.0.0 draft, 992 lines, with a 66-code reason registry; 5 JSON Schemas
  (non-normative). Counted here:
  `grep -oE '\bAWR-[A-Z0-9]+-[0-9]{3}\b' awr/SPEC.md | sort -u | wc -l` → 66;
  `ls awr/schemas/*.json | wc -l` → 5.
- Python reference implementation: all five §17 CLI subcommands present (`verify`,
  `canonicalize`, `digest`, `hashdata`, `issue`); `issue` → `verify --profile L0` round-trips
  valid; a one-field tamper is rejected with `AWR-PROOF-006`. Its own suite:
  `pytest awr/reference/python/tests -q` → **439 passed**, and the suite prints its own coverage
  line — **66 of 66** registry reason codes are exercised by at least one assertion.
- **A second implementation**, in Rust (6782 lines of `src/`, 1246 of `tests/`), written from
  the specification prose without reading the Python source. Independent codebase, **same
  author, same repository — no second party has implemented AWR**, and a reviewer should
  discount it accordingly. Re-checked in this session on the shipped minimal receipt: the two
  produce identical `proofConfigHash`, `transformedDocumentHash` and concatenated `hashData`
  (`awr hashdata`), identical document digests (`awr digest`), each verifies as valid L0 a
  receipt the other issued, and both reject the same one-field tamper with `AWR-PROOF-006` at
  exit 1. **One document is not a conformance result.**
- Conformance vectors: `awr/vectors/` exists — `find awr/vectors -type f | wc -l` → 124 at time
  of measurement. Conformance matrix: `awr/conformance/` **does not exist**. Every draft in
  `drafts/` links to it and none may be sent until it does.
- **AWR/2 has zero production emitters.** Its predecessor AWR/1 runs in one system and is
  cryptographically weaker in ways §12 and Appendix D document explicitly.
- **No third party has adopted, endorsed, reviewed, or agreed to anything.**

## What we are asking for

Implementation experience, and a reason code we specified wrong. Not a logo.
