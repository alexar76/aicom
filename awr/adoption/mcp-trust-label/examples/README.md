# MTL/1 example documents

> **Drafts on disk.** Nothing here has been sent, published, submitted or registered anywhere.
> These files exist so a reviewer can check the profile against real bytes.

> ## ⚠ THE SIGNING KEY FOR EVERYTHING IN THIS DIRECTORY IS PUBLIC
>
> Every `.awr.json` file here is signed from the seed **`bytes(range(32))`**, published in
> `generate.py`. The private key is therefore public, and **anyone can mint valid AWR/2
> documents under this issuer's DID**
> `did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd`.
>
> Consequences, all of which matter:
>
> - A document signed by that key is **evidence of nothing**: not of adoption, not that any
>   scan was performed, not anything about any server. A valid signature here proves only
>   that someone used a key everybody has.
> - It must **never** be displayed as a trust signal, allow-listed by a registry, or counted
>   as an adopter. It is declared in
>   [`awr/adoption/metrics/own-keys.txt`](../../metrics/own-keys.txt) for exactly that
>   reason — before that entry existed, the adoption metric reported **1 adopter, and the
>   adopter was this directory**. `test_examples.py` and the metric's own suite both fail if
>   the declaration goes missing.
> - Every label says all of this **inside its own signature**: see `mcpTrustLabel.demonstration`
>   below.

Every `.awr.json` file here was **signed by the AWR/2 reference implementation** at
`awr/reference/python`. No signature byte was written by hand, and every document verifies —
re-run on 2026-07-31 at 19:05 UTC — after the `demonstration` marker below was added — with
`python -m awr verify` on each file, reading `valid`, `profile`, `len(reasons)` and
`len(warnings)` out of the JSON result:

```
exit 0  pass-01-pattern-scan.awr.json              valid=True profile=L0 reasons=0 warnings=0
exit 0  inconclusive-01-pattern-scan.awr.json      valid=True profile=L0 reasons=0 warnings=0
exit 0  pass-02-tool-set-observation.awr.json      valid=True profile=L0 reasons=0 warnings=0
exit 0  pass-03-tool-set-continuity.awr.json       valid=True profile=L0 reasons=0 warnings=0
```

That is the whole of what is genuine here: the signatures, and the digest arithmetic over the
bytes in these files. **No MCP server was ever contacted.** The tool arrays are literals in
`generate.py` for two invented servers, `observedAt` is a fixed constant, and the pattern matches
recorded in `inconclusive-01` are Python literals that `generate.py` does not compute — see
`PROFILE.md` Appendix A, which lists both gaps. These files demonstrate the document format, not
the §7.2 procedure, and there is no MTL issuer in this repository.

Two of those gaps are now *checked* rather than asserted, by `test_examples.py`:

- the hardcoded `patternMatches` are compared against a live run of
  `argus/dist/warden/static-scan.js` over exactly these tool definitions (three matches, score
  `0.40`); the test skips, visibly, if node or that build is absent;
- `pattern-set-argus-warden-static-scan.json` is a **hand transcription** of
  `argus/src/warden/static-scan.ts`, and a digest over a hand copy binds to the copy rather than
  to the code that ran — so the test re-extracts all 22 patterns and both heuristics from the
  TypeScript and requires them to match, source and flags included.

## The `demonstration` marker

Every label carries this inside `credentialSubject.mcpTrustLabel`, and therefore inside the
signature:

```json
"demonstration": {
  "isDemonstration": true,
  "issuerPrivateKeyIsPublic": true,
  "issuerKeySeed": "bytes(range(32)), published in awr/adoption/mcp-trust-label/examples/generate.py",
  "warning": "DEMONSTRATION DOCUMENT. The private key of this issuer is published, so anyone can mint documents under this DID and none of them means anything. …"
}
```

**This is spec- and profile-conformant, and it costs the documents nothing.** `PROFILE.md` §6.3
says in as many words that unknown `mcpTrustLabel` members MAY be present and that a registry
MUST ignore them semantically and MUST NOT strip them; `SPEC.md` §3.1 and §4.2 require a verifier
to preserve unknown properties and canonicalize them. So the marker is signed, travels with the
document, survives any conformant round-trip, and all four labels still verify at
`valid=True profile=L0 reasons=0 warnings=0` — the table above is the run *with* the marker
present. Because it is inside the signature, it cannot be quietly deleted: flipping
`isDemonstration` to `false` invalidates the document, which `test_examples.py` asserts.

The `issuer.name` on every label reads `mtl-demo-scanner (DEMONSTRATION KEY — SEED PUBLISHED, NOT
AN ADOPTER)`. `SPEC.md` §3.1 gives `issuer.name` no trust weight and `PROFILE.md` §9.1 forbids
displaying it as identity — it is worded that way for the human reading raw JSON, and for any
report that lists issuer names, not as a security control.

The two `*-subject-descriptor.json` files deliberately carry **no** inline marker. They are
digested, and `sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s=` is quoted in `PROFILE.md`
§4.5, in this file and in `registry-integration.md`; adding a field would change the digest and
make three documents wrong at once. They are descriptors of invented servers, not signed claims,
and the labels that reference them say what they are.

## Files

