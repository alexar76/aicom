# MTL — MCP Trust Label

**Profile of:** AWR/2 (`awr/SPEC.md`, version 2.0.0)
**Version:** MTL/1 (1.0.0)
**Status:** Draft profile, seeking implementation experience
**License:** MIT
**Profile namespace:** `https://verify.modelmarket.dev/ns/awr/mtl/v1`
**This document:** `awr/adoption/mcp-trust-label/PROFILE.md`

> **This is a draft on disk.** Nothing in this directory has been sent, published, submitted,
> posted or registered anywhere. The profile namespace URI above is an identifier, not a
> promise: it is **not currently served** (verifiers are forbidden to dereference it anyway —
> SPEC §13.5). Distribution is the repository owner's decision, not this document's.

---

## Abstract

MCP registry listings we are aware of surface popularity — stars, downloads, install counts —
which measures attention, not safety. That characterisation is **TO VERIFY** against each
registry's live UI: no registry UI was queried while writing this profile and no outbound
request was made, so it is our impression and not a survey. MTL defines how a small set of
MCP-server security signals becomes a signed AWR `VerificationVerdict` whose bytes and digest
arithmetic can be re-checked offline by anybody, so that a registry can render a claim whose
signing key is identified.

MTL is deliberately narrow. The signals it admits are:

> **What the label records, as its issuer's signed assertion: the exact set of tool definitions
> the issuer says a server advertised at a stated time, committed to by digest; whether that
> set has changed since a previous label; whether the advertised text matched a published
> pattern set; and whether the server's registry name and transport coordinates matched a
> published threat record set.** The signature makes those assertions attributable to one
> Ed25519 key and tamper-evident. It does not establish that any retrieval occurred, or when
> (§13.5), and the digest binds the label to a subject only for a consumer that recomputes it
> (§4.6, §13.1).
>
> **What the label does not record at all: that any source code was read, that any package was
> inspected, that any tool was invoked, or that the server is safe.** No component of the
> issuing ecosystem audits an MCP server's code, and MTL/1 provides no vocabulary for saying
> otherwise.

Definition pinning plus a name-and-coordinate threat match is the strongest thing the
underlying implementation does. That is what the label says, in those words.

**The consumer-side cost, stated in the Abstract because it is the largest fact about this
profile.** §4.6 makes subject-digest recomputation REQUIRED, and recomputation requires the
consumer's own retrieval of the tool set. For a `stdio` server — the transport of both worked
examples in `examples/`, and of most MCP servers — retrieving a tool set means installing the
package and **executing** it to answer `tools/list`. A consumer unwilling to run untrusted code
falls back to §4.6's `unconfirmed subject` mode, in which a valid signature may certify a claim
about a different server (§13.1). MTL/1 has no third option to offer and does not pretend to.

Two signals available in the implementation are **excluded** rather than weakened: a network
reputation score that never executes, and a composite safety score whose value for a flawless
server is capped at 0.540 by that dead gate. §8 records the exclusions and the code that
justifies them. A model-dependent judgement, should one ever be issued, is confined to a
separate document type and a separate method arc so it can never inherit a signed verdict's
credibility (§7.6).

## Status of this memo

This is not an IETF RFC, not a W3C Recommendation, and not a standard of the Model Context
Protocol project. It profiles AWR/2 for one subject class and normatively depends on it.
Where this document and `awr/SPEC.md` disagree, `awr/SPEC.md` wins and this document is a bug.

Every statement here about implementation behaviour was checked against the code named in
Appendix B, and — where the statement is behavioural — by executing it. Nothing is transcribed
from documentation or comments. The checks were re-run on 2026-07-31 (18:19–18:30 UTC) while
revising this document; every codebase named is under active development, so a reviewer should
re-run them rather than trust the prose.

## Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**,
**SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** are to be interpreted as described
in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

"Label" means one MTL document. "Issuer" means the party that signs it. "Registry" means
software that retrieves, verifies and displays labels. "Subject" means the thing a label is
about, as constructed in §4. Section references of the form "SPEC §n" are to `awr/SPEC.md`.

---

## 1. Introduction

### 1.1 Problem

An MCP registry listing carries a name, a description, an install command, and a popularity
figure. None of those is a security property. The registry cannot audit the servers it lists,
the servers are not built by the registry, and the definitions a server advertises can change
at any time after a user has approved them — the tool-poisoning and rug-pull surface.

The one MCP security implementation examined for this profile — ARGUS WARDEN, in this
repository (Appendix B lists every file and every executed check) — emits a composite score, an
allow/block boolean and a list of findings. **We have not surveyed any other tool and make no
claim about the market;** other implementations may already sign their output or scope it
differently. WARDEN's output has three defects as a registry signal. It is unsigned, so a
registry cannot tell which key computed it. Its inputs are not committed, so a second party
cannot re-derive it. And it collapses signals of wildly different strength into one number, so a
pattern match over advertised prose gets rendered with the same authority as a cryptographic
digest comparison.

### 1.2 What MTL adds

MTL/1 fixes those three defects and nothing else:

1. **Signed.** A label is an AWR `VerificationVerdict` (SPEC §3.4) with an `eddsa-jcs-2022`
   Data Integrity proof over an RFC 8785 canonicalization, issued by a `did:key`. The issuer
   has an identity and is therefore accountable for the claim.
2. **Deterministic given the observed bytes** — which is less than "reproducible", and the
   difference matters. No model, no clock and no scoring appears in any decision, and every
   input a method depended on is committed by digest in `evidence`, so a second party can
   recompute the *comparison*. What a second party cannot reproduce is the **observation**:
   acquiring a tool set is a network operation against an adversarial party, and §13.4 records
   that a server can vary the definitions it advertises by client. So the reproducible object
   is the digest over bytes the issuer chose to commit to and publish, not the retrieval that
   produced them. Read §12 and §13.5 for what that leaves unestablished.
3. **Unaggregated.** One method, one label. MTL/1 defines **no** composite score and forbids
   `score` on every label (§6.4). A registry that wants a single glyph must choose one itself
   and say so; MTL will not launder the choice.

### 1.3 Design constraints

1. **Offline.** *Verification* is offline: a signature check plus one digest recomputation, with
   no DID resolution, no schema fetch and no call to the issuer (SPEC §13.5). The digest
   recomputation's **input** is not offline — §4.6 requires the consumer's own retrieval of the
   tool set, which for a `stdio` server means executing the server. Retrieval and verification
   are separate phases and only the second one is free.
2. **No new cryptography, no new canonicalization.** MTL reuses SPEC §4 and §6 unchanged. The
   one new digest (§5) is SHA-256 over the same RFC 8785 canonical form.
3. **Every ambiguity refused, not arbitrated.** Where a value cannot be digested identically
   by two separately written implementations, MTL/1 declines to digest it and the label degrades to
   `inconclusive` (§5.4). This follows SPEC §4.3 rather than extending it.
4. **`inconclusive` is a first-class outcome.** SPEC §3.4 requires that `inconclusive` not be
   treated as a failure. MTL/1 relies on that: it is the outcome for every signal that is
   suggestive but not dispositive, which is most of them.
5. **No authority.** MTL creates no accreditation, no registry of approved scanners and no
   trust root. Anybody can generate a `did:key` and label anything. §13.2 is the consequence.

   This constrains how the rest of the document must be read. Every requirement here addressed
   to a *registry* or *consumer* binds only a consumer that chooses to claim MTL/1 conformance.
   MTL has no authority over any registry, asks for none, and is not a standard of the Model
   Context Protocol project (see "Status of this memo"). A registry that reads a label and
   ignores this profile entirely is not violating anything.

### 1.4 Relationship to ARGUS WARDEN

The §7 signals — deterministic in the qualified sense of §1.2 — are drawn from the WARDEN MCP
gate chain in `argus/`, which
this profile treats strictly as *one possible issuer implementation*, not as a normative
reference. MTL/1 names no ARGUS endpoint, requires no ARGUS code, and in two places
deliberately **diverges** from it:

- WARDEN's tool-definition hash is not cross-implementation reproducible (§5.5). MTL/1 defines
  its own digest and does not accept WARDEN's.
- WARDEN's composite score and allow/block decision are not admissible as label content (§8.2,
  §8.3).

An issuer MAY be built on entirely different code. Conformance is defined by §4–§7, not by
matching any implementation's output.

---

## 2. Terminology

| Term | Definition |
|---|---|
| **MCP Server Descriptor (MSD)** | The JSON object that *is* the subject of a label: a server identity plus its advertised tool set, digested (§4). AWR names the field `verifiedWork`; the name is AWR's and implies no verification of the server |
| **Subject digest** | SHA-256 over the RFC 8785 canonical form of the MSD, SRI-encoded (§4.5) |
| **Tool set** | The fully drained `tools` array of a successful MCP `tools/list` (§5.1) |
| **Tool-set digest** | SHA-256 over the RFC 8785 canonical form of the normalised, sorted tool set (§5) |
| **Label** | One MTL document: an AWR `VerificationVerdict` also typed `MCPTrustLabel` (§6) |
| **Opinion** | A model-dependent statement, typed `MCPTrustOpinion`, which is not a label (§7.6) |
| **Method** | One procedure, identified by a URN registered in §7.1, whose decision is deterministic given the observed bytes (§1.2) |
| **Pattern set** | The published, digested table of signatures a scan method ran under (§7.3) |
| **Record set** | The published, digested table of threat records a match method ran under (§7.5) |
| **Corroboration** | Two or more valid labels over the same subject digest, from distinct issuer DIDs (§9.4) |
| **Drift** | Two labels over the same server name whose subject digests differ (§7.4) |

