# Real package changes for a review demonstration

Selected from the immutable 2026-10-20 HISTOR dataset. Downloaded and statically checked on 2026-10-25. These are examples of changed instructions and interfaces, not accusations against the package publishers.

| Case | npm versions | tools | Useful distinction |
| --- | --- | --- | --- |
| [17172](https://histor.modelmarket.dev/api/v1/changes/17172) | `@mapled/mcp` 0.21.5 → 0.21.6 | 33 → 33 | Two descriptions change how the agent waits for and follows an approval made on the publisher's screen. |
| [20433](https://histor.modelmarket.dev/api/v1/changes/20433) | `@browserbridge/bbx` 1.12.2 → 1.12.5 | 6 → 6 | Description changes to batching/ordered flows and when to stop for new approval. |
| [23671](https://histor.modelmarket.dev/api/v1/changes/23671) | `@suparse/mcp` 1.4.0 → 1.5.0 | 10 → 17 | Added tools, schema changes and revised extraction/approval descriptions. |

For each case, `from-toolsets.json` and `to-toolsets.json` are complete raw API responses. `toolsets.diff` is a display generated from these raw objects. `case-summary.json` lists all changed tools and fields. The `from-descriptors.json` and `to-descriptors.json` subjects intentionally carry unversioned package identifiers; they do **not** prove the executed npm version by themselves.

`fetch-verification.json` records public GET URLs, response hashes, and recomputed MTL/1 tool-set/subject digests. All six tool-set and six descriptor digests match the frozen dataset. `server.json` preserves the live public API response and its observation timeline; `snapshot-metadata.json` preserves the frozen row.

Exact npm metadata and static archive inspection results are retained as `from-npm-*` and `to-npm-*`. All six public tarball integrity values and SHA-1 values were checked before examining text. The archives were read in memory; no archive was extracted to disk, installed or executed, and no lifecycle scripts or MCP calls were run.

For Mapled, both descriptions modified in the recorded event match the corresponding pinned npm archive's full description text, assembled solely from adjacent JSON string literals in `package/dist/tools.js`. Twenty-nine of 33 full descriptions match by this method in each version; the remaining four are not claimed as statically verified. The latest successful public observation is exactly the changed event at 2026-10-13T14:12:49Z, and its package signals name 0.21.6 with previousVersion 0.21.5. The protocol handshake advertises 0.1.0 for both observations, so it must not be used as the npm version.

For Browser Bridge, the six full descriptions in each snapshot match the respective pinned archive. The live package is now newer than the recorded event; use the pinned versions and saved timeline, not the current packageVersion, when describing this example. All 10/17 Suparse descriptions also match their corresponding pinned archive.

Pinned commands for a future isolated reproduction, **not executed in this research**:

```sh
npm exec --yes --package=@mapled/mcp@0.21.5 -- mapled-mcp
npm exec --yes --package=@mapled/mcp@0.21.6 -- mapled-mcp
```

Mapled requires its normal publisher token. A fresh unauthenticated launch is not expected to reproduce the successful tools/list observation. These commands identify the executable artifact, but the saved raw toolsets are the reproducible review input used here.

AI disclosure: AI agents selected the examples, wrote the read-only analysis scripts and prepared this evidence under the ecosystem maintainer's direction.