| File | What it is |
|---|---|
| `pass-01-subject-descriptor.json` | MCP Server Descriptor (`PROFILE.md` §4) for a clean two-tool server. Subject digest `sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s=` |
| `pass-01-pattern-scan.awr.json` | **pass** label — `tool-def-pattern-scan`, zero patterns matched |
| `pass-02-tool-set-observation.awr.json` | **pass** label — `tool-set-observation`, the first of two observations |
| `pass-03-tool-set-continuity.awr.json` | **pass** label — `tool-set-continuity`, same subject digest as the prior label, so definitions unchanged |
| `inconclusive-01-subject-descriptor.json` | Descriptor for a server whose *benign* definitions trip the pattern set |
| `inconclusive-01-pattern-scan.awr.json` | **inconclusive** label — three matches, all on benign text |
| `pattern-set-argus-warden-static-scan.json` | The pattern table, digested so labels are comparable (`PROFILE.md` §7.3). A hand transcription of `argus/src/warden/static-scan.ts`, kept honest by a drift test |
| `generate.py` | Regenerates everything above, deterministically, and re-verifies it. **It is an AWR/2 issuer whose seed is published** |
| `test_examples.py` | Fails unless the demonstration marker is present and costs no warning, the generator's DID is declared in `own-keys.txt`, the quoted digests are stable, and the pattern table and the hardcoded findings still match ARGUS. 18 tests, all passing as of 2026-07-31 |

## Why the `inconclusive` example matters

`inconclusive-01` is a two-tool server with a `create_issue` tool whose description says
"Requires a personal access token with repo scope" and whose schema carries an `api_key` property,
and a `list_files` tool whose description contains the words "instead of". Executing the shipping
ARGUS static-scan gate (`argus/dist/warden/static-scan.js`) over exactly these definitions —
re-run 2026-07-31 18:29 UTC — produces:

| Match | Severity | Where |
|---|---|---|
| `TOOL_DEF_SECRET_REQUEST` | `high` | `create_issue` description |
| `TOOL_DEF_SECRET_REQUEST` | `high` | `create_issue` input schema |
| `TOOL_DEF_INJECTION` | `low` | `list_files` description |

Three matches, gate score **0.40**, which at that implementation's default
`blockAtSeverity: "high"` refuses the connection outright. Isolated in the same run: the `api_key`
property **alone** produces one `high` match and a score of 0.4, and "instead of" alone produces
one `low` match and a score of 0.9. The clean two-tool server in `pass-01` produces 0 matches and
a score of 1.

Neither tool is malicious. This is why `PROFILE.md` §7.3 forbids `fail` for the pattern-scan
method and requires `inconclusive` instead, and why §9.2 requires registries to render
`inconclusive` as neutral rather than as failure.

## Regenerate

From the repository root:

```bash
PYTHONPATH=awr/reference/python:awr/adoption/mcp-trust-label/tools \
  .venv/bin/python awr/adoption/mcp-trust-label/examples/generate.py
```

Output is byte-identical on every run: the signing key comes from a fixed seed and all four
timestamps are fixed. The run opens with a banner saying the private key is public, prints the
derived DID and asserts it is the documented one, and then checks that
`awr/adoption/metrics/own-keys.txt` declares it — printing a loud complaint if it does not,
because an undeclared issuer of ours is counted as an adopter:

```
==============================================================================
DEMONSTRATION ISSUER — the private key below is PUBLIC (seed bytes(range(32))).
Anyone can mint documents under this DID; none of them is evidence of anything.
==============================================================================
issuer DID: did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd
own-keys: declared in awr/adoption/metrics/own-keys.txt -> the adoption metric counts this key as zero
```

Also run the suite, which is where the checks live rather than in prose:

```bash
PYTHONPATH=awr/reference/python:awr/adoption/mcp-trust-label/tools \
  python3 -m pytest awr/adoption/mcp-trust-label/examples/test_examples.py -q
# 18 passed
```

## Verify

```bash
PYTHONPATH=awr/reference/python python -m awr verify \
  awr/adoption/mcp-trust-label/examples/pass-01-pattern-scan.awr.json

# and the registry-side subject-digest recomputation (PROFILE.md §4.6):
PYTHONPATH=awr/reference/python python -m awr digest \
  awr/adoption/mcp-trust-label/examples/pass-01-subject-descriptor.json
# sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s=
```

Both re-run 2026-07-31 19:07 UTC with the output shown, against the current label bytes (i.e.
with the `demonstration` marker present). Note that the second command is only the
*arithmetic* half of §4.6: it digests a descriptor that ships in this directory. A real consumer
must build that descriptor from **its own** retrieval of the server's tool set, which for the
`transport: "stdio"` servers in these examples would mean installing and executing the package.
The convenience of this example is exactly the part §4.6 does not let a consumer keep.

## These are not real servers

`com.example/weather`, `com.example/tracker`, the `urn:awr:mtl:1:registry:example` registry
identifier and the `npm:@example/...` package names are all invented. No real MCP server is
described, labelled, endorsed or criticised anywhere in this directory.

The demonstration signing key is derived from a seed published in `generate.py`
(`bytes(range(32))`). Its DID is
`did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd`. It confers no authority and
**MUST NOT** be used to issue a real label.

The banner at the top of this file states the consequences in full. The two that bear repeating:
the private key is public by construction, so a document signed by it establishes nothing about
who issued it and **MUST NOT** appear on any consumer's issuer allow-list (`PROFILE.md` §13.2);
and it is *our* key, so it stays in
[`awr/adoption/metrics/own-keys.txt`](../../metrics/own-keys.txt) permanently — an adoption metric
that counts it reports our own fixture as a foreign adopter, in the flattering direction, which is
the direction nobody checks.