---

## 3. Document model

### 3.1 A label is a standalone `VerificationVerdict`

A label **MUST** be a valid AWR/2 `VerificationVerdict` as defined by SPEC §3.1, §3.4 and §6.
Every requirement of those sections applies unchanged, and a label that fails any of them is
not an MTL label.

Additionally:

- `type` **MUST** contain `VerifiableCredential`, `VerificationVerdict`, and exactly one of
  `MCPTrustLabel` (§6) or `MCPTrustOpinion` (§7.6). Absence of both is `MTL-DOC-001`.
- `@context` **MUST** contain `https://verify.modelmarket.dev/ns/awr/mtl/v1` in addition to
  the two URIs SPEC §3.1 requires. A verifier **MUST NOT** dereference it (SPEC §13.5).
- `credentialSubject` **MUST** carry an `mcpTrustLabel` object (§6.3). It is an unknown
  property to a plain AWR verifier, which SPEC §3.1 requires such a verifier to ignore
  semantically, include in canonicalization, and never strip. It is therefore signed.

### 3.2 There is no `WorkReceipt`, and this has consequences

AWR's `VerificationVerdict` was designed to judge a `WorkReceipt`. An MCP server is not a unit
of work: nothing was invoked, no model ran, there is no input and output pair. MTL therefore
**MUST NOT** synthesise a `WorkReceipt` for a server or for a scan run. Dressing a regex pass
over advertised text as a record of AI-performed work would misrepresent both documents.

Instead, `verifiedWork` points at the MSD (§4). This is a **deliberate deviation** from SPEC
§3.4's default reading, under the permission SPEC §3.2 grants: "The hashed bytes are defined
per field". §4.5 defines them for this profile. Four consequences follow. Consequences 1 and 3
were re-executed on 2026-07-31 against the AWR/2 reference implementation; consequence 2 was
re-checked by reading `verify.py`; consequence 4 is structural:

1. A conformant AWR verifier reports a label as `"valid": true` with `"profile": "L0"`. The
   signature, envelope and verdict-subject checks all pass.
2. `AWR-VDCT-005` (verdict references a receipt that does not match) **cannot** fire for a
   label, because the reference implementation raises it only when a supplied supporting
   document carries the same `id` as `verifiedWork.id`, and an MSD subject URN is never an AWR
   document `id`. The cross-check is therefore not merely unused but structurally absent — and
   §4.6 is the replacement that a registry **MUST** perform instead.
3. **Profiles L0/L1/L2 do not apply to a label.** Evaluated at L1 or L2, a label is reported
   as failing with `AWR-PROFILE-001`, because those profiles are defined over a `WorkReceipt`.
   An issuer **MUST NOT** advertise a label as satisfying L1 or L2, and a registry **MUST NOT**
   display an AWR profile level for a label (`MTL-PROF-001`).
4. L1's structural guarantee — that the judge is not the judged — has no analogue here, because
   there is no receipt issuer to differ from. §9.4 defines **corroboration** as the substitute:
   distinct issuer DIDs agreeing on the same subject digest. It is a weak substitute, and §9.4
   says why — distinct DIDs are distinct keys, so a count means "two parties" only for a
   consumer that has allow-listed those keys as separately operated. Nothing can be read off a
   single label, and not much can be read off an unfiltered count either.

### 3.3 What a label may not contain

- `score` **MUST NOT** be present (§6.4, `MTL-DOC-003`).
- `policy.threshold` **MUST NOT** be present, there being no score to compare (`MTL-DOC-003`).
- `stake` **MAY** be present; MTL/1 attaches no meaning to it, and SPEC §10.3's rule stands —
  a verifier **MUST NOT** contact a chain to check it.

---

## 4. The subject: MCP Server Descriptor

### 4.1 What the subject is

The subject of a label is the pair **(server identity, advertised tool set)**. It is not the
server's code, not its package, and not its publisher. Two labels are about the same subject
when, and only when, their subject digests are equal.

The MSD carries **no timestamp**. This is load-bearing: because the descriptor is timeless, a
second observation of an unchanged server produces the *same* subject digest, and drift
detection reduces to comparing two digests (§7.4). Observation time lives in the label
(§6.3), not in the subject.

### 4.2 Structure

```json
{
  "mtl": "1",
  "server": {
    "name": "com.example/weather",
    "registry": "urn:awr:mtl:1:registry:example",
    "version": "1.4.2"
  },
  "artifact": {
    "transport": "stdio",
    "package": "npm:@example/weather-mcp@1.4.2"
  },
  "toolSet": {
    "count": 2,
    "names": ["get_weather", "list_cities"],
    "digestSRI": "sha256-9+Gp1Oq15KPBAAGmFucoVwSQ/PUzwLt1CRxesSUvX5c="
  }
}
```

This is `examples/pass-01-subject-descriptor.json` verbatim, and its subject digest is
`sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s=` — reproduced on 2026-07-31 with
`awr digest examples/pass-01-subject-descriptor.json`.

- `mtl` **MUST** be present and **MUST** be `"1"` for this profile. It is inside the digested
  bytes, so a descriptor cannot be reinterpreted under a later profile's field rules.
- `server.name` **MUST** be a non-empty string: the name that identifies the server *within*
  `server.registry`. `server.registry` **MUST** be a non-empty opaque string naming the
  namespace authority that assigned the name. MTL/1 defines no registry identifiers and
  validates none; two registries that assign the same name to different servers produce
  different subjects only if they use different `registry` values, so an issuer **MUST** use a
  value the consuming registry recognises.
- `server.version` is **OPTIONAL** and is the version string the server or its listing
  advertised. It is the issuer's transcription; MTL/1 does not verify it.
- `artifact` is **OPTIONAL**. `transport` **MUST**, if present, be one of `stdio`,
  `streamable-http`, `sse`. `package` and `endpoint` are **OPTIONAL** opaque strings recording
  what the issuer connected to. **MTL/1 does not verify that the package named installs to the
  code observed** (§12).
- `toolSet.count` **MUST** be the integer number of tools, and `toolSet.names` **MUST** be the
  tool names sorted per §5.3. Both are redundant against the tool-set digest and exist so a
  registry can render something without holding the tool set.
- `toolSet.digestSRI` **MUST** be present when the tool set is digestible (§5) and **MUST** be
  absent otherwise. Its absence is what makes a non-digestible subject representable at all.

### 4.3 Omission, not null

An **OPTIONAL** member that has no value **MUST** be omitted. It **MUST NOT** be present as
`null`, an empty string or an empty object, because presence changes the canonical bytes and
therefore the subject digest. An empty `artifact` object **MUST** be omitted entirely.

### 4.4 Numbers

The MSD **MUST** contain no JSON number other than `toolSet.count`, and `toolSet.count`
**MUST** be a non-negative integer. The descriptor is therefore always canonicalizable under
SPEC §4.3, including when the tool schemas it summarises are not (§5.4).

### 4.5 Subject digest and subject URN

- The **subject digest** is the W3C SRI encoding (SPEC §3.2) of SHA-256 over the RFC 8785
  canonical form (SPEC §4) of the MSD.
- The **subject URN** is `urn:awr:mtl:1:subject:sha256:` followed by the lowercase hexadecimal
  of the same 32 bytes. `urn:awr:` is **not** an IANA-registered URN namespace; the URN is an
  opaque identifier and **MUST NOT** be resolved.
- `credentialSubject.verifiedWork` **MUST** be `{"id": <subject URN>, "digestSRI": <subject
  digest>}`. Both members are required by SPEC §3.4. Deriving the `id` from the digest means
  the identifier cannot be re-pointed at different bytes even in isolation.

### 4.6 A registry MUST recompute the subject digest

Signature validity proves only that the issuer signed those claims (SPEC §13.7). It does not
prove the label is about the server the registry is displaying — the `mcpTrustLabel.server`
block is the issuer's assertion, and a label for one server can be attached to another
server's listing by whoever controls the listing pipeline.

A registry **claiming MTL/1 conformance MUST** therefore, before displaying a label:

1. build the MSD itself, from its own record of `server.name` and `server.registry` and its own
   retrieval of the tool set;
2. compute the subject digest per §4.5;
3. compare it to `verifiedWork.digestSRI` and refuse to display the label as being about that
   server on mismatch (`MTL-SUBJ-004`).

