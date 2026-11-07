---
license: cc-by-4.0
pretty_name: HISTOR — MCP tool definitions and how they change
language:
- en
task_categories:
- text-classification
task_ids:
- multi-label-classification
annotations_creators:
- machine-generated
source_datasets:
- original
multilinguality:
- monolingual
tags:
- mcp
- model-context-protocol
- ai-security
- prompt-injection
- tool-poisoning
- transparency-log
- supply-chain-security
- ai-agents
size_categories:
- 100K<n<1M
configs:
- config_name: servers
  data_files: servers.jsonl.gz
- config_name: toolsets
  data_files: toolsets.jsonl.gz
- config_name: changes
  data_files: changes.jsonl.gz
- config_name: scans
  data_files: scans.jsonl.gz
- config_name: classifications
  data_files: classifications.jsonl.gz
- config_name: tool_extras
  data_files: tool_extras.jsonl.gz
- config_name: extras_changes
  data_files: extras_changes.jsonl.gz
- config_name: package_observations
  data_files: package_observations.jsonl.gz
---

# HISTOR snapshot 2026-11-02: what MCP servers advertise, and when it changes

HISTOR reads the tool list (`tools/list`) of every remote MCP server in the official MCP registry
on a polling schedule, and of npm/PyPI MCP packages run in a sandbox once per published version (new versions
first, a few hundred a day). It records the exact tool definitions,
pins them by digest, and writes a signed label to a public RFC 9162 Merkle log whenever a tool set
first appears, stays the same, or changes. This snapshot is that record as files.

- **90,863** listed servers (37,593 remote endpoints, 53,270 packages), plus 6,060 delisted
- **47,016** with a recorded tool set; **15,082** changed at least once
- **53,159** recorded changes, 2026-09-24 to 2026-11-02
- **90,641** distinct tool sets (current ones and every one a change replaced)
- **982** servers with a block-tier WARDEN pattern match, **18,480** advise-only

Live view and per-server pages: https://histor.modelmarket.dev · code: https://github.com/alexar76/histor

## Files

| File | Rows | Size | SHA-256 |
| --- | ---: | ---: | --- |
| `servers.jsonl.gz` | 96,923 | 21 MB | `fc9759a4166f7c12…` |
| `toolsets.jsonl.gz` | 90,641 | 1,054 MB | `2a3e516b1ab5487e…` |
| `changes.jsonl.gz` | 53,159 | 57 MB | `9c90605fe9fa935d…` |
| `scans.jsonl.gz` | 11,069 | 754 kB | `304f7797d9dc625b…` |
| `classifications.jsonl.gz` | 4,195 | 233 kB | `b7ddf9d948e4691f…` |
| `tool_extras.jsonl.gz` | 95,178 | 41 MB | `37ee4fcec4233c8a…` |
| `extras_changes.jsonl.gz` | 74,812 | 8 MB | `66fa0a1f1334e9dd…` |
| `package_observations.jsonl.gz` | 171,834 | 15 MB | `f2d5c17b0eecabcc…` |
| `pattern-set.json` | — | 19 kB | `cc281951922f3654…` |
| `record-set.json` | — | 2 kB | `31c46efdcbcbae5a…` |

`manifest.json` holds the full hashes and the counts, signed by the log's key `did:key:z6Mkw1CVxsPj9utYp7VXWEbuuGM9Ev47itwKu1UfKd5ByxR9`
(type `histor.dataset/v1`, Ed25519 over RFC 8785 JSON). It also carries the signed tree head the
export started under (tree size 1,490,816), so any label id below can be checked
against the live log with `GET https://histor.modelmarket.dev/api/v1/labels/<id>/proof`.

## Fields

Fields whose shape varies between servers are JSON text (`*Json`), so every file loads as a flat
table. Digests are SRI strings (`sha256-…`) over the RFC 8785 form of the value.

