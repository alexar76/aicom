# The AWR adoption metric

> **This directory is a draft on disk.** Nothing here sends, posts, publishes or uploads
> anything. `adoption_metric.py` reads the filesystem and prints; verification itself is
> offline by construction (SPEC.md §13.5 forbids a verifier from dereferencing anything).
> Any number produced here is for the maintainers to look at and decide what to do with.

## The metric

**How many AWR documents exist that were issued by a key this project does not control?**
Reported as a count of **distinct foreign issuer DIDs**: the number of distinct `did:key`
identifiers that appear as `issuer.id` in valid AWR/2 documents and are *not* listed in
our own-keys file. A document counts once per document `id`; an issuer counts once no
matter how many documents it issued; a document that fails verification never counts;
whether a document reaches profile L0, L1 or L2 changes nothing about whether it counts.
That is the whole definition, it is one number, and it is the only number on the first
line of both outputs.

The definition string lives in `adoption_metric.py` as `METRIC_DEFINITION`, its SHA-256
is reported in every run as `headline.definitionDigestSHA256`, and
`test_adoption_metric.py` pins that digest. Changing what the metric means therefore
requires editing a test, which shows up in a diff and has to be argued for.

## Why distinct foreign *issuers*, and not documents

Because document count measures our own plumbing and issuer count measures other people's
decisions.

One enthusiastic adopter who wires AWR into a hot loop and emits a million receipts is
**one adopter**. Ten thousand receipts from our own hub is **zero adopters**. A single
receipt from one stranger's key is worth more evidence about whether this format is
useful than any volume number we can generate ourselves, because it is the only kind of
number we cannot produce by turning up our own traffic.

Issuing an AWR document requires generating an Ed25519 keypair, reading enough of the
spec to build a valid envelope, and signing over a canonical form — profile L0 needs no
payment, no verdict, no network and no third party (SPEC.md §10.1). So a foreign issuer
DID is a signed, self-authenticating, offline-checkable statement that somebody outside
this project did that work. That is what we are trying to measure. Volume is not.

`adoption_metric.py` still reports document counts, per-type counts and per-profile
counts, because they are useful for diagnosis — but they live under a `context` key whose
first field says `NOT THE METRIC`, and the human summary prints them under a heading that
says the same thing. The shape of the output is deliberately hostile to anyone who wants
to quote a bigger number later.

## What does NOT count

Not adoption, by construction:

- **Documents issued by our own hub.** Its DID belongs in the own-keys file.
- **Documents issued by our own satellites** — Metis, GAIA, the oracle family, ARGUS,
  DIOSCURI, SKOPOS, the lottery, anything in this monorepo that grows an emitter. Their
  DIDs belong in the own-keys file.
- **Documents issued by our own courses**, demos, quickstarts and example scripts,
  including keys generated on the fly for a tutorial.
- **Documents issued by CI.** A conformance run that signs a fresh receipt on every
  build would otherwise manufacture unbounded "adoption". CI keys belong in the own-keys
  file; ephemeral CI keys are worse than static ones, because a new DID per build looks
  exactly like a new adopter per build.
- **Our own test vectors and fixtures**, including `awr/vectors/` and anything under a
  `tests/` tree. Point the tool at a corpus of collected documents, not at the repo.
- **Documents that fail verification.** They are counted and listed in the `invalid`
  section — never silently dropped — but they are not adoption. An invalid document from
  an unknown key is a lead, not a number: someone may be trying and failing, which is
  worth chasing, and the reason codes tell you what broke.
- **Valid AWR/1 documents.** They are a different format (SPEC.md §12 permits verifying
  them and forbids issuing them). They are reported separately as
  `invalid.validAwr1NotCountedAsAwr2`; `--include-legacy` counts them if you have a
  reason, and the report records that you did.
- **A repeat of a document `id` we have already seen.** Counted once. The `id` is inside
  the signature, so it is a binding statement by the issuer (SPEC.md §3.1), which makes
  it the right dedup key. If the same `id` shows up over different bytes, the collision
  is reported in `idCollisions` and the document is attributed to its first occurrence.

