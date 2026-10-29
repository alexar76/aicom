# Complete WARDEN source-build observations

These are fresh local MCP observations captured on 27 October 2026. They replay an exact older
Git source version and the current local source; they do not reconstruct the original HISTOR
capture's protocol, launch context or extras, and they do not attest independently downloaded
npm artifacts.

| Snapshot | Executed source manifest version | Observed protocol | Full tools | Purpose |
|---|---|---|---|---|
| [replay-before.json](replay-before.json) | 0.18.0 | 2025-03-26 | 9 | Current-time replay of Git commit `fec7b195b8675ea5b74c18a7e65c0e3568c102a0` |
| [current-baseline.json](current-baseline.json) | 0.22.1 | 2025-03-26 | 9 | Current local working-tree build, including the local `server_info` validation fix |
| [current-recheck.json](current-recheck.json) | 0.22.1 | 2025-03-26 | 9 | Independent fresh process with the same current artifact and launch policy |

All three snapshots preserve the full received tool objects, including `title`, `annotations`
and output schemas where present. `extrasCoverage` is `observed`; absent extras are recorded
as absent, without filling values from another observation. Package manifest versions and
server-reported versions are stored separately. They matched in these source-build runs.

## Launch and collection

Both versions were compiled with the existing TypeScript compiler and installed Node types;
no packages were downloaded or installed. The old source is exported directly from local Git.
The current source is copied from the working tree. The explicit `--types node` compiler
selection is needed for the historical tsconfig with this installed compiler. Build commands,
source hashes, compiled JavaScript hashes, compiler files and runtime identity are recorded in
[build-provenance.json](build-provenance.json).

Each server runs from its isolated artifact root using Node 22.22.1 and the same logical command
`node dist/mcp-server.js`. Artifact content/version changes are described in provenance, rather
than treated as a different transport or access profile. The clean environment contains only
`PATH` and `WARDEN_STATE_DIR`; snapshots expose environment names and policies, not values.
State is empty before and after each process. Pin changes remain disabled.

macOS `sandbox-exec` applies `(version 1)(allow default)(deny network*)` to the Node process.
This is a network denial profile, not a filesystem sandbox. The only MCP requests sent were
`server/discover`, legacy `initialize`, `notifications/initialized` and `tools/list`. The actual
server responds through the legacy protocol. No tool calls, approvals or other pin operations
were performed. Per-capture wire records, process exit codes and provenance accompany snapshots.

## Comparison results

- [Source replay comparison](comparison-replay.json): **changed**, comparable, full coverage.
  The old and current definitions show the `server_info` input changes and status output changes.
- [Current recheck comparison](comparison-stability.json): **unchanged**, comparable, full coverage.
  This establishes observed current definition stability, not runtime behavior or safety.
- [Verification](verification.json): the old replay's MTL core digest exactly matches the
  original HISTOR before digest `sha256-E6s0oh417i8CZLJYVTuZwy9F51CcSlL9UPpZR7BE2Mk=`;
  the current build's core digest exactly matches the original HISTOR after digest
  `sha256-oc4ZUKD5KONt5yMkyZbMvboUIcQgK+oZc+qqAQIRov0=`.

The digest match confirms the same observed core contracts. It does not prove that newly
observed extras or launch conditions were present in the historical sessions. The local
runtime guard fix changes behavior without changing these advertised tool definitions;
its separate regression evidence remains necessary.

## Reproduce locally

From the workspace root, use the existing local toolchain:

```bash
histor/.venv/bin/python -S -B docs/evidence/histor-full-observations-2026-10-27/warden/capture.py --prepare
histor/.venv/bin/python -S -B docs/evidence/histor-full-observations-2026-10-27/warden/capture.py
histor/.venv/bin/python docs/evidence/histor-full-observations-2026-10-27/warden/verify.py
```

The capture worker uses the existing HISTOR environment with its installed `httpx` dependency;
the parent driver can run without site-packages. macOS must allow applying a nested sandbox.
In Codex's restricted execution sandbox this required automatic approval for the local
deny-network launcher. Derived builds and empty state directories live under ignored `.work/`.
Original historical evidence and product sources are not modified. All work remains local;
no GitHub write or deployment is involved.
