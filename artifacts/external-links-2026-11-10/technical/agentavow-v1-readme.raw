# Tool-manifest-digest vectors (v1): one named tool

Extends [v0](../tool-manifest-digest-vectors-v0/) for the boundary on
[aeoess/agent-governance-vocabulary#177](https://github.com/aeoess/agent-governance-vocabulary/issues/177)
(edge E1 in [#179](https://github.com/aeoess/agent-governance-vocabulary/pull/179)).
v0 bound a gate to a whole server by its manifest digest. The first consumer run recorded
that the attestation carried no tool name, so a gate authorizing one tool had nothing to
bind to. v1 closes that: the attestation now signs one digest per served tool, keyed by
tool name, and the gate binds to the tool it is authorizing.

    node verify.mjs

Zero dependencies, Node 18+. Nothing is fetched. Exits non-zero on any failure.

## The artifact

One real, pinned AgentAvow scan attestation for the live MCP server at
`https://mcp.deepwiki.com/mcp` (a public, unauthenticated server with three tools): a
compact JWS (RFC 7515, EdDSA/Ed25519) whose payload is the RFC 8785 canonical bytes of
the verdict. Inside the signed payload: the issuer (`did:web:agentgraph.co`), the subject
`mcp:https://mcp.deepwiki.com/mcp`, `issuedAt`, `expiresAt`, the score and tier, the
findings, `scan.toolDigests` (one digest per tool, keyed `tool:<name>`), and
`scan.toolManifestDigest` folded over them.

The file also carries `observed_tools`: the `tools/list` the server served at scan time,
fetched directly from the server and unmodified. That is what makes the preimage
testable (below).

## The consumer input

A gate supplies four things about the one tool call it is about to authorize:

```jsonc
"gate": {
  "subject_id": "mcp:https://mcp.deepwiki.com/mcp",     // the server
  "tool_name": "ask_wiki_question",                      // the tool being authorized
  "observed_tool_digest": "sha256:171a53c9…",            // digest of the definition it was served
  "evaluation_time": "2026-10-01T22:28:34.085Z"          // pinned, so verdicts are reproducible
}
```

A gate computes `observed_tool_digest` itself, from the `tools/list` entry it holds,
with no call to the issuer. The derivation:

```
tool      = the served definition restricted to
            name, title, description, inputSchema, outputSchema, annotations
            (a missing or null field is omitted; _meta and unknown fields are never hashed)
preimage  = JCS({ "profile": "agentavow.mcp-tool-definition.v1", "tool": tool })
digest    = "sha256:" + hex(sha256(preimage))
key       = "tool:" + body, where body is the name with every character outside
            0x21-0x7E (space, controls and all non-ASCII), plus % and =, replaced by
            its UTF-8 bytes as %XX (uppercase hex); if that encoded body is longer
            than 128 characters it is cut to its first 96 and suffixed with "~" and
            the first 16 lowercase hex characters of sha256 over the raw UTF-8 name;
            the cut is a plain character count and may land inside a %XX triplet
```

The profile label versions the preimage: if the field set ever changes, the label changes,
and an old digest can never be mistaken for a new one.

## The six axes

A consumer reports these separately. None is derived from another.

- **signature_valid**: Ed25519 verifies under the pinned key.
- **canonical_bytes**: `jcs(JSON.parse(payload))` equals the payload bytes.
- **subject_binds**: the attestation's subject is the server the gate names.
- **tool_binds**: the scan observed a tool of the name the gate is authorizing.
- **tool_digest_binds**: the signed digest for that tool equals the digest the gate
  computed from the definition it was served. `not_evaluated` when `tool_binds` is false:
  there is no signed digest to compare, and the verifier says so rather than reporting a
  failure it did not measure.
- **fresh**: `evaluation_time` is inside `[issuedAt, expiresAt)`, compared as instants, not as
  strings, at the precision the timestamps carry. The signed times have microseconds and an
  explicit `+00:00`; gate times have milliseconds and `Z`. A string comparison, or a parser that
  truncates to milliseconds (JavaScript `Date`), misjudges a gate time just inside the window.
  See the [supported time contract and boundary controls](time-contract.md).

`rely` is true only when all six axes are `true`; `not_evaluated` is not `true`, so it never relies. Whether a gate proceeds on `rely=true` is a separately versioned
admission policy.

## The seven cases

1. **tool-match**: the positive case.
2. **unknown-tool**: the gate authorizes `delete_wiki_page`, which the scan never saw.
   `tool_binds` false, `tool_digest_binds` not evaluated.
3. **tool-drift**: the definition the gate was served has one sentence added to its
   description after the grade (the rug-pull, per tool). Only `tool_digest_binds` fails.
4. **wrong-subject**: the same tool name and digest presented for a different server.
5. **past-expiry**: evaluated after `expiresAt`.
6. **tampered-payload**: score raised after signing, payload re-canonicalized, original
   signature kept. Canonical bytes still check; the signature does not.
7. **boundary-fresh**: a gate time inside the window by less than a millisecond. It is
   `expiresAt` truncated to millisecond precision and written with `Z`, the shape a
   millisecond clock produces. Every axis passes. A consumer that compares the timestamps
   as strings, or parses them with something that truncates to milliseconds, reads it as
   expired.

Each negative fails exactly one axis, and the verifier asserts that. `boundary-fresh` is a
second positive rather than a negative: it is the only case where comparing instants,
truncating to milliseconds and comparing strings do not all agree, so it is the one that
tells a correct consumer from one that happens to pass the other six.

## What the verifier also checks

Before the vectors, it recomputes the digest of every served definition in
`observed_tools` with the derivation above and checks it against the signed
`scan.toolDigests`. All three match. So the preimage is under test across
implementations, not only the comparison: a consumer in another language that gets the
same three digests from the same three definitions has implemented the derivation
correctly.

## Key encoding

The pinned server's tool names are plain ASCII, so the seven cases never exercise the
key rules. `key_encoding` in the vector file carries thirteen name-to-key pairs that
do: seven for percent-encoding (`=`, `%`, space, a tab, `é`, an emoji) and six for the
length rule (an encoded body of exactly 128 stays literal; 129 ASCII characters, 200
ASCII characters, and 50 `é` whose encoded body is 300 characters are cut and
suffixed; two names whose cut lands inside a `%XX` triplet, keeping `%` and `%C`
respectively). They are derived with the same rules and carry no signature; the
expected keys were produced by the issuer's own implementation. The verifier checks
them; an implementer who gets all thirteen has the encoder right.

## Claim ceiling

`rely=true` establishes exactly this: at `evaluation_time`, the named issuer had signed a
static-analysis grade for this server, the grade covered a tool of this name, the
definition the gate was served for that tool is the one the scan graded, and signature,
subject and window all check. It establishes nothing about runtime behavior, nothing about
what the tool does when invoked, nothing about other tools on the server, and nothing
about definitions the scan did not observe.

## Boundaries carried over from v0

- The subject is a server, not a tool; the tool binding is the separate `tool_binds` axis.
- `scan.toolManifestDigest` is a fold over the per-tool digests, not a per-tool metadata
  pin, and the v1 gate does not use it. A consumer that needs the whole-server binding
  uses v0.

## Derivation

`node generate.mjs` rebuilds the vector file from `source.json` (the pinned JWS, JWK and
the served `tools/list`). It refuses to build if any served definition does not recompute
to its signed digest. The pinned attestation was fetched once on 2026-10-01 from
`https://agentavow.com/api/v1/public/scan/mcp?endpoint=https%3A%2F%2Fmcp.deepwiki.com%2Fmcp`;
the `tools/list` was fetched from the server in the same minute. A fresh fetch yields a
fresh attestation, so the file is the fixture, not the URL.

## Separate implementations

Each entry says who wrote the implementation, what it ran against, and what it reported.
The labels follow the authors' own. In the Agent Authority Conformance lab's terms, a run
counts as independent only when the runner authored neither the vectors nor the reader.
Every run below was made by the reader's own author, so each is a separate implementation,
not an independent record. A run of either reader by someone who wrote neither would be.

- **Probity reader** (`probityai/agent-evidence-vectors`, Apache-2.0), owned by Probity:
  [`interop/agentavow-signed-map-v1/` at `d759fb4`](https://github.com/probityai/agent-evidence-vectors/tree/d759fb4db68a7fefcc91c2d3ad2a585471d6a53a/interop/agentavow-signed-map-v1),
  merged in [PR #43](https://github.com/probityai/agent-evidence-vectors/pull/43) and
  reported on [#177](https://github.com/aeoess/agent-governance-vocabulary/issues/177).
  A separate reader in Python (name encoding, JWS and canonical-bytes checks, the six
  axes, the served-definition digest) that reads the vector file at `36426cf` unchanged.
  It matches all thirteen name-to-key pairs, the three served-definition digests, the
  payload digest and the six case verdicts. A separate implementation, run by its author:
  written by a party other than us and other than a consumer we handed a fixture to. It
  selects the signing key on its own side (`selection.json`) rather than taking it from
  the packet, and adds an `issuer_binds` axis of its own.
- **APS-side consumer** (`agent-passport-system` 7.2.0 primitives), owned by APS:
  [`examples/interop/agentavow/` at `fd47f34`](https://github.com/aeoess/agent-passport-system/tree/fd47f34cc36fce060d092fe1216aff3f89fb8d88/examples/interop/agentavow),
  listed under Consumers in the [v0 README](../tool-manifest-digest-vectors-v0/README.md).
  By its author's label, a second implementation run by the consuming project: a
  reproduction, not an independent verification record. Its v0 run is what recorded the
  two boundaries that v1 closes; a v1 run will be listed here when it is reported.
- **heldfast** (`rufat325/heldfast`, Apache-2.0), owned by heldfast:
  [docs/TRANSPARENCY.md, "Comparing with another record"](https://github.com/rufat325/heldfast/blob/main/docs/TRANSPARENCY.md#comparing-with-another-record),
  reported on [stacklok/toolhive#6734](https://github.com/stacklok/toolhive/issues/6734).
  heldfast reproduces the published per-tool digests and the key encoding for the pinned
  fixture (3 of 3 digests, 13 of 13 key pairs, as of 2 October 2026), from its own
  implementation of the rules, with none of our files copied. It makes no claim about
  AgentAvow's grades, and asked to be described exactly that narrowly. Its native record
  keeps a different preimage (snake_case keys, defaults for missing fields, no profile
  label) and does not store this profile's digest per entry; it is recomputed from the
  definitions it already holds.

### The CI check

The Probity reader is run in our CI against the current vector file, next to
`verify.mjs`, by the workflow
[`probity-v1-compat.yml`](../../../.github/workflows/probity-v1-compat.yml). It runs on
every change under this directory, on a weekly schedule, and on demand. A producer change
that `verify.mjs` agrees with but the outside reader does not fails the job. Both reports
are retained as a workflow artifact for 90 days.

The pin is `compat/probity-pin.json` (repository, commit, reader directory, Python
version, requirements file). Moving to a newer Probity commit means changing that one file.

What runs, in order (`compat/run-probity.sh`):

1. `node verify.mjs`, our native verifier.
2. Probity's own driver, `run_agentavow.py`, unmodified. It refuses any vector file whose
   bytes differ from the one it locked at `36426cf`, which is the right control for their
   repository. So this step runs only while the file is byte-identical to that lock, and
   is reported as skipped otherwise.
3. `compat/probity_compat.py`, which imports Probity's `map_reader` from the pinned
   checkout and runs the same sequence their driver runs (thirteen keys, three
   definition digests, payload digest, six cases, positive pin) on the current file. Only
   glue lives in that script; no encoding, hashing or verification logic is ours. The
   signing key comes from Probity's `selection.json`, so a rotated issuer key fails here
   until the consumer updates its selection; `--key-from-fixture` isolates that case.

Update 2026-11: after agent-evidence-vectors PR #236, Probity's own driver accepts the
current vector file (appendix row R4-driver, agent-evidence-vectors 82b8bb67, producer
b7c5cd2f). The records here were produced through the glue.

Locally:

    python3.13 -m pip install -r <probity-checkout>/interop/a2a-s3-retain-2026-10-01/requirements.txt
    compat/run-probity.sh --probity <probity-checkout> --python python3.13

Without `--probity` the script clones the pinned commit into its output directory. The
reader's `pyproject.toml` says Python 3.13 or newer; it also runs on 3.14. Its runtime
dependencies are `cryptography` and `rfc8785`, at the versions pinned in that
requirements file.

## Contributors

- **Mayur Agnihotri** ([@Mayur021](https://github.com/Mayur021)): a separate reader that reproduced all six cases on
  2026-10-08, the finding that string or millisecond comparison misjudges freshness inside the window, and the
  `boundary-fresh` vector (#131).
- **Sankalp Gilda, Probity** ([@astrogilda](https://github.com/astrogilda)): the signed-map reader run in CI
  (`probity-v1-compat`), and nanosecond-exact time comparison with calendar checks, a locally signed
  200 ns window fixture and 49 controls (#132).

Contributions to this folder are accepted under its Apache-2.0 licence; see `CONTRIBUTING.md` at the repository root.

## Licence

This directory (the vector file, `source.json`, `generate.mjs`, `verify.mjs` and this README) is licensed under
Apache-2.0; see [`LICENSE`](./LICENSE) here. The repository LICENSE grants a subdirectory with its own LICENSE file
its own terms, so these vectors can be vendored and redistributed by any implementer.

## Run it yourself and report

Nothing here needs permission or guidance from AgentAvow. The inputs are pinned in this directory,
the procedure is `node verify.mjs` (Node 18+, no dependencies, no network), and the classification
rules are the ones the verifier prints: every check is `ok` or `FAIL`, and the run exits non-zero on any
failure. To report a run, state the commit of this directory you ran, your Node version and OS, the
verifier output verbatim, and whether you wrote your own implementation of the derivation or used
`verify.mjs`. A run by someone who authored neither these vectors nor the implementation under test is
the only kind that counts as independent; a run of your own reader is a separate implementation, run by
its author, and should be labelled that way. The claim ceiling above applies to every run regardless of
who performs it.

## The same derivation elsewhere

- **agentrust-io/trace-spec** publishes this derivation as `trace.mcp-tool-definition.v1`
  ([RFC](https://github.com/agentrust-io/trace-spec/blob/main/docs/rfcs/tool-catalog-observed-digest.md),
  cases COMP-MCP-004 to 006, merged 2026-10-07). The rules are identical; only the profile label
  differs, and the label is part of the preimage, so digests under the two labels are not equal.
  A consumer that needs both computes both.
- **Agent Authority Conformance lab** holds this set as the `tool-manifest-digest` cross-stack family
  (merged 2026-10-07) with per-claim records: an independent record for the key encoding, per-tool
  digests, canonical bytes, signature and case verdicts (a lab-operated run of a reader written by
  Probity), and independently operated runs of these verifiers for v0 and the one-axis property.
- **Probity Observer** consumes this set as a gate input before a local file effect
  ([`TOOL-MANIFEST-EFFECT`](https://github.com/probityai/agent-evidence-observer/blob/00e92b0a3fcf53376ebafc6cc9b4abde7e9fdc8c/docs/reference/TOOL-MANIFEST-EFFECT.md)
  at `probityai/agent-evidence-observer@00e92b0`, fixture vendored unchanged). Three recorded runs, all
  with the same six-case axes and `--verify` exit 0:
  - [author-operated](https://github.com/probityai/agent-evidence/issues/24#issuecomment-6275394206)
    by AgentAvow, macOS arm64, Python 3.12.13;
  - [reproduced](https://github.com/probityai/agent-evidence/issues/50) by a non-author operator
    (Pico, @piiiico) on Linux aarch64. Its output files are byte-identical to the author's once the
    run clock (`runEvaluationTime`) is set to the same value;
  - [replayed](https://github.com/probityai/agent-evidence/issues/50#issuecomment-6375111046) by the
    reader's author (Probity, @astrogilda) on Linux x86_64, with the same byte-identical result.

  All three ran the same reader code, so the second and third are reproductions on other platforms,
  not independent implementations.

## See also

- [v1-annotations](../tool-manifest-digest-vectors-v1-annotations/): a separate pinned packet adding an annotation-only drift case; this packet and its run records are unchanged.
- [w3c-v01](w3c-v01/): the runs of this set by `verify.mjs`, the Probity reader and heldfast, written as v0.1 reports of the W3C Agent Conformance CG reporting format, with the command that re-runs them.
- [v1-numbers](../tool-manifest-digest-vectors-v1-numbers/): unsigned derivation vectors for how a number in a definition is read (a fraction, 2^53, 2^53 + 1, a large exponent, -0), computed by the issuer; this packet and its run records are unchanged.
- [v1-noncanonical](../tool-manifest-digest-vectors-v1-noncanonical/): unsigned vectors for the issuer's fallback digest on definitions JCS cannot carry (a lone surrogate, a number too large for a double), computed by the issuer; this packet and its run records are unchanged.