## Exclude our own documents by DID — never by hostname, never by trust

**Warning.** The only correct way to exclude our own documents is to match
`issuer.id` against a declared list of DIDs we control. Every other filter is either
forgeable or wrong:

- **Not by hostname or domain.** An AWR document contains no hostname. It was not
  fetched from anywhere — it is a self-contained file that may arrive by any route, and a
  verifier must not dereference anything (§13.5). The URL we happened to download it from
  is not part of the signed bytes, so filtering on it filters on unsigned metadata that
  anyone can change, and it fails in both directions: an adopter who mirrors a document
  on our domain would be excluded, and our own document served from anywhere else would
  be counted as adoption.
- **Not by `issuer.name`.** §3.1 is explicit that `name` carries no trust weight. It is
  an unauthenticated label chosen by the issuer, inside the signature but meaningless:
  anybody can sign `"name": "example-hub"`. The report shows `names` for foreign issuers
  purely so a human can recognise who showed up; it is never used to classify.
- **Not by trust, reputation, allow-list membership, or "we know these people".** Trust
  is a different question from provenance. A key we do not hold is foreign even if we
  like its owner; a key we do hold is ours even if we forgot we had it.
- **Not by profile, verdict, or score.** L0 is the adoption floor and is deliberately
  free (§10.1). Requiring L1 would count "adopters who also got someone else to verify
  them", which is a different and much smaller number, and one we could inflate by
  verifying strangers' receipts ourselves. The per-profile counts include a `none` bucket,
  which is not a failure: SPEC §10.4 gives a document that is not a `WorkReceipt` — a
  `VerificationVerdict`, a `BlameAttestation` — a null profile, because L1/L2 are levels of
  assurance about a unit of work. Those documents are valid and they count.

The consequence is that the metric is only as honest as `own-keys.txt`, and a DID missing
from that file inflates the number in the flattering direction. `own-keys.example.txt`
explains the discipline; short version: **the DID of any component of ours that starts
issuing AWR documents goes into the own-keys file in the same change.**

### What this repository issues today

Nothing in this repository issues AWR/2 documents **in production**. Two things in it do
issue, both from seeds published in their own source:

- **The MTL example generator**, `awr/adoption/mcp-trust-label/examples/generate.py`, signs
  four MTL/1 labels on every run from the seed `bytes(range(32))`. Its DID is
  `did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd`. That DID is in `own-keys.txt`
  and **must stay there forever**. Because the seed is public, anyone can mint documents
  under it, which is also why no document signed by it is evidence of anything.
- **The adoption demo corpus**, `demo_corpus.py`, mints six synthetic issuers from published
  seeds so the transcript below can be regenerated. All six are in `own-keys.txt` too.

This was a real defect, not a hypothetical: before those entries existed, this tool
reported **1 adopter over our own example directory, and the adopter was us**. The
regression is now pinned by `test_adoption_metric.py`
(`test_a_document_from_the_example_generator_is_not_a_foreign_adopter`, and its twin that
requires the count to go back to 1 when the entry is removed), so the file's integrity is
enforced by a test rather than by discipline. The correct value of the metric today, over
any corpus in this repository, is **zero**.

Also declared, for the same reason: the test-vector keys in `awr/vectors/generate.py` (the
RFC 8032 §7.1 seeds) and the reference suite's `deterministic_key(tag)` fixtures. Fixtures
are not adoption, and a fixture that strays into a collected corpus must not become one.

## Usage

```sh
# default: human summary on stderr, JSON on stdout
python3 adoption_metric.py /path/to/corpus

# several inputs; files and directories both work
python3 adoption_metric.py corpus/ extra/receipt.awr.json batch.jsonl

# explicit own-keys file; deterministic time for time-dependent warnings
python3 adoption_metric.py corpus/ --own-keys own-keys.txt --now 2026-07-31T12:00:00Z

# JSON only, to a file, refusing to run without real signature verification
python3 adoption_metric.py corpus/ --format json --json-out report.json --require-reference

# mint the synthetic corpus the transcript below is computed from, and stop
python3 adoption_metric.py --demo-corpus /tmp/awr-demo

# show what a degraded run counts (never for a quoted number: the report marks itself)
python3 adoption_metric.py corpus/ --no-verify-signatures
```

