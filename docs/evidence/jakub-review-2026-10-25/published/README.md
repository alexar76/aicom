# Published WARDEN 0.21.0 replay — real Mapled transition 17172

Executed on **admin-vps / Linux amd64 / Node v22.23.3**, 2026-10-25 09:41 UTC. This replay executes only the ecosystem's own published `@aimarket/warden@0.21.0`. It never runs Mapled, `npx @mapled/mcp`, a target handler, or another external MCP package.

## Evidence and result

- Real, complete before/after definitions: `../real-cases/17172/from-toolsets.json` and `to-toolsets.json`; **33 → 33 tools**, two description changes, no added/removed tools.
- Original change: `../real-cases/17172/change.json`, HISTOR observation **2026-10-13T14:12:49Z**. Package release mapping is a separate evidence step; this replay does not execute or verify an installed Mapled artifact.
- `diff.json` contains the complete structured diff; `review.txt` contains `formatDefinitionDiff` output.
- `rpc-transcript.json` preserves full NDJSON JSON-RPC requests and responses from the actual published `dist/mcp-server.js`, including complete tools payloads. It is an isolated test session.
- The test explicitly approves only the original snapshot in a disposable state directory. The changed snapshot is inspected, never approved. Repeated status calls keep the old approval and continue showing drift.
- The newly added **“and carry on without asking”** phrase on `propose_setup_plan` receives the `approval` attention marker. Removing only that phrase in an otherwise real after snapshot removes the marker. That marker is a reading cue, not a finding that Mapled is malicious or a substitute for reviewing its approval workflow.
- The changed tools are detected while the supplied MCP `serverInfo.version` remains **0.1.0** on both sides. The launcher metadata `npx -y @mapled/mcp` is recognised as having no exact package version. The launcher is never run.
- **15 behavioral assertions pass, but a separate version-advice defect is present:** the published review suggests `@mapled/mcp@0.1.0`, using the self-reported MCP version as an npm package pin. That is not supported: the associated package releases under review are **0.21.5 → 0.21.6**. The 15 assertions do not claim that this version advice is correct. See `review-observations.json`.

`serverInfo.name=mapled` is fixture metadata; its spelling is not claimed as an independently verified historical initialize name. The historical version supplied to the fixture is kept separate from npm package provenance. No human usability study is claimed.

## Runtime and integrity

`execution.json` records the exact Docker command, transferred input SHA-256 hashes, timestamps, and registry archive verification. The immutable image is `sha256:e1b65057659c168cb8510100daeca2f95d6e3f7ec081ed1b98f217591359b7a3`. Runtime **runc**, network **none**, read-only root and code mounts, UID/GID **65532**, 512 MiB memory, 1 CPU, 64 PID limit, dropped capabilities, no-new-privileges, 64 MiB noexec tmpfs. This is not a gVisor run.

The own public archive was downloaded on the server and checked against both registry integrity and the previously recorded SHA-256:

- URL: `https://registry.npmjs.org/@aimarket/warden/-/warden-0.21.0.tgz`
- SHA-256: `5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1`
- SHA-512 SRI: `sha512-mahzo72wcLhz0yNRC+IAi1jLVfa7i9amu40Gw/HVGTTJ5y46rQPS5/euAhrCKYH2E1VG7NNNVXYNxDjzi9QYHQ==`

Only the new `replay.mjs` and three public JSON files were transferred from the workspace. There were no credentials or deployment settings. The package was extracted as regular files/directories only. All 13 generated output artifact hashes and all four transferred input hashes were verified after download. `checksums.json` is the original server output manifest; extra local explanatory files are covered by `local-artifact-hashes.json`.

The exact remote temporary directory was removed after verification; `cleanup.json` records the result. Production state was never mounted or changed.

AI disclosure: AI agents prepared this replay, ran the analysis and wrote these notes under alexar76's direction.