- **servers** — `id` (stable per name+endpoint), `name`, `title`, `description`, `endpoint`
  (`https://…` or `npm:`/`pypi:` for packages), `transport`, `registry`, `version`, `repository`,
  `firstListed`/`lastListed`, `delisted`, `skipReason` (why it was not dialled), `lastStatus` and
  `lastDetail` (the last attempt's outcome), `lastObserved`, `toolCount`, `toolSetDigest` (join to
  toolsets), `firstPinned`, `unchangedSince`, `attempts`, `observations`, `changes`,
  `blockMatches`/`adviseMatches`/`recordMatches`, `classifierFlags`, `chainLabel` (latest label id), `page`.
- **toolsets** — `digest`, `toolsJson`: per tool the four members the digest covers, as served
  (`name`, `description`, `inputSchema`, and `outputSchema` when sent).
- **tool_extras** — `digest`, `extrasJson`: `{"tools": {name: {member: value}}}`, every member a tool
  carried beyond those four (`annotations`, `_meta`, `title`, `icons`, `execution`, vendor fields),
  only for tools that carried one. Join from `servers.toolExtrasDigest`: `""` there means observed with
  none, null not observed since HISTOR keeps them (2026-10-22). Not part of the MTL/1 digest or of any
  label; its digest is SHA-256 over sorted-key JSON, not RFC 8785 (prices in `_meta` are fractions).
- **extras_changes** — `serverId`, `observedAt`, `fromExtrasDigest` → `toExtrasDigest`, `summaryJson`:
  per tool, every annotation that moved (`[before, after]`) and every other member added, removed or
  changed; `escalations` names tools that stopped saying `readOnlyHint: true` or started saying
  `destructiveHint: true`.
- **changes** — `serverId`, `observedAt`, `fromToolSetDigest` → `toToolSetDigest`, `summaryJson`
  (tools added, removed and changed, with the field that moved), `labelId` (the signed continuity label).
  For a package, `fromPackageVersion` → `toPackageVersion`: the last version that served the old list
  and the one that served the new list (null for remote servers and before 2026-10-26).
  For every change, `fromServerVersion` → `toServerVersion`: the version the server reported about itself
  (`serverInfo`) in the last run that served the old list and in the run that saw the new one; and
  `fromRegistryVersion` → `toRegistryVersion`: the version the MCP registry listed for the entry at those
  two runs. A change whose versions are equal on both sides moved at an unchanged version: a record keyed
  on the version cannot see it. Server versions come from every run since the log began (null when the
  server reported none); registry versions are recorded since 2026-10-28 and null before, and null for
  entries that come from no registry.
- **scans** — `toolSetDigest`, `patternSet`, `matchesJson` (rule code, tier, severity, tool, where).
  The rules are in `pattern-set.json`. A match is a pattern hit to look at, not a verdict.
- **classifications** — `toolSetDigest`, `model`, `verdictJson`: an LLM's advisory reading of the
  tool set. Not reproducible, so it never enters the signed log.