`--own-keys` defaults to `$AWR_OWN_KEYS`, else the committed `own-keys.txt` in this
directory. That file is public, contains only DIDs, and is the artefact any quoted number
has to be read against.

Inputs may be a single AWR document, a §9 bundle (`{"awrBundle": "2.0", "documents":
[…]}`), a JSON array of documents, or one document per line in a `.jsonl`/`.ndjson` file.
Directories are walked for `*.json`, `*.jsonl` and `*.ndjson`; an explicitly named file
is always read whatever its extension.

Exit codes: `0` a report was produced, `1` `--fail-under N` was given and the metric is
below `N`, `2` usage or I/O error. Invalid documents do not change the exit code — they
are data.

## What a run looks like — and how to regenerate it yourself

The corpus is **shipped**, so nothing below has to be taken on trust. `demo_corpus.py`
mints it deterministically from six seeds published in that file, together with the
own-keys file the run uses. Three commands, and you have the transcript that follows:

```sh
python3 awr/adoption/metrics/adoption_metric.py --demo-corpus /tmp/awr-demo
cd /tmp/awr-demo
python3 <repo>/awr/adoption/metrics/adoption_metric.py corpus \
    --own-keys own-keys.txt --format human \
    --now 2026-07-31T12:00:00Z --require-reference
```

**None of these DIDs is an adopter.** Every one of the six demo keys comes from a published
seed, so anyone can mint documents under them; the demo's own-keys file declares two of the
six *on purpose*, so the arithmetic is visible. (All six are declared in this directory's
real `own-keys.txt`, which is why running the tool against the demo corpus with the default
own-keys file reports 0. That is the correct answer for a synthetic corpus.) The point of
the run is the arithmetic, not the names.

Output of the command above, pasted verbatim:

```
AWR adoption metric — awr.adoption.distinct-foreign-issuers
===========================================================

THE NUMBER: 3 distinct foreign issuer DIDs

  definition: The number of distinct did:key issuer identifiers that appear in valid AWR/2 documents and are not listed in this project's own-keys file. A document counts once per document id; an issuer counts once regardless of how many documents it issued. Documents that fail verification never count.

Instrument
  verifier           awr reference implementation 2.0.0
  own-keys file      own-keys.txt
  own DIDs declared  2
  timestamp field    validFrom
  network access     none: no request is made by this tool or by verification (§13.5)

Corpus
  inputs                   corpus
  files scanned            8
  documents read           48
  duplicate ids collapsed  1
  unreadable inputs        1

Issuers
  distinct issuers        5
  ours (excluded by DID)  2
  FOREIGN (the metric)    3

Foreign issuers
  did:key:z6MkevyW84ncRNA51dkac93YJCMqEEydBcM7T8ueJLSgxrsu (swarm-runner)
      documents   41
      first seen  2026-07-01T12:00:00Z
      last seen   2026-07-28T12:00:00Z
      by type     WorkReceipt=40 VerificationVerdict=1
      by profile  L0=40 none=1
      seen in     corpus/duplicate-of-swarm-0001.awr.json, corpus/swarm-runner.jsonl
  did:key:z6MkgJkQq87vmETBqKTBJNsE1MNTiqYS29rwMj1YPZT7gQ8f (third-party-juror)
      documents   1
      first seen  2026-07-21T09:00:00Z
      last seen   2026-07-21T09:00:00Z
      by type     VerificationVerdict=1
      by profile  none=1
      seen in     corpus/third-party-juror.awr.json
  did:key:z6Mkoc3dRo3DUKv1uiu13MfYgcYTeyob1Ajhc6CWpP55KodC (careful-labs)
      documents   1
      first seen  2026-07-20T09:00:00Z
      last seen   2026-07-20T09:00:00Z
      by type     WorkReceipt=1
      by profile  L2=1
      seen in     corpus/careful-labs-receipt.awr.json

Our own issuers (excluded)
  did:key:z6MkkRDecSi6Zwb97YPJVUBsJEFTNLyDGqBjkPj4x5hBGjxu  2 documents
  did:key:z6MkoBPxsraEkYCMSrPoJ7ogXJAMYMbZoTmMExjbsrUjFjN3  1 documents

Context — NOT THE METRIC
  NOT THE METRIC. Document counts are volume, not adoption: one enthusiastic adopter emitting a million receipts is one adopter.
  valid documents         46
  foreign documents       43
  our documents           3
  type (foreign)          WorkReceipt=41 VerificationVerdict=2
  profile (foreign)       L0=40 none=2 L2=1
  type (all valid)        WorkReceipt=43 VerificationVerdict=3
  profile (all valid)     L0=41 none=3 L1=1 L2=1
  awrVersion (all valid)  2.0.0=46

Excluded from adoption (1)
  failed verification     1
  valid AWR/1, not AWR/2  0
  by reason code          AWR-PROOF-006=1
  by issuer class         foreign=1 own=0 unattributable=0
    corpus/struggling-001.awr.json  AWR-PROOF-006  did:key:z6MkmhdsteM2yqZ8LBDwjeTUqsvgd6Vzdb27GzJr3GVrHsZf

Unreadable inputs (1)
    corpus/junk.json  not strictly parseable under spec §4: AWR-CANON-005: not well-formed JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```