**What step 1 costs, said plainly.** "Its own retrieval of the tool set" means the consumer runs
the MCP `initialize` handshake and `tools/list` against the server itself. For `transport:
"stdio"` there is no remote endpoint to query: the tool set exists only when the package is
installed and **executed**. So step 1 is, for the majority of MCP servers, *execute untrusted
code in a sandbox you operate, once per listed server, on your own schedule.* MTL/1 cannot remove
this: it is a consequence of §13.1, where the subject binding is the only defence against the
primary attack, and of §8.5, where nothing in this ecosystem produces a signed installable-
artifact digest that could substitute for a live retrieval. An implementer who has not budgeted
for that has not budgeted for §4.6.

A registry that cannot or will not retrieve the tool set itself **MAY** instead compare only
`mcpTrustLabel.server` against its own record, and **MUST** in that case render the label as
`unconfirmed subject` rather than as a label about that server. Understand what that mode is:
§13.1 describes it as the state in which every signature check passes and the claim is simply not
about what the page says it is about. It is a degraded mode, not an equivalent one.

---

## 5. Tool-set canonical digest

### 5.1 Input

The input is the `tools` array of a successful MCP `tools/list` result.

- Pagination **MUST** be fully drained: every page **MUST** be retrieved and the arrays
  concatenated in retrieval order before normalisation. A partial listing **MUST NOT** be
  digested; it yields `inconclusive` under §7.2.
- The digest covers **advertised definitions only**. Live tool output, resource contents and
  prompt templates are outside MTL/1 (§12).

### 5.2 Normalisation

Each tool object is replaced by an object with exactly these members:

| Member | Value |
|---|---|
| `name` | the tool's `name`; **MUST** be a non-empty string (`MTL-SUBJ-001`) |
| `description` | the tool's `description` when it is a string, otherwise `""` |
| `inputSchema` | the tool's `inputSchema` when it is an object, otherwise `{}` |
| `outputSchema` | the tool's `outputSchema`, **present if and only if** the observed object carried an object under that key |

Every other member the server sent — `title`, `annotations`, `_meta`, vendor extensions — is
**dropped**. `outputSchema`'s conditional presence is deliberate: absent and `{}` are different
advertised contracts, and collapsing them would let a server change its output contract without
changing the digest.

A future MTL version **MAY** digest more fields. Doing so changes every digest, which is why
`mtl` is inside the descriptor (§4.2) and the version is inside every method id (§7.1).

### 5.3 Ordering

- Duplicate `name` values **MUST** be rejected (`MTL-SUBJ-003`): with duplicates the digest
  would depend on retrieval order, which servers vary freely.
- An empty tool set **MUST** be rejected (`MTL-SUBJ-002`): there is nothing to pin.
- Entries **MUST** be sorted by `name`, compared as **arrays of UTF-16 code units treated as
  unsigned integers** — the identical rule RFC 8785 §3.2.3 mandates for object keys, so an
  implementation reuses its JCS key comparator.

  Locale collation **MUST NOT** be used. It disagrees with code-unit order on ordinary inputs:
  in JavaScript `"Z_tool".localeCompare("a_tool")` is `1` while code-unit order gives `-1`, and
  `["resume", "résumé", "rezume"]` collates as `resume, résumé, rezume` but orders by code unit
  as `resume, rezume, résumé`. Both divergences were reproduced in this environment.

  Sorting by Unicode **code point** **MUST NOT** be used either. It agrees with code-unit order
  for names in the Basic Multilingual Plane and diverges outside it, which makes it the kind of
  defect that passes every test until it doesn't (SPEC §4.1, item 1).

### 5.4 Digest, and the non-digestible case

The **tool-set digest** is the SRI encoding of SHA-256 over the RFC 8785 canonical form (SPEC
§4) of the normalised, sorted array.

SPEC §4.3 forbids non-integer JSON numbers in signed documents because implementations disagree
about their serialization *silently*. JSON Schema permits them freely — `multipleOf`,
`minimum`, `default` — so a real tool schema may contain one.

MTL/1 does not arbitrate. **A tool set containing a non-integer JSON number is not digestible
under MTL/1.** When one is encountered:

- the issuer **MUST NOT** compute or publish a `toolSet.digestSRI`, and **MUST** omit it from
  the MSD (§4.2);
- the label **MUST** carry `verdict: "inconclusive"` and **MUST** report `MTL-NUM-001` in
  `mcpTrustLabel.reasons`, naming the offending tool;
- a continuity comparison involving such a subject **MUST** be `inconclusive`, never `fail`
  (§7.4), because there is no digest to compare.

The subject remains well-formed and identifies the server and its tool *names*. What is
withheld is the strong claim, not the label.

This rule is why an issuer needs no number-serialization code of its own: the AWR/2 reference
canonicalizer already refuses such a value with `AWR-CANON-001`, and MTL/1 maps that refusal to
`MTL-NUM-001`.

### 5.5 This is not WARDEN's `canonicalToolsHash`

The ARGUS WARDEN pinning gate computes a superficially similar hash and MTL/1 **MUST NOT** use
it as a subject digest or a tool-set digest. Two defects, both instances of the failure class
SPEC Appendix D was written to close:

1. It sorts tool names with `String.prototype.localeCompare`, which is ICU- and
   locale-dependent and disagrees with the code-unit order RFC 8785 mandates (§5.3).
2. It serialises with `JSON.stringify`, so a schema containing a non-integer number is written
   with JavaScript float formatting instead of being refused (§5.4).

A conformant reimplementation performing the obvious byte-wise sort computes a different digest
for the same tool set — which would surface to a registry as spurious drift.

An issuer **MAY** carry WARDEN's hex hash as an additional `evidence` entry with
`kind: "argus-tool-pin"` for cross-referencing against local ARGUS state. It **MUST NOT** be
placed in `verifiedWork.digestSRI` or `toolSet.digestSRI`.

---

## 6. The label document

### 6.1 `credentialSubject`

```json
"credentialSubject": {
  "verifiedWork": {
    "id": "urn:awr:mtl:1:subject:sha256:9cd47aba…",
    "digestSRI": "sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s="
  },
  "verdict": "pass",
  "method": {
    "id": "urn:awr:mtl:1:method:tool-def-pattern-scan",
    "name": "MTL/1 tool-definition pattern scan"
  },
  "evidence": [
    { "kind": "mtl-subject-descriptor", "digestSRI": "sha256-nNR6…=" },
    { "kind": "mtl-tool-set",           "digestSRI": "sha256-9+Gp…=" },
    { "kind": "mtl-pattern-set",        "digestSRI": "sha256-TeFg…=" }
  ],
  "mcpTrustLabel": { "…": "§6.3" }
}
```

Elided digests are abbreviations of the real values in
`examples/pass-01-pattern-scan.awr.json`; that file is the complete document.

### 6.2 One method per label

A label **MUST** name exactly one method (SPEC §3.4 already requires a single `method.id`), and
its `verdict` **MUST** be the outcome of that method alone. An issuer running several methods
**MUST** issue several labels and **MAY** ship them in an AWR bundle (SPEC §9).

Combining methods into one verdict is forbidden because the methods are not of comparable
strength: a digest comparison is dispositive and a regex match is not, and any combining rule
would have to grant one the other's authority.

> **Bundle gotcha — executed 2026-07-31, a two-label bundle reports `AWR-BUNDLE-003` at exit 1.**
> The AWR/2 reference implementation's bundle entry point resolves
> the bundle's subject by finding the one `WorkReceipt` not referenced as a parent. A bundle of
> labels contains no `WorkReceipt`, so it is reported as `AWR-BUNDLE-003` (subject ambiguous)
> unless the caller names a subject document explicitly. A registry **SHOULD** therefore verify
> each label document individually rather than relying on bundle subject resolution
> (`registry-integration.md` §3).

### 6.3 The `mcpTrustLabel` block

```json
"mcpTrustLabel": {
  "profile": "MTL/1",
  "observedAt": "2026-07-30T09:00:00Z",
  "reproducibility": "deterministic",
  "server": { "name": "com.example/weather", "registry": "urn:awr:mtl:1:registry:example" },
  "toolSet": { "count": 2, "digestSRI": "sha256-9+Gp…=" },
  "scope": "…",
  "patternSet": { "id": "urn:…", "digestSRI": "sha256-…=" },
  "patternMatches": [],
  "reasons": []
}
```

- `profile` **MUST** be `"MTL/1"`.
- `observedAt` **MUST** be an RFC 3339 UTC `date-time` with `Z` offset: when the issuer
  retrieved the tool set. It is the issuer's assertion; MTL/1 has no timestamping authority
  (§13.5). It is distinct from `validFrom`, which is when the label was issued.
- `reproducibility` **MUST** be `"deterministic"` on a label and `"model-dependent"` on an
  opinion (§7.6). A registry **MUST** reject a document whose `reproducibility` disagrees with
  its type (`MTL-OPIN-001`).
- `server` **MUST** restate `server.name` and `server.registry` from the MSD, so a registry can
  read the label without holding the descriptor. It is not evidence of anything: only §4.6's
  recomputation binds the label to a server.
