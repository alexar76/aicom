# Frozen two-sided comparison inputs — 2026-11-07

All acquisition, normalization and data checks ran in gVisor on Attested. Frozen inputs are mirrored on Blip. Definitions are inert data; no original third-party package or benchmark implementation is executed.

## Runtime inputs

../inputs/cases.json is the frozen 3,177-case lazy catalog. SHA256: e29baa05fbdbf46e34631ff2c75f0b4f535f0188054dd4499699bd189a3dc757.

../histor/inputs/cases.json is the separate frozen 14,933-package lazy catalog. SHA256: 78d4dab7125318b80cc35302e7cf1cfc1a49fa6f310957ed7b8fddfb538375b6.

Both use warden.shared-lazy-inputs/v1, cases[], key, set, label, optional split, supplied opaque wireId, toolCount, and toolsFile relative to their own catalog directory. Each tools file contains {name: wireId, tools: [...]}. toolsFileSha256 hashes exact UTF-8 file bytes. toolsSha256 hashes Python 3.13 JSON serialization with sorted object keys, compact separators, Unicode unescaped, array order retained, and non-finite numbers refused. It is not asserted to be JCS; portable consumers should verify exact file bytes.

Wire IDs are c plus the first 32 hexadecimal characters of SHA256 over UTF-8 "warden shared inputs 2026-11-07|" followed by the case key. They are identical across scanner/version/host comparisons.

## Counts and overlap

The 3,177 views contain own 35 (23 attack, 12 benign), independent 12 (10 attack, 1 benign, 1 ambiguous), public 986, carry 41, MCPTox native 485, clean 45, decorated 225, and full scenarios 1,348. Public main/carryover have 28 exact name+definition overlaps, leaving 999 unique name+definition snapshots.

MCPTox is pinned to author repository commit f85189f9ad12504c197c7f920ab818a40657b1fa at https://github.com/zhiqiangwang4/MCPTox-Benchmark . The 485 native definitions and 1,348 complete prompt-surface scenarios are different overlapping views; neither denominator replaces the other. All 1,348 scenario rows were projected, zero discarded; 10 exact raw scenario duplicates are retained. Clean 45 prompts expose 362 normalized tools, not the paper's 353; deduplication by name+description/full definition does not resolve that discrepancy. Raw definitions, schema text and attack payloads are excluded from the publication inventory because the source repository specifies no license.

## Historical packages

The frozen 2026-10-16 index contains 14,933 package versions: 12,023 npm and 2,910 PyPI; every version is recorded. There are 14,449 distinct referenced toolsets. Recovery covers all 14,933 rows and 272,657 definitions, with zero discarded rows or tool-count mismatches. Exact MTL digest rederivation passed all 14,449 distinct toolsets; every case-file hash matched.

14,930 rows were recovered from https://histor.modelmarket.dev/datasets/2026-10-20/toolsets.jsonl.gz . Published manifest: https://histor.modelmarket.dev/datasets/2026-10-20/manifest.json . Compressed archive SHA256: 9d5f8493910741c084a4e8315375d6bba918d5a0fad8d7bbc02f1e216773e2a2. Manifest SHA256: a7bfc9e09ab9782157ad6c7a4bb136477609746a7e7e6f9c6695ea2012e926fc. Manifest and embedded tree-head Ed25519 signatures verified against HISTOR's pinned did:key.

Three archive-absent digests were recovered via public immutable https://histor.modelmarket.dev/api/v1/toolsets/{URL-encoded digest} URLs. Exact bytes, digests and versions are retained; MTL hashes match. These API responses state no separate license, so their publication inventory is metadata only; they are not silently covered by the archive license.

Archive license: CC-BY-4.0. Attribution: Aleksandr Artamokhov / HISTOR, HISTOR: MCP tool definitions and how they change, public dataset snapshot 2026-10-20. The archive covers MTL base fields; no current annotations/title/extras are merged into historical inputs.

## Publication-safe downloads

public-inventory.json, public-inventory.csv and .gz copies contain 18,110 factual metadata rows: names, recorded versions, labels, tool counts, digests and provenance. They contain no descriptions, schemas, argument text, attack payloads or benchmark Python source. Hashes and set counts are in public-inventory-manifest.json. Original private test inputs stay separate.

Public corpus and package rows are unlabelled. Blocking rate is not false-positive rate. Prior own/independent regressions and post-hoc candidate19 repair are not fresh holdouts. Execution/CLI parity success does not imply unchanged detection recall.

Detailed source and isolation evidence is in manifest.json, ../histor/metadata/historical-recovery-manifest.json, ../histor/metadata/integrity-audit.json and preserved preparation logs. The two catalogs remain separate immutable evaluation phases.