Four things to read off that output, because they are the whole design. Each one is a
command you can run against the same corpus, and each one is asserted by a test in
`test_adoption_metric.py`, so the transcript cannot drift away from the tool:

- **43 foreign documents, 3 foreign issuers.** One key emitted 41 of them (40 receipts and
  one verdict, and a byte-identical duplicate that collapsed). The headline is 3.
- **A fourth foreign key issued only a document that fails verification** and is therefore
  not an adopter — but it is named, with `AWR-PROOF-006`, so it can be chased. Profile is
  irrelevant to counting in the other direction too: `careful-labs` reaches L2 and still
  counts exactly once, like the L0 issuer next to it — and `third-party-juror`, whose only
  document is a verdict and therefore has profile `none` (§10.4), counts exactly once as well.
- **The same corpus with an empty own-keys file yields 5, not 3.** Same bytes, same
  verification, a 67% larger number, purely from two undeclared keys of our own:

  ```sh
  python3 <repo>/awr/adoption/metrics/adoption_metric.py corpus --own-keys /dev/null \
      --format human --now 2026-07-31T12:00:00Z --require-reference
  # THE NUMBER: 5 distinct foreign issuer DIDs
  ```

  That is the failure mode, and it is why the own-keys file is the artefact to police.
- **The structural fallback yields 4, not 3**, because it accepts the document whose
  signature is broken. A degraded run refuses to look trustworthy — it prints a banner and
  sets `headline.signaturesVerified: false`:

  ```sh
  python3 <repo>/awr/adoption/metrics/adoption_metric.py corpus --own-keys own-keys.txt \
      --format human --now 2026-07-31T12:00:00Z --no-verify-signatures
  # THE NUMBER: 4 distinct foreign issuer DIDs
  # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  # ! NO SIGNATURES WERE VERIFIED — the number above is an UPPER BOUND,
  # ! not the metric. Rerun with the AWR reference implementation
  # ! importable and without --no-verify-signatures.
  # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ```

## How it verifies

`adoption_metric.py` imports the AWR reference implementation from
`awr/reference/python` (or an installed `awr`) and calls `verify_document` on every
candidate, passing all loaded documents as the supporting set so that L1 and L2 can be
evaluated (§10). Dependencies are the standard library plus whatever the reference
implementation needs — `cryptography`, for Ed25519 — and nothing else.