- `toolSet` **MUST** restate `count`, and **MUST** restate `digestSRI` when the MSD carried one.
- `scope` **MUST** be a human-readable string stating, in plain words, what was and was not
  examined. It **MUST NOT** claim more than the method's §7 definition permits. It exists
  because a registry's UI will be read by people, and the honest sentence must travel inside
  the signature rather than live in a template the registry controls.
- `reasons` is **OPTIONAL** and, when present, **MUST** be an array of objects with a `code`
  from §11 and a human-readable `detail`.
- Method-specific members are defined in §7.
- Unknown members **MAY** be present; a registry **MUST** ignore them semantically and
  **MUST NOT** strip them (SPEC §3.1).

### 6.4 No score

A label **MUST NOT** carry `score`, and a registry **MUST** reject one that does
(`MTL-DOC-003`).

MTL/1 registers no method whose output is a calibrated number. The available implementation's
score is a product of gate contributions, one of which is a constant emitted by a gate that
never executes (§8.1), so its numeric range does not mean what a reader would take it to mean:
the value for a flawless first-contact server is **0.540**. Publishing that as a `[0,1]` safety
score in a signed document would be the single most misleading thing this profile could do.

Registries wanting one glyph should derive it from the verdicts and say how (§9.3).

---

## 7. Methods

### 7.1 Method registry

| Method id | Deterministic given the observed bytes | `pass` | `fail` | Section |
|---|---|---|---|---|
| `urn:awr:mtl:1:method:tool-set-observation` | yes | tool set retrieved and digested | **never** | §7.2 |
| `urn:awr:mtl:1:method:tool-def-pattern-scan` | yes | zero patterns matched | **never** | §7.3 |
| `urn:awr:mtl:1:method:tool-set-continuity` | yes | subject digest unchanged | digests differ | §7.4 |
| `urn:awr:mtl:1:method:name-threat-match` | yes | no record matched | **never** | §7.5 |
| `urn:awr:mtl:1:opinion:*` | **no** | — | — | §7.6 |

A registry **MUST** treat a label whose `method.id` is not registered above as unknown and
**MUST NOT** render it as a trust signal (`MTL-METH-001`). It **MAY** store it. A label whose
`verdict` is not permitted for its method **MUST** be rejected (`MTL-METH-002`).

`urn:awr:` is not an IANA-registered URN namespace. SPEC §3.4 makes `method.id` opaque, and
comparability comes from exact string equality, not from resolution.

Three of the four methods can never return `fail`. That is the profile's central honesty
commitment, not an oversight: `fail` in AWR means the verifier judged the work wrong, and none
of those three methods can establish wrongness. §7.3 records the measurement that settles it.

### 7.2 `tool-set-observation`

**Claim.** At `observedAt`, the server identified by the MSD advertised exactly the tool
definitions whose MTL/1 canonical digest is `toolSet.digestSRI`.

**Procedure.** Connect; complete the MCP initialise handshake; drain `tools/list` (§5.1);
normalise, sort and digest (§5); build the MSD (§4); issue.

**Determinism.** Deterministic *given the observed bytes*: no model, no clock in the decision, no
scoring. The observation itself is **not** reproducible by a second party — it is a live network
operation against a party that can vary what it advertises per client (§13.4). A second party
re-checks the digest over the bytes the issuer published; it does not re-perform the retrieval,
and nothing in the label establishes that the retrieval happened (§13.5).

**Outcomes.**

| Verdict | When |
|---|---|
| `pass` | the tool set was fully drained, is non-empty, and was digested |
| `inconclusive` | connection or handshake failed; pagination could not be drained; the tool set was empty (`MTL-SUBJ-002`); a tool entry was malformed (`MTL-SUBJ-001`); duplicate names (`MTL-SUBJ-003`); a non-integer number made the set non-digestible (`MTL-NUM-001`) |
| `fail` | **MUST NOT** be issued |

`fail` is excluded because there is no proposition to be false. A server that cannot be reached
has not been shown to be anything.

**Required members.** `toolSet.digestSRI` on `pass`. `reasons` on `inconclusive`.
`evidence` **MUST** include `{"kind": "mtl-subject-descriptor"}` and, on `pass`,
`{"kind": "mtl-tool-set"}`.

This is the strongest signal MTL/1 carries, and it is a statement about advertised text, not
about safety.

### 7.3 `tool-def-pattern-scan`

**Claim.** The tool names, descriptions and JSON schemas in the digested tool set were matched
against the pattern set identified by `patternSet.id` and digested by `patternSet.digestSRI`,
and these matches occurred — no more.

**Procedure.** For each normalised tool entry, run every pattern in the pattern set against the
surfaces that pattern declares: the tool `name`, the `description`, the serialised `inputSchema`.
Record `{code, severity, tier, tool, where}` per match, where `where` names the surface that
matched and `tier` is the one the published pattern table records for that `code`.

Surfaces are per-rule and are published with the table (`rules[].surfaces`, summarised as
`scannedFields`). A rule keyed on a NOUN — `api_key`, `private_key`, `.env` — declares only the
prose surfaces, because it matches ordinary identifiers and `sign_with_private_key` is a plausible
tool name. A rule keyed on a PHRASE cannot match `snake_case` at all, and the two hidden-payload
rules are about characters that are never legitimate in a name, so those run on the name too.

**Determinism.** Total, given the pattern set: pure pattern matching over strings the issuer
already committed to by digest.

**Required members.**

- `patternSet` **MUST** be present with a non-empty `id` and a `digestSRI` over the published
  pattern table (`MTL-PSET-001` if absent). Two scan labels are comparable only when their
  pattern-set digests are equal; without the digest the label is unfalsifiable, since the issuer
  could have run anything.
- `patternMatches` **MUST** be present, **MUST** be an array, and **MUST** list every match.
  On `pass` it **MUST** be empty.
- Every entry **MUST** carry the matched rule's `tier`, and a consumer **MUST NOT** present an
  `advise` match as a blocking finding.

  ARGUS ruleset v2 gave each rule a tier: a `block` rule can refuse a connection, an `advise`
  rule is reported and never blocks at any `blockAtSeverity` and never affects the composite
  score. The distinction is not cosmetic — v1 had one tier, so a schema field named `api_key`
  weighed the same as "ignore all previous instructions" and the scanner refused most real
  MCP servers. A label that flattens the tiers back into one list reintroduces exactly that
  error at the display layer, and its reader has no way to tell a poisoned definition from a
  server that documents an API key.

  The published table in
  [`examples/pattern-set-argus-warden-static-scan.json`](examples/pattern-set-argus-warden-static-scan.json)
  is generated from the shipping gate, not transcribed, and records the gate's own
  `version` and `digest` alongside each rule's tier and surfaces. Regenerate it rather than editing
  it.

  Ruleset **v3** added the surfaces, and with them the tool `name` as a scanned field. Before v3 the
  name was scanned by nothing at all, so an injection phrase, a zero-width character or a base64
  blob sat unreported in the one field that reaches the model first. A label issued under a
  pre-v3 pattern set therefore says nothing about the tool names it covered — which is what the
  pattern-set digest is for.

**Outcomes.**

| Verdict | When |
|---|---|
| `pass` | zero patterns matched |
| `inconclusive` | one or more patterns matched; every match listed in `patternMatches` |
| `fail` | **MUST NOT** be issued |

**Why `fail` is forbidden, measured.** The pattern set available in this ecosystem produces
matches on ordinary benign definitions. Executed against `warden/dist/static-scan.js` over
the exact two-tool definitions in `examples/generate.py` — a `create_issue` tool whose description
says "Requires a personal access token with repo scope" and whose schema has an `api_key`
property, and a `list_files` tool whose description contains the words "instead of" (re-measured
2026-08-24 under ruleset v3; v3 scans the names too, and neither `create_issue` nor `list_files`
matches anything):

| Tool set | Matches | Gate score |
|---|---|---|
| the two benign tools above | **3**, all `advise` — `TOOL_DEF_CREDENTIAL_PARAM` (`low`, description), `TOOL_DEF_CREDENTIAL_PARAM` (`low`, input schema), `TOOL_DEF_IMPERATIVE` (`info`, description) | **1.0** |
| one tool, neutral description, `api_key` property only | 1 `advise` — `TOOL_DEF_CREDENTIAL_PARAM` (`low`) | 1.0 |
| one tool, "instead of" in the description only | 1 `advise` — `TOOL_DEF_IMPERATIVE` (`info`) | 1.0 |
| two tools, plain weather/city definitions | 0 | 1 |

Not one of those rows is refused, at any `blockAtSeverity`: an `advise` match never blocks and
never touches the score. That is the point, and it is what changed. Ruleset **v1** scored row one
`0.40` with two matches at `high` and blocked it at the default threshold; **an `api_key` property
alone was sufficient** to refuse a server whose schema legitimately accepts an API key. v2 gave
every rule a tier and moved those rules to `advise`.