- **package_observations** — every run of an npm/PyPI package, failed ones included, oldest first:
  `serverId`, `observedAt`, `status`, `packageVersion` (the version the sandbox ran), `toolSetDigest`
  (join to toolsets; null when the run failed), `subjectDigest`, `toolExtrasDigest`, `toolCount`, and
  `serverName`/`serverVersion` as the server reported them in legacy initialization or modern result
  metadata (often not the package version), `registryVersion` (what the MCP registry listed for the entry
  at that run; since 2026-10-28), and `protocolVersion` when recorded (otherwise null).
  `packageVersion` is recorded since 2026-10-26; older rows have it null. `launchJson`
  says how the run was launched: `observer` (the sandbox's version), `image`/`imageTag`/`runtime`/
  `entry`, `network` (`no route out`: a server that fetches something at startup gets nothing), and
  `supplied` when HISTOR started it again with configuration: the env variable NAMES it set to
  placeholders (never a value), start `args`, `pins`. The same version can serve different tools under
  other launch args or with the network, so compare lists launched alike. Null on runs before it was
  recorded (2026-10-26). Remote servers are not in this file: their record is their changes.

## How a change is counted

- **What is compared.** Per tool, the members in `toolsets`: `name`, `description`, `inputSchema`, and
  `outputSchema` when the server sent one. Tools are sorted by name and the set is hashed in its RFC 8785
  form, so tool order, object key order and JSON whitespace never make a change. Strings are compared as
  sent (a description that only gains a space is a change), and so is the order of arrays inside a schema
  (`required`, `enum`). Other members (`title`, `annotations`, `_meta`, `icons`) are not in the digest;
  they are kept in `tool_extras`, and their changes in `extras_changes`.
- **When.** A change is a successful read whose digest differs from the server's previous successful
  read. Remote polling cadence depends on the observer configuration and available capacity; packages are read
  once per published version. States between polls can be missed. Every recorded change is
  recorded, including one that goes back to a list the server showed before.
- **Failed reads.** A timeout, an HTTP error, a server that asks for credentials or one HISTOR does not
  dial is never a change: the server keeps its last list, and `lastStatus` says how the last attempt
  went. A server that never answered without credentials has no tool set.
- **One client.** HISTOR reads without credentials, from one host. Lists that differ by user, account or
  region are not seen; a list that differs per session shows up as changes alternating between two digests.
- **What moved.** In `summaryJson`, a modified tool names the members that moved: `description` as a
  word diff, `inputSchema`/`outputSchema` as JSON paths (a parameter description is a path ending in
  `"description"`). A renamed tool is a removal plus an addition. `detail` is `names-only` when one side
  could not be digested; that change compares names only.

## Load it

```python
import pandas as pd
servers = pd.read_json("servers.jsonl.gz", lines=True)
changes = pd.read_json("changes.jsonl.gz", lines=True)
```

```sql
-- DuckDB
SELECT name, count(*) AS changes FROM 'changes.jsonl.gz' c
JOIN 'servers.jsonl.gz' s ON s.id = c.serverId GROUP BY name ORDER BY changes DESC LIMIT 20;

-- Changes in which nothing moved but tool descriptions
SELECT count(*) FROM (SELECT summaryJson::JSON AS s FROM 'changes.jsonl.gz')
WHERE s->>'detail' = 'full' AND json_array_length(s->'added') = 0 AND json_array_length(s->'removed') = 0
  AND json_array_length(s->'modified') > 0
  AND list_bool_and(list_transform(from_json(s->'modified', '["JSON"]'), m -> json_keys(m->'fields') = ['description']));
```

`scripts/change_kinds.py` in the code repository sorts every change by the fields it touched.

## What it is not

- A tool list is what a server advertised to an anonymous client on that day. Servers that need
  credentials, or that refused HISTOR, have no tool set here (`lastStatus`, `skipReason` say why).
- Pattern matches and classifier flags point at text worth reading; they do not say a server is malicious.
- A change is a change in the definitions, not a judgement of it. Most are ordinary releases.

## Cite

Artamokhov, A. (2026). *HISTOR snapshot 2026-11-02: MCP tool definitions and how they change* [Data set].
Zenodo. https://doi.org/10.5281/zenodo.23512759

This is the DOI of every snapshot (it resolves to the newest; each has its own version DOI on the record): https://doi.org/10.5281/zenodo.23512759.
Also on Hugging Face: https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions (tag `snapshot-2026-11-02`).

## License and rights

The compilation, digests, labels, scans and verdicts are CC-BY-4.0. Tool names, descriptions and schemas are reproduced as each server
published them; their rights stay with their authors. They are included so the definitions can be
studied and checked. A server operator who wants out: open an issue on https://github.com/alexar76/histor with the
endpoint or host. Opted-out servers are left out of every later snapshot.
