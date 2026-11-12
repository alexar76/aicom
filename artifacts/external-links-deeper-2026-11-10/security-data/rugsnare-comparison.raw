# PIN-SPEC surfaceHash × Dominion Observatory captures — format comparison (corpus side)

Companion to [Paraphern/rugsnare#6](https://github.com/Paraphern/rugsnare/issues/6). Scope: where
the two formats already match byte-for-byte, and where they do not. This is the corpus-side
comparison document promised in the join-pair thread.

## Live proof

First public join pair (also the Dominion ledger's first public entry — their ledger held no
public capture for any census-LIVE endpoint at publish time):

- **Endpoint:** `https://rugsnare-mcp.rugsnare.workers.dev/mcp` (rugsnare 1.5.0, hosted)
- **Our `surfaceHash`** (PIN-SPEC §3.2, computed locally by rugsnare 1.5.0): `a7f60d0b5cc214dada5b2c1ec51ff080e0b0828694a0104733b2cc1d5967fb2e`
- **Dominion `manifest_hash`** (their prober, their code, signed capture 2026-10-23T18:36:33Z): `a7f60d0b5cc214dada5b2c1ec51ff080e0b0828694a0104733b2cc1d5967fb2e`
- **Recompute chain:** a third digest computed from the live endpoint's `tools/list` with our code
  also equals the above (verified independently of both stored artifacts). Dominion captures are
  Ed25519-signed; verification key at their `/.well-known/capture-jwks.json`
  (`kid capture-a46fe710c055398f3b6f43a1`, OKP/Ed25519/EdDSA).
- Pin snapshot: [`pins/rugsnare-mcp-worker@1.5.0.json`](pins/rugsnare-mcp-worker@1.5.0.json)

## Where the formats match

| property | PIN-SPEC §3.2 surfaceHash | Dominion capture | match |
|---|---|---|---|
| per-tool field set | `{name, description, inputSchema}` | `{name, description, inputSchema}` | ✅ identical |
| object key order | recursive sort, every depth | recursive sort, every depth | ✅ |
| serialization | compact (no insignificant whitespace) | compact | ✅ |
| non-ASCII strings | raw UTF-8, JSON-minimum escaping | raw UTF-8 (not `\uXXXX`) | ✅ |
| tools array order | sorted by `name` (UTF-8 bytes) | sorted by `name` | ✅ (no deviation needed on our side — theirs is already name-sorted) |
| digest | SHA-256 hex over the UTF-8 bytes of the array | SHA-256 hex | ✅ (proven live, above) |

## Where they do not (yet) meet

1. **Float serialization** — the one honest divergence. PIN-SPEC follows RFC 8785 (JCS) §3.2.2.3
   number serialization; the Dominion corpus has no non-integer numbers in any captured schema, so
   their float behavior is unexercised rather than specified to match. This stays open until a
   captured schema carries a float; their recompute endpoint (public canonical array per capture)
   is the arbiter when it happens.
2. **Scope of the capture set** — Dominion captures only the three-field set above. PIN-SPEC also
   defines internal per-tool hashes over a fourth field (`icons`, PIN-SPEC §1) used for our own
   gating; those are deliberately **not** part of the interop hash, so the two digests remain
   comparable. Annotations and `outputSchema` are stored-but-never-hashed on our side and outside
   their capture — no interop impact, but a pinning host should know the interop digest is blind
   to annotation flips (our ANNOTATION class covers that gap on the client side).
3. **Vantage** — the two hashes agree only because both sides captured the same served surface.
   A publisher-attested pin and an externally-observed capture of an auth-dependent server can
   legitimately differ (per-auth surfaces); the join pair above is an unauthenticated endpoint by
   construction. This distinction is preserved in the registry design thread
   ([modelcontextprotocol/registry#82](https://github.com/modelcontextprotocol/registry/issues/82)).

## Recompute recipe (no trust in either side)

```
GET  https://dominionobservatory.com/api/drift?server=<endpoint-url>
     -> capture.tools (the canonical, name-sorted array)
     recompute SHA-256 over the compact JSON array (sorted keys, raw UTF-8)
     == capture.baseline.manifest_hash
```

Our implementation of that computation: `surfaceHash()` in
[`product/src/hash.js`](../../product/src/hash.js) — field set chosen for exactly this
interoperability (see the code comment citing issue #6).

## Addendum 2026-10-25: a third profile in the wild (MTL/1, HISTOR)

The registry-scale record published in
[google/agentmesh#561](https://github.com/google/agentmesh/issues/561) (HISTOR,
[profile](https://github.com/alexar76/aicom/blob/main/awr/adoption/mcp-trust-label/PROFILE.md))
uses a third canonicalization for tool-set digests. Same base (RFC 8785 + SHA-256), four real
deltas against the pair documented above:

| property | PIN-SPEC §3.2 | Dominion capture | MTL/1 (HISTOR) |
|---|---|---|---|
| per-tool fields | `{name, description, inputSchema}` | same 3 | 4: adds `outputSchema` |
| tools sort unit | UTF-8 **bytes** (code-point order) | "sorted by name" (unit unstated; corpus all-ASCII — unexercised) | UTF-16 **code units** |
| floats in schemas | JCS §3.2.2.3 (specified) | unexercised (none in corpus) | **no digest** — set reported inconclusive |
| annotations | stored, never hashed; own finding class (ANNOTATION) | not captured | outside the tool-set digest; **separate digest** since 2026-10-22 |

Two notes for anyone joining digests across ecosystems. First, the sort unit only matters for
names outside ASCII: a supplementary-plane character (surrogate pair) sorts below some
BMP-range characters in UTF-16 code-unit order but above them in code-point/UTF-8 order — two
correct implementations disagreeing only on the unit will produce different digests for the
same tool set, and that reads as "someone changed something" when nothing did. Second, the
float row now has three honest answers (specified / unexercised / refused) — a spec-level
profile should mandate *stating* the policy, whichever it is.

Convergence note: the separate annotation digest in MTL/1 is the same design decision as our
ANNOTATION finding class — two independent implementations arrived at "annotations outside the
tool-set digest, surfaced as their own change."

### Correction 2026-10-26 (from the MTL/1 author, thread [mcp#3431](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3431#issuecomment-6416860082))

Two cells of the MTL/1 column above were too narrow, corrected here verbatim in substance:

- **The separate digest covers more than annotations.** `toolExtrasDigest` covers every member
  MTL/1 drops from the tool-set digest: `annotations`, `_meta`, `title`, `icons`, `execution`
  and vendor fields — not annotations alone.
- **Its algorithm is SHA-256 over sorted-key JSON, not RFC 8785**, because prices in `_meta` are
  fractions (JCS has no number form for them).
- The field-level record is `extras_changes`: per tool, every annotation that moved as
  `[before, after]`, with an escalation when `readOnlyHint: true` disappears or
  `destructiveHint: true` appears — the closest thing to our ANNOTATION class, plus a
  destructive-direction escalation we grade on the same axis.

The other three rows (per-tool field set, sort unit, float refusal) match `PROFILE.md` as
published. The convergence note above survives the correction, stronger: both implementations
keep "extra" members out of the interop digest AND surface them as their own change record.

## Addendum 2026-10-27: interop test vectors (Gooo contribution)

kimjooyoon (Gooo saved-definition comparison experiment) contributed four synthetic input pairs
with exact preimages, expected hashes and a pinned reproduction command under their named
`gooo/mcp-tool-definition-json/v1` profile
([gist](https://gist.github.com/kimjooyoon/0ba21ab78065f9cffd1cf1af422c8fec), inputs BSD-3-Clause,
reusable independently of Gooo; see [issue #6](https://github.com/Paraphern/rugsnare/issues/6)).
The value of the set: it isolates the **property-key ordering** axis while keeping tool names
ASCII, so the tool-array sort deviation documented above stays out of the picture entirely.

Our computed result on the nested-Unicode fixture (tool name `lookup`, property keys U+E000 and
U+10000 inside `inputSchema.properties`):

- our property-key order: **U+10000 first, then U+E000** (our key sort is UTF-16 code-unit, i.e.
  RFC 8785 §3.2.3 - surrogate pairs sort below U+E000 in code-unit order);
- `surfaceHash` over the single-tool set (empty description):
  `7776cc742e8165bbe0f7e6ed610f76dfcf6ea347f4d0bea21afd9ad4a555ca03`;
- this agrees with the JCS-expected ordering and **diverges from the Gooo Go profile** (their
  pinned `encoding/json` comparison puts U+E000 first) - exactly the class of named, deliberate
  divergence this document exists to record.

Sort-order now reads as two separate facts: **tool-array order** (PIN-SPEC: code-point/UTF-8
bytes - a deliberate, documented deviation; MTL/1: UTF-16 units; Dominion: unit unstated) and
**property-key order** (PIN-SPEC: JCS/UTF-16 units, as verified by this fixture; any profile
comparing raw JSON key order must state its unit, or digests will disagree on non-BMP keys while
agreeing everywhere else).