The measurement therefore now supports the rule from the other direction. The matches still
happen — three of them, on text nobody should be penalised for — but the scanner that produces
them declines to treat them as defects. A label that rendered them as `fail` would be strictly
harsher about a server than the gate that scanned it, which is why `fail` is forbidden for this
method and why every entry **MUST** carry its tier: a reader who cannot see `advise` is looking at
v1's calibration again, in the display layer. SPEC §3.4's requirement that `inconclusive` not be
treated as a failure is what makes the honest outcome expressible.

**Severity is not risk.** The `severity` value on a match is the pattern set's own label. MTL/1
attaches no meaning to it, defines no mapping from it to a risk level, and a registry **MUST
NOT** invent one or sort by it (§9.2). Reporting the code is the claim; ranking the codes would
be a new, unvalidated judgement wearing the label's signature.

**Evasion.** The pattern set is public by construction (it must be, to be digestible and
checkable), so evading it requires only paraphrase. A `pass` here means "the obvious tells are
absent", which is weak, and §9.2 forbids rendering it as more.

### 7.4 `tool-set-continuity`

**Claim.** The subject digest computed at `observedAt` equals, or does not equal, the subject
digest of the referenced prior label.

**Procedure.** Retrieve and digest the tool set as in §7.2. Compare the resulting subject
digest with `verifiedWork.digestSRI` of a previously issued, still-verifiable MTL label over
the same `server.name` and `server.registry`.

**Required members.**

- `priorLabel` **MUST** be present with `id`, `digestSRI` — a digest reference to the **secured**
  prior label document, per SPEC §3.2 — and the prior label's `observedAt`. The digest
  reference is what stops a continuity claim being re-pointed at a different history
  (`MTL-CONT-001` when absent or unresolvable).
- `unchangedSince` **MUST** be present on `pass`: the `observedAt` of the earliest label in the
  unbroken chain of `pass` continuity labels the issuer is asserting.
- `evidence` **MUST** include `{"kind": "mtl-prior-label"}` carrying the same digest.

**Outcomes.**

| Verdict | When |
|---|---|
| `pass` | both subject digests are present and equal |
| `fail` | both subject digests are present and differ |
| `inconclusive` | no prior label exists; the prior label cannot be verified; either side lacks a `toolSet.digestSRI` (`MTL-NUM-001`); the current observation failed |

`fail` is permitted here, uniquely, because it is a mechanical statement about two committed
digests rather than a judgement: the advertised definitions changed. **It is not an accusation.**
A version bump changes definitions. §9.2 requires it be rendered as a change with a date, never
as maliciousness.

**What continuity does not prove.** That the definitions did not change *between* two
observations, and that behaviour did not change while the definitions held. A remote server can
serve identical definitions and different behaviour indefinitely (§13.4). The claim is exactly
two point observations and their equality.

### 7.5 `name-threat-match`

**Claim.** The server's registry-scoped name and advertised transport coordinates were matched
against the record set identified by `recordSet.id` and digested by `recordSet.digestSRI`, and
these records matched — no more.

**Scope, stated precisely because it is narrow.** The available implementation's threat gate
builds its haystack from the server's `id`, `name`, `url`, `command` and `args` and nothing
else. **Tool definitions are never examined by this gate.** For a registry the honest reading
is therefore: *this name and these coordinates are not on a published list.* Of the 11 built-in
records (counted in `warden/src/threat-feed.ts`), three are typosquat patterns over names,
**two** are crypto-drainer keyword patterns whose reason string the implementation itself writes
as "Crypto-drainer keyword in server identity", and one more is a wallet-seed-phrase keyword whose
reason string is "Server references wallet seed phrases"; that six-record subset is the part with
any reach over a registry record. The remaining five target strings that occur in a locally
written command line — an SSH key path, a private key filename, a recursive delete, a fork bomb,
an environment-file exfiltration phrase — where a registry has nothing to match. An issuer
**MUST NOT** describe this method as scanning the server, and `scope` **MUST** say what was
matched.

**Required members.** `recordSet` with a non-empty `id` and a `digestSRI` over the published
record table (`MTL-PSET-001` if absent), plus `recordMatches` as an array listing every match
(empty on `pass`).

**Outcomes.**

| Verdict | When |
|---|---|
| `pass` | no record matched |
| `inconclusive` | one or more records matched, each listed in `recordMatches` |
| `fail` | **MUST NOT** be issued |

A name match is a naming-similarity signal — a typosquat suspicion — not evidence about code,
so `fail` is unavailable for the same reason as in §7.3.

**Feed freshness: there is none, so pin the set.** The available implementation accepts a
remote record set carrying an Ed25519 signature and a `timestamp`, parses the timestamp, and
never compares it to anything: there is no maximum age, no staleness check and no revocation.
A validly signed snapshot is therefore accepted indefinitely, and whoever serves the feed URL
can replay an old snapshot to make newer records disappear. Its signature is also computed over
`JSON.stringify` of parsed wire JSON, so the signed byte string depends on the key order the
wire happened to use, and a logically identical feed can fail its own verification.

Consequently MTL/1 **REQUIRES** that the record set be pinned by digest in every label, so a
registry can see exactly which set was used and detect a rollback by comparing digests across
labels. An issuer **SHOULD** publish the record set alongside its labels, and **SHOULD** prefer
a built-in set over a remote feed until the freshness gap is closed upstream. An issuer
**MUST NOT** state or imply that the record set was current at `observedAt`.

### 7.6 Opinions — model-dependent statements are not labels

A statement whose outcome depends on a model's judgement is **not reproducible**: a second
party cannot recompute it, so it cannot carry a verdict's authority. MTL/1 does not exclude
such statements — they are often the most informative thing anyone can say about a server — but
quarantines them completely.

An opinion document **MUST**:

- carry `MCPTrustOpinion` in `type` and **MUST NOT** carry `MCPTrustLabel`;
- name a method under the `urn:awr:mtl:1:opinion:` arc and no other;
- carry a non-empty `method.modelIds` (SPEC §3.4);
- set `mcpTrustLabel.reproducibility` to `"model-dependent"`;
- carry no `score` (§6.4);
- carry a `scope` stating that the outcome is a model's judgement and is not reproducible.

A registry **MUST NOT**:

- render an opinion in a label slot, badge or filter;
- aggregate an opinion with any label, or let it affect a label's display;
- display an opinion without naming the model and the issuer.

Violations are `MTL-OPIN-001`.

MTL/1 **registers no opinion methods.** No model-dependent MCP-server judgement is issued by
any component examined for this profile — the four gates in the available implementation are
regex, glob and digest comparisons with no model in the loop. §7.6 exists so that when one
appears, it cannot be smuggled into a deterministic method id and inherit a signature's
credibility.

---

## 8. Excluded signals

Each exclusion is a signal that exists in the implementation and is **not** admissible as
label content, with the reason it fails.

### 8.1 Network reputation score — excluded: it never executed, and has since been removed

The reputation gate asked the LUMEN trust oracle for the server's score by calling
`scoreEntity(serverId)` with **no trust edges**. `scoreEntity` returns
`{score: 0.5, degraded: true}` immediately whenever the edge list is empty or absent, before
any network call, and no call site passed edges. The early return preceded the `fetch`, so the
oracle invocation path — including the graph commitment it would read — was unreachable in
production, and the gate's own message that the oracle was "unreachable" was false: nothing had
been attempted.

**The gate has since been removed from the implementation**, and a regression test
(`warden/test/no-phantom-gate.test.ts`) now fails if any gate in the chain reports a service as
unreachable without having sent a request, or taxes the composite score for a measurement it
never took. The exclusion below stands on its own terms regardless: a score that is a constant is
not a measurement, and publishing one about a server would be publishing a fixture.

Under the default permissive policy the gate contributes a constant **0.6**. Under a strict
policy the same branch is fatal, so strict mode blocks *every* server unconditionally.

A constant is not a signal. It **MUST NOT** appear in a label, in `evidence`, or in any derived
number. A future MTL version **MAY** register a reputation method once the score is computed
from real edges and its input graph is committed by digest.

### 8.2 Composite safety score — excluded: not a safety level

The composite is the product of the four gate scores. Because one factor is the constant of
§8.1 and a first-contact server scores 0.9 on pinning, the ceiling for a flawless,
never-before-seen server is `0.6 × 0.9 × 1 × 1 = 0.540`. The number is a constant times a
first-contact penalty, not a calibrated risk estimate, and its scale invites exactly the
misreading a signed document must not enable. **MUST NOT** be published; see §6.4.

### 8.3 Allow/block decision — excluded: policy, not a property of the server

The allow/block outcome is a function of the caller's configured blocking threshold and rule
tiers, not of the server: the same `block`-tier `medium` match refuses a connection under
`blockAtSeverity: "medium"` and passes under `"high"`, and under ruleset v1 the benign two-tool
server of §7.3 was blocked at the default threshold while under v2 it is not. Two registries
publishing "blocked" about the same server would be publishing their own configuration. It is a
local policy decision, correct to make locally and meaningless to publish about a server. **MUST
NOT** appear in a label.

### 8.4 Host security posture — excluded: different subject