If the reference implementation cannot be imported, the tool falls back to a structural
check that validates envelope shape and **verifies no signatures at all**. In that mode
the headline number is an upper bound, not the metric: the JSON sets
`headline.signaturesVerified: false`, the human summary prints a banner, and a warning
says not to quote it. Use `--require-reference` in CI so a degraded run fails instead of
producing a comfortable number.

`--no-verify-signatures` asks for that fallback deliberately, on a machine where the
reference implementation imports fine. It exists so the degraded mode is demonstrable
rather than described (it is how the "4, not 3" line above was produced), it cannot make a
run look trustworthy — the same banner, warning and `signaturesVerified: false` — and it is
refused outright when combined with `--require-reference`.

Two other deliberate conservatisms, both chosen so that the instrument can only
under-count:

- A file whose bytes do not survive the strict §4 parse (duplicate property name,
  non-integer JSON number, malformed JSON) yields **no** documents and is reported under
  `corpus.readErrors`. For a bundle, one bad document rejects the whole file. Coarse, but
  it never manufactures an adopter.
- A document that somehow verifies without an `issuer.id` is attributed to no issuer at
  all rather than to a foreign one, and is surfaced as
  `issuers.unattributableValidDocuments`. This is unreachable with the reference
  implementation (§3.1 requires `issuer.id`; a document without one gets `AWR-DOC-010`).

Timestamps: `firstSeen` and `lastSeen` per foreign issuer come from the document's
`validFrom`, which is present in all three document types and is inside the signature.
File modification times are not used — they are unsigned, they say when we copied a file,
and they would let the timeline be rewritten by a `cp`.

## Files

| File | What it is |
|---|---|
| `adoption_metric.py` | the instrument |
| `own-keys.txt` | **committed, public, one line per DID** — the live list, read by default. A metric quoted without the own-keys file it was computed against is unauditable, which is the whole reason this file is in the repository and not on somebody's laptop |
| `own-keys.example.txt` | the documented format and the discipline, with placeholder entries; points at `own-keys.txt` for the real thing |
| `demo_corpus.py` | mints the synthetic corpus the transcript above is computed from, plus its own-keys file. Deterministic, published seeds, contains no adoption |
| `test_adoption_metric.py` | proves the counter on synthetic documents signed with real keys — including that our own example generator counts as zero, and as one if its DID is removed from `own-keys.txt` |
| `README.md` | this file |

## Tests

```sh
python3 -m pytest awr/adoption/metrics/test_adoption_metric.py -q
```

The tests generate real Ed25519 keys and issue genuinely signed documents with the
reference implementation, then assert the four properties that make the number mean what
it says: documents from our own keys do not count, documents from foreign keys do,
invalid documents are excluded from adoption and reported separately, and a duplicate
document `id` counts once. They also pin the metric definition digest, so the metric
cannot be redefined quietly.

Three further groups exist because of the audit that found this instrument reporting
itself as an adopter:

- **The committed own-keys file is checked, not assumed.** It must exist, parse with zero
  problems, and declare the MTL example generator's DID — which the test *derives* by
  running `SigningKey.from_seed(bytes(range(32)))` rather than copying the string.
- **The regression is pinned in both directions.** A label signed by the example
  generator's published key counts as **0** with the committed file, and as **1** with that
  one entry removed. A test that passed either way would guard nothing.
- **The transcript above is asserted.** Every number in it — 3, 8 files, 48 documents, 1
  duplicate, 1 unreadable, 5 issuers, 2 ours, 41 documents from one key, `AWR-PROOF-006` —
  is a test assertion over the shipped demo corpus, as are the 5 (empty own-keys) and 4
  (structural fallback) comparison runs.

The MTL examples have their own suite, which proves that the demonstration marker inside
those labels costs them no reason and no warning, and that the transcribed ARGUS pattern
table has not drifted from the code it was transcribed from:

```sh
PYTHONPATH=awr/reference/python:awr/adoption/mcp-trust-label/tools \
  python3 -m pytest awr/adoption/mcp-trust-label/examples/test_examples.py -q
```
