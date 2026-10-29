# Oracle Gateway and Packager full observations

Eight real, list-only captures were collected locally on 27 October 2026. The collector used
the existing clean release environment at `/private/tmp/pypi-mcp-releases-20261027` with
CPython 3.12.13 and MCP SDK 1.30.0. Exact first-party wheels were unpacked into this evidence
directory; no package installer or dependency resolver was run.

## Comparison results

| Comparison | Before | After | Result |
|---|---|---|---|
| Oracle current stability | 0.3.2, full 36 tools | 0.3.2, full 36 tools | `unchanged`, comparable, full coverage |
| Packager current stability | 2.1.2, full 3 tools | 2.1.2, full 3 tools | `unchanged`, comparable, full coverage |
| Oracle controlled upgrade replay | 0.3.1 exits during tool registration | 0.3.2, full 36 tools | `unknown`: no successful old definition set |
| Packager controlled upgrade replay | 2.1.1, full 3 tools | 2.1.2, full 3 tools | `unchanged`, comparable, full coverage |

The successful observations negotiated protocol `2025-06-18`. Captures retain complete raw
`tools/list` objects. These servers advertised no additional tool keys beyond `name`,
`description`, `inputSchema` and `outputSchema`; `extrasCoverage: observed` records their
observed absence. No annotation fields were invented. Initialize results, including
instructions and capabilities, remain in the corresponding capture evidence.

Packager 2.1.1 self-reports server version **1.30.0**, inherited from the SDK. Its wheel
metadata identifies the package version as **2.1.1**. Both values are preserved separately.
The new Packager reports server and package version 2.1.2. Unchanged tool definitions do
not test generator behavior, Docker flags or the generated relay.

Oracle 0.3.1 fails with FastMCP `InvalidSignature` while registering `aggregate_values`.
The [stderr](upgrade-oracle-gateway-before-stderr.log) and failed snapshot preserve that
failure; it was not patched into an artificial success.

## Files and provenance

- [Verification](verification.json) checks eight snapshot hashes, all wheel hashes, extracted
  package metadata and source hashes, captured tools against complete list responses,
  actual initialize protocol/serverInfo and absence of `tools/call` requests.
- `snapshots/current-*-baseline.json` and `snapshots/current-*-recheck.json` are fresh current
  baseline/recheck pairs. These measure definition stability now, without recreating a
  historical package transition.
- `snapshots/upgrade-*-before.json` and `snapshots/upgrade-*-after.json` are exact version
  replays captured now under one fixed runtime/dependency profile. They are not the original
  historical observations downloaded from HISTOR.
- `*-evidence.json` records exact artifact hashes, physical resolved source paths, actual
  argv, normalized successful response results, sent requests and archived collector hashes.
- [Runtime inventory](runtime.json), [artifact index](artifact-index.json) and
  [old-wheel receipts](old-wheel-downloads.json) identify installed dependencies and artifacts.
- `sources/` stores the exact collector, launcher and reader source bytes used for this run,
  addressed by SHA-256. The capture helper subsequently gained an equivalent metadata assertion
  for future collections; archived bytes preserve the code that actually ran.

Old wheels were downloaded read-only from the exact official PyPI file URLs already saved
in registry evidence. Their SHA-256 values matched those records. Current wheels were
reused from the earlier verified release evidence. No GitHub writes were made.

## Launch and execution limits

All server processes ran with a clean environment containing only `PATH`, no credentials,
Python `-I -B`, an isolated working directory and an explicit known package overlay.
The logical overlay path and argv remain stable between versions; its resolved artifact
directory and bytes are recorded separately in each receipt. The actual SDK and dependency
profile remain unchanged. The installed clean environment was not modified.

A Python audit guard denies DNS resolution, socket connections and child process execution.
This is a Python audit guard, not an OS network namespace or container sandbox. The reader
allows only discovery, initialize, initialized notification and paginated `tools/list`;
it does not invoke any tool. No paid calls, Docker commands, deployment, publishing or
production state writes occurred.

Current successful snapshots provide new complete baselines. They cannot fill missing
protocol, launch or extras in earlier HISTOR timeline rows. The Oracle old-release gap
remains genuine even though the current release starts successfully.