The ecosystem's posture scoring is fleet and host observability — access logs, open ports,
firewall and TLS state of *machines*. It does not examine MCP servers, and its subject is not
the subject of §4. A host posture grade **MUST NOT** be presented as an MCP server label.

### 8.5 Source, package and supply-chain provenance — excluded: never performed

No component examined reads an MCP server's source, resolves its package, verifies a signature
on a published artefact, or checks that an installed artefact matches a scanned one. There is
no signal to admit, and §12 states the consequence.

### 8.6 Runtime behaviour — excluded: never observed

Every method above reads *advertised definitions*. No tool is invoked, no live
tool result is inspected, and no traffic is observed. A label says nothing about what the
server does when called (§13.4).

---

## 9. Registry rendering

**Scope of every requirement in this section, and in §4.6 and §13.2.** These requirements bind a
consumer that chooses to claim MTL/1 conformance. MTL has no authority over anyone and asks for
none (§1.3 principle 5): it is a draft profile with no adopters, and it is not a standard of the
Model Context Protocol project. A registry may read labels, ignore this section and be in
violation of nothing — it simply is not claiming MTL/1 conformance. The BCP 14 capitals below say
what conformance means, not what anyone owes us.

### 9.1 Required elements

When a registry claiming MTL/1 conformance displays a label it **MUST** show:

1. the outcome (§9.2), in the vocabulary of §9.2;
2. the issuer — `issuer.id`, or a registry-controlled name bound to that DID in a
   registry-maintained list. `issuer.name` inside the document is issuer-supplied and **MUST
   NOT** be shown as an identity (SPEC §3.1 gives it no trust weight);
3. `mcpTrustLabel.observedAt`, as the age of the observation;
4. what was checked — `method.name` or a registry string keyed on `method.id`.

A registry **MUST NOT** render a label as a bare check mark, badge or colour without the issuer
and the observation date. SPEC §13.7 is explicit that validity means only "this issuer signed
these claims, and the bytes are intact"; a glyph without an issuer misrepresents the format.

### 9.2 Vocabulary

A registry **MUST NOT** use the words **safe**, **secure**, **audited**, **certified**,
**approved**, **trusted**, or an unqualified **verified** to render any MTL outcome. None is
supported by any method in §7.

| Outcome | Render as | Never as |
|---|---|---|
| `pass` on `tool-set-observation` | "Tool definitions pinned <date> by <issuer>" | "Verified", "Audited" |
| `pass` on `tool-def-pattern-scan` | "No known injection or secret-request patterns in the advertised definitions (pattern set <id>)" | "Safe", "Clean", "No vulnerabilities" |
| `pass` on `tool-set-continuity` | "Definitions unchanged since <unchangedSince>, <N> observations" | "Stable and secure" |
| `pass` on `name-threat-match` | "Name and coordinates not on threat list <id>" | "Not malicious" |
| `inconclusive` on a scan | "<N> patterns matched — see details" plus the codes | "Failed", "Dangerous", a red state |
| `fail` on `tool-set-continuity` | "Tool definitions changed on <observedAt> — re-approval recommended" | "Compromised", "Rug-pull detected" |
| no label | "No label" | "Failed", or ranked below a label with `inconclusive` |

Additional requirements:

- `inconclusive` **MUST** be rendered as a neutral, informational state. It **MUST NOT** be
  styled as failure, **MUST NOT** be aggregated into a failure count, and a server holding one
  **MUST NOT** be ranked below an unlabelled server. Suppressing `inconclusive` is what turns
  verifiers into rubber stamps (SPEC §3.4), and penalising it teaches issuers to launder it
  into `pass`.
- A registry **MUST NOT** derive an ordering from match `severity` values (§7.3).
- A registry **SHOULD** show `mcpTrustLabel.scope` verbatim on a details view. It is inside the
  signature precisely so the honest sentence cannot be replaced by a template.

### 9.3 Deriving one glyph

A registry that needs a single indicator **MAY** derive one, and if it does it **MUST** publish
the rule and **MUST NOT** attribute the result to the label issuer. The derivation is the
registry's claim, not the issuer's.

A rule that stays within what §7 supports:

- **Pinned** — a valid `tool-set-observation` `pass` from an allow-listed issuer.
- **Pinned, unchanged N days** — additionally a `tool-set-continuity` `pass` whose
  `unchangedSince` is N days old.
- **Changed** — a `tool-set-continuity` `fail`, with the date.
- **Flagged for review** — any `inconclusive`, with the codes.
- **Unlabelled** — no valid label.

None of those words claims safety, and the first three are statements a reader can check.

### 9.4 Corroboration is the substitute for L1, and it is a weak one

Because a label has no receipt issuer to differ from, AWR's L1 structural guarantee is
unavailable (§3.2). The substitute a conformant registry **MAY** display is the count of
**distinct issuer DIDs** holding valid labels with the **same** `verifiedWork.digestSRI` and the
same `method.id`.

**What that count is, and what it is not.** Two distinct issuer DIDs signing the same subject
digest is checkable — that part is real. But **a corroboration count computed over DIDs the
consumer has not allow-listed as separate operators is not a signal; it is a count of keypairs.**
Distinct DIDs are distinct *keys*, keygen is free (§13.2), and two other explanations satisfy the
same count exactly: one party holding two keypairs, or a copier who never retrieved anything and
lifted the digest out of the first label, where it is published in the clear. It is evidence that
two **parties** retrieved and canonicalized identically only if the consumer's allow-list (§13.2)
records the two keys as separately operated, which is a judgement the consumer must make out of
band because MTL/1 provides no mechanism for it. §13.3 states the same thing as an attack.

A registry that displays a corroboration count therefore **MUST** compute it over allow-listed
DIDs only, and **MUST NOT** present a count over unknown DIDs as agreement between parties. This
profile's own issuer would satisfy an unfiltered count by generating keys, and so would anyone
else.

Two issuers *disagreeing* on the subject digest for the same server name at nearby `observedAt`
values is a signal of a server that varies its advertised definitions by client, and a registry
**SHOULD** surface it rather than pick a winner. It inherits the same precondition: the detector
means something only when the two DIDs are known to be separately operated.

A single label — however valid — **MUST NOT** be rendered as corroborated.

---

## 10. Publication and retrieval

Normative minimum; the operational detail is in `registry-integration.md`.

- A label **MUST** be retrievable as a standalone JSON document, media type `application/vc`
  (SPEC §15), without authentication (SPEC §15 forbids requiring it for documents intended to
  be independently verifiable).
- Several labels **MAY** be shipped as an AWR bundle (SPEC §9), media type `application/json`.
  §6.2's gotcha applies: verify the documents individually.
- The MSD **SHOULD** be published alongside its labels so that a registry unable to retrieve
  the tool set itself can still recompute the subject digest (§4.6).
- A digest-addressed location **SHOULD** be served with `Cache-Control: immutable` (SPEC §15).
- A registry **MUST NOT** fetch anything during verification (SPEC §13.5). Retrieval and
  verification are separate phases: fetch, then verify offline.

**Signature survival is not meaning survival.** A label's signature is self-contained and keeps
verifying forever, including after its issuer disappears. Its *content* is not self-contained: a
pattern-scan label is comparable only via `patternSet.digestSRI` (§7.3 — "without the digest the
label is unfalsifiable"), a continuity label needs the prior label it references
(`MTL-CONT-001`), and publication of both is only a **SHOULD** above. When an issuer vanishes, an
unresolvable pattern-set digest leaves a valid signature over a sentence a consumer cannot
interpret: "no known patterns matched (pattern set `<unknown>`)". A consumer **SHOULD** therefore
cache, keyed by digest, every pattern set, record set, MSD and prior label its labels reference,
at the time it receives them. A consumer that does not is depending on the issuer's continued
existence for the label's meaning, which is the dependency this profile otherwise avoids.

---

## 11. Reason codes

MTL codes are namespaced `MTL-` and are disjoint from the AWR registry (SPEC §11.2), which
continues to apply unchanged. `detail` strings are human-readable, unstable, and **MUST NOT**
be parsed (SPEC §11.1).

| Code | Severity | Meaning |
|---|---|---|
| `MTL-SUBJ-001` | error | Tool entry is not an object, or has no non-empty string `name` |
| `MTL-SUBJ-002` | error | Tool set is empty; there is nothing to pin |
| `MTL-SUBJ-003` | error | Duplicate tool name; the digest would depend on retrieval order |
| `MTL-SUBJ-004` | error | Registry-recomputed subject digest ≠ `verifiedWork.digestSRI` (§4.6) |
| `MTL-NUM-001` | error | Non-integer JSON number in a tool schema: not digestible under MTL/1 (§5.4) |
| `MTL-DOC-001` | error | `type` lacks `MCPTrustLabel`/`MCPTrustOpinion`, or `@context` lacks the MTL namespace |
| `MTL-DOC-002` | error | `mcpTrustLabel` missing, not an object, or missing a required member |
| `MTL-DOC-003` | error | Label carries `score` or `policy.threshold` (§6.4) |
| `MTL-METH-001` | error | `method.id` is not registered in §7.1 |
| `MTL-METH-002` | error | `verdict` is not permitted for this method (§7.1) |
| `MTL-PSET-001` | error | Pattern-set or record-set digest missing (§7.3, §7.5) |
| `MTL-CONT-001` | error | Continuity label without a resolvable `priorLabel` digest reference (§7.4) |
| `MTL-OPIN-001` | error | Opinion typed or rendered as a label, or missing `modelIds`/`reproducibility` |
| `MTL-PROF-001` | error | Label advertised or evaluated as satisfying AWR profile L1 or L2 (§3.2) |
| `MTL-ISS-001` | warning | Issuer DID is not on the consumer's allow-list (§13.2) |
| `MTL-AGE-001` | warning | `observedAt` is older than the consumer's policy allows |

`MTL-AGE-001` is a **warning**, never invalidity: SPEC §11.3 makes age a policy question, and
an old label is exactly as cryptographically sound as a new one. A registry applies its own
threshold and **MUST** show the date rather than silently hiding the label.

---

## 12. Non-goals — what the label does not establish

A valid MTL label establishes exactly two things: that the holder of a named key signed a claim
about a committed digest, and that the bytes are intact. Everything the claim *says* is the
issuer's assertion, and a consumer who has not recomputed the subject digest does not even have
the binding between the claim and a server (§4.6, §13.1). The label does **not** establish, and
**MUST NOT** be represented as establishing, any of the following.

**About the code**

1. That the server's source code was read, reviewed or audited. **No component of the issuing
   ecosystem reads an MCP server's code** (§8.5).
2. That the server is free of vulnerabilities, backdoors or malicious logic.
3. That the published package corresponds to the code that was observed, or that installing the
   named package yields what was scanned.
4. That any dependency, transitive or direct, was examined.

**About behaviour**

5. That the server behaves as its tool descriptions say. Nothing was invoked (§8.6).
6. That the server does not exfiltrate data, escalate privileges or take destructive action at
   run time.
7. That the server behaves the same for another client, at another time, or from another
   network position. A remote server can serve one set of definitions to a scanner and another
   to a user (§13.4).
8. That tool *output* is safe. Only advertised definitions were examined; injection delivered
   through a tool's runtime result is entirely outside MTL/1 — as are resources and prompt
   templates.

**About the signals**

9. That a `pass` on a pattern scan means no injection is present. It means the published
   patterns did not match, and paraphrase defeats them (§7.3).
10. That a `pass` on a name-threat match means the server is not malicious. Only its name and
    coordinates were compared to a list (§7.5).
11. That an `inconclusive` means the server is dangerous. It means a signal was suggestive and
    the issuer declined to draw a conclusion (§9.2).
12. That unchanged definitions mean unchanged behaviour (§7.4).
13. That the threat record set was current. There is no freshness check upstream (§7.5).

**About authority**

14. That the issuer is competent, honest or accredited. Anybody can generate a `did:key`. MTL
    creates no accreditation and no trust root (§13.2).
15. That the label satisfies an AWR assurance profile. L0/L1/L2 do not apply (§3.2).
16. That anything was verified on-chain, staked or paid for. MTL/1 requires no economics, and
    SPEC §10.3 forbids a verifier from checking a binding over the network.

**About coverage**

17. That the absence of a label means anything about a server. It usually means nobody ran a
    scanner (§9.2).

---

## 13. Security considerations

SPEC §13 applies in full. These are the additions specific to this subject class.

### 13.1 Subject substitution is the primary attack

A label is a portable, valid document about *some* subject. Whoever controls a listing pipeline
can attach a clean server's label to a different server, and every signature check will pass —
the format is working correctly; the claim is simply not about what the page says it is about.
§4.6's recomputation is the only defence, and it is **REQUIRED**, not advisory. A registry that
displays labels without recomputing subject digests has built a system where a valid signature
certifies the wrong thing.

### 13.2 No authority, so allow-list issuers

A `did:key` costs nothing to generate. An attacker can issue a perfectly valid `pass` label
about their own malicious server, from a fresh DID, all day. MTL adds accountability, not
authority: it makes the claim attributable, and attribution only helps if the consumer knows
whose claims it accepts.

A registry claiming MTL/1 conformance **MUST** maintain an explicit allow-list of issuer DIDs
whose labels it renders as trust signals, and **SHOULD** report `MTL-ISS-001` for others.
Rendering "signed by someone" as a trust signal is worse than rendering nothing, because it
converts a free operation into a badge.

The allow-list **SHOULD** additionally record, per DID, whether the consumer believes it to be
operated separately from the others on the list. Nothing in AWR or MTL supplies that fact; it is
the consumer's own determination, and §9.4's corroboration count is meaningless without it. Note
what this asks: MTL declines to build an accreditation function (§1.3 principle 5) and then leaves
the consumer to perform one. That is a real gap in the profile, not a division of labour we can
justify — it is stated here so that nobody discovers it after building a badge.

Because AWR has no revocation (SPEC §13.6), removing a DID from the allow-list is the only
mechanism for retiring a compromised or discredited issuer, and it works only for consumers who
maintain one.

### 13.3 Gaming the signals

- **Pattern scan.** Public patterns, so paraphrase evades them. A `pass` costs an attacker one
  rewrite. §9.2's wording is calibrated to that.
- **Continuity.** An attacker who ships a poisoned definition *first* accrues an unbroken
  "unchanged for N days" history. Continuity measures stability, and a stable attacker is
  stable. It is not a substitute for reading the definitions on first approval.
- **Name-threat match.** Trivially evaded by choosing a name not on the list, which is most
  names.
- **Corroboration.** Cheap to fake by generating several DIDs, unless the consumer allow-lists
  issuers (§13.2). Counting DIDs is meaningless without that list.

### 13.4 Definition pinning does not pin behaviour

For a `stdio` server the definitions and the code ship together, so drift detection has real
force. For a remote server the definitions are served by the same party that serves the
behaviour: it can hold its advertised tool set constant forever while changing what the tools
do, and every continuity label will read `pass`. A registry **SHOULD** display `transport` next
to a continuity claim, because the claim's strength depends on it.

Correspondingly, a server can vary the definitions it advertises by client — serving clean text
to a scanner and poisoned text to users. §9.4's disagreement signal is the only detector MTL/1
offers, and it requires at least two issuers that the consumer knows to be **separately
operated** — two DIDs alone do not supply that, since one operator's two keys will agree by
construction.

### 13.5 Time is asserted, not proven

`observedAt` and `validFrom` are issuer claims. MTL/1 has no timestamping authority, so an
issuer can backdate `unchangedSince` and produce a longer history than it observed. Nothing in
the format detects it. Consumers get durability from a chain of labels they retrieved and whose
digests they stored themselves, not from any single label's dates.

### 13.6 Denial of service

Tool sets are attacker-controlled input. An issuer **MUST** bound the number of tools, the size
of each schema, and the total bytes it will canonicalize before canonicalizing, and **MUST**
bound pagination rounds when draining `tools/list` (SPEC §13.4). An unbounded drain of a hostile
server's paginated tool list is a trivially available resource exhaustion.

---

## 14. Privacy considerations

- A label carries digests, tool **names** and a server identity. Tool descriptions and schemas
  are not disclosed by publishing a label; the tool-set digest commits to them without
  revealing them.
- Server names and tool names are enumerable, so a subject digest is a confirmation oracle for
  "did this exact tool set exist". For a public registry listing this is not a leak — the
  listing is public. An issuer labelling a **private** or internal MCP server **SHOULD**
  consider that the label's digests confirm the existence and exact shape of an internal tool
  surface, and **SHOULD NOT** publish such labels.
- `issuer.id` is a stable pseudonymous identifier, fully correlatable across every label it
  signs (SPEC §14). An issuer scanning private servers alongside public ones links them.
- Offline verification means the issuer learns nothing about who verified a label, and the
  registry's readers are not disclosed to the issuer. SPEC §13.5 preserves this.

---

## Appendix A — Worked examples

`examples/` contains documents **whose signatures are genuine** — produced by the AWR/2 reference
implementation at `awr/reference/python`, not hand-written. `examples/generate.py` regenerates
them deterministically from fixed seeds and re-verifies each one before exiting; all four were
re-verified 2026-08-24 against the current bytes (`valid=true`, `profile=null` — SPEC §10.4: a
`VerificationVerdict` is not a `WorkReceipt` — 0 reasons, 0 warnings, exit 0 each), and `awr digest examples/pass-01-subject-descriptor.json`
reproduces
`sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s=`, the value §4.5's worked example quotes.

**Two things about these examples are not genuine, and a reviewer should know before reading
them.** They are the reason there is no MTL issuer in this repository.

1. **No server was contacted.** The tool arrays are literals in `generate.py` for two invented
   servers. `mcpTrustLabel.observedAt` is a fixed constant. No `tools/list` was ever drained,
   which means these labels demonstrate the *document format*, not the §7.2 procedure.
2. **The pattern matches are transcribed, not produced.** `generate.py` hardcodes
   `PATTERN_HIT_FINDINGS` as literals; the generator itself never executes the gate, because it
   must run with nothing but the reference implementation on the path.

   The pattern set is no longer a transcription. `pattern-set-argus-warden-static-scan.json` is
   **generated** by `tools/regen_pattern_set.mjs` calling `staticScanRuleset()` in
   `@aimarket/warden` — 25 rules, 15 `block`, 10 `advise`, version 4, 17 rules also covering the
   tool name — so the digest §7.3 makes the label falsifiable by now binds to the gate's own table
   rather than to a hand copy of it.

   `examples/test_examples.py` closes the rest of that gap with four checks: the table is
   regenerated and compared **byte for byte**; its `digest` must equal the gate's own
   `rulesets.staticScan.digest`; its rule codes must match `warden/src/static-scan.ts` (this one
   needs no build); and the hardcoded `patternMatches` are compared against a live run of
   `warden/dist/static-scan.js`, tiers included. Executed 2026-08-24: **21 passed.** Residual
   limits: the two node-dependent checks skip visibly when node or the build is absent, and
   `generate.py` still emits literals rather than gate output, so the *generator* remains a
   fixture rather than an issuer.

The three matches the examples record *were* reproduced against the shipping gate on 2026-08-24
(§7.3's table) — three `advise` matches, gate score 1.0 — so the numbers are right, and they are
not the numbers ruleset v1 produced.

| File | Method | Verdict |
|---|---|---|
| `pass-01-pattern-scan.awr.json` | `tool-def-pattern-scan` | `pass` — zero patterns matched |
| `inconclusive-01-pattern-scan.awr.json` | `tool-def-pattern-scan` | `inconclusive` — three matches, all `advise`-tier, all on benign text |
| `pass-02-tool-set-observation.awr.json` | `tool-set-observation` | `pass` |
| `pass-03-tool-set-continuity.awr.json` | `tool-set-continuity` | `pass` — unchanged since the earlier observation |
| `pass-01-subject-descriptor.json` | — | the MSD whose digest the first two labels commit to |
| `inconclusive-01-subject-descriptor.json` | — | the MSD for the pattern-hit server |
| `pattern-set-argus-warden-static-scan.json` | — | the digested pattern table |

The demonstration signing key is derived from a seed published in `generate.py`. It confers
nothing and **MUST NOT** be used to issue a real label. The server names, registry identifier
and package names in the examples are invented; no real MCP server is described, endorsed or
labelled.

## Appendix B — Provenance of the implementation claims

Every behavioural statement in §5.5, §7.3, §7.5 and §8 was checked against the code below, in
this repository, and re-checked on 2026-07-31 at 18:19–18:30 UTC while revising this document.
Statements marked *executed* were additionally reproduced by running the code in that same pass.
`argus/` is under active development like the rest of this repository; a reviewer should re-run
these rather than trust the table.

| Claim | Source |
|---|---|
| Gate chain and its order | `warden/src/index.ts` — `Warden.create` |
| Composite score is the product of gate scores | `warden/src/index.ts` — `vet` |
| Block decision is threshold-driven; default threshold `high` | `warden/src/index.ts`, `argus/src/config.ts` |
| 25 rules (15 `block`, 10 `advise`) in ruleset v4; 17 of them also scan the tool `name`, the 3 noun-keyed codes do not. v4 re-tiered three rules to `advise` on field evidence and added per-rule `guards`, which are inside the digest | `warden/src/static-scan.ts` |
| Gate score is `1 −` penalty for the worst **blocking** severity, i.e. one of {1, 0.9, 0.7, 0.4, 0}; `advise` matches are excluded from it | `warden/src/static-scan.ts` |
| **Executed (2026-08-24, ruleset v3):** benign two-tool server → 3 matches, all `advise` (2 `low`, 1 `info`), gate score 1.0, nothing blocked at any threshold; the two tool names match nothing | `warden/dist/static-scan.js` |
| **Executed:** clean two-tool server → 0 matches, gate score 1 | `warden/dist/static-scan.js` |
| **Executed (2026-08-24, ruleset v3):** one tool with a neutral description and an `api_key` property → 1 `advise` match (`TOOL_DEF_CREDENTIAL_PARAM`, `low`), gate score 1.0 | `warden/dist/static-scan.js` |
| **Executed (2026-08-24, ruleset v3):** one tool whose description contains "instead of" → 1 `advise` match (`TOOL_DEF_IMPERATIVE`, `info`), gate score 1.0 | `warden/dist/static-scan.js` |
| Pinning hash sorts with `localeCompare` and serialises with `JSON.stringify` | `warden/src/pinning.ts` — `canonicalToolsHash` |
| **Executed:** `"Z_tool".localeCompare("a_tool") === 1` vs code-unit `−1`; `résumé`/`rezume` inversion | Node in this environment |
| ~~Reputation gate calls `scoreEntity(id)` with no edges~~ — **removed since this pass.** The gate no longer exists; a regression test now fails if any gate reports a service as unreachable without having sent a request | `warden/test/no-phantom-gate.test.ts` |
| `scoreEntity` returns `{0.5, degraded}` on an empty edge list, before any fetch | `argus/src/economy/lumen.ts` |
| No call site anywhere passes edges | `grep -rn scoreEntity argus/src` → **4 matches**: the interface declaration (`types.ts:323`), the definition (`economy/lumen.ts:52`), and the **two** actual call sites (`cli/commands/passport.ts:22`, `warden/reputation.ts:28`), neither of which passes an `edges` argument |
| ~~Degraded gate contributes 0.6 permissive / fatal strict → ceiling 0.540~~ — **removed with the gate.** A clean, declared, unpinned server now scores exactly 0.9 (unpinned first contact only) | `warden/test/no-phantom-gate.test.ts`, `warden/src/pinning.ts` |
| Threat haystack is `id`/`name`/`url`/`command`/`args` for `scope: "server"` records; `ThreatRecord.scope` (added since this pass) also allows matching tool definitions | `warden/src/threat-feed.ts` — `match` |
| 11 built-in records: 3 name typosquats; 3 wallet/crypto keyword, of which **two** carry the reason string "Crypto-drainer keyword in server identity" and one carries "Server references wallet seed phrases"; 5 command-line | `warden/src/threat-feed.ts` — `BUILTIN` (`grep -n 'reason:'` → 11 records) |
| ~~`timestamp` is parsed and never used; no staleness check exists~~ — **fixed since this pass.** The signed timestamp must fall inside `maxAgeMs` (24 h default) and no more than 5 min ahead, or the remote feed is refused and the built-in floor kept | `warden/src/threat-feed.ts` |
| ~~Feed signature is over `JSON.stringify` of parsed wire JSON~~ — **fixed since this pass.** The signature is verified over the RFC 8785 canonical form of `{records, timestamp}` | `warden/src/threat-feed.ts` — `load`, `warden/src/jcs.ts` |
| No default feed URL or feed public key ships | `argus/src/config.ts` |
| No model is used by any warden gate | `warden/src/*.ts` |
| Host posture scoring has MCP servers nowhere in its subject | `skopos/security/posture.py` |
| **Executed:** a standalone label verifies `valid: true`, `profile: null` — SPEC §10.4: a `VerificationVerdict` is not a `WorkReceipt`, so it satisfies no profile, and null there does not mean "below L0" | `awr/reference/python`, `awr verify` |
| **Executed:** L1/L2 report `AWR-PROFILE-001` for a `VerificationVerdict` | `awr/reference/python/awr/verify.py` — `evaluate_profiles` |
| `AWR-VDCT-005` fires only when a same-`id` supporting document is supplied | `awr/reference/python/awr/verify.py` — `_cross_check_verdict` |
| **Executed:** a bundle with no `WorkReceipt` reports `AWR-BUNDLE-003` unless a subject is named | `awr/reference/python/awr/verify.py` — `verify_bundle` |
| The reference canonicalizer refuses non-integer numbers with `AWR-CANON-001` | `awr/reference/python/awr/jcs.py` |
| **Executed:** one flipped byte in a label → `AWR-PROOF-006`, exit 1 | `awr verify` |
| **Executed:** all four shipped labels → `valid=true`, `profile=null` (§10.4), 0 reasons, 0 warnings, exit 0 | `awr verify examples/*.awr.json` |
| **Executed:** `awr verify` emits nine top-level keys, and `profilesEvaluated` reports `AWR-PROFILE-001` for L1 and L2 | `awr verify` on `examples/pass-01-pattern-scan.awr.json` |
| `pattern-set-argus-warden-static-scan.json` is **generated** from the gate by `tools/regen_pattern_set.mjs` (`staticScanRuleset()`), so the drift test regenerates it and compares bytes; the rule codes are also checked against the source without a build, and the file's `digest` against the gate's own | `tools/regen_pattern_set.mjs`, `examples/test_examples.py` |
| **Executed (2026-08-24):** `pytest examples/test_examples.py -q` → 21 passed | `examples/test_examples.py` |
