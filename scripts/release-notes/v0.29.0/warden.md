# WARDEN 0.29.0 — known-malicious packages are not started

```bash
npx -y @aimarket/warden@0.29.0 scan
```

`warden scan` and `wrap` start a stdio server to read its tools, and `npx -y` or `uvx` runs the package's install scripts on the way. A package that is already known to be malware has run before any tool definition can be read. 0.29.0 checks the package first. The full list of changes is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.29.0/CHANGELOG.md).

- **New gate `malware-list`.** It reads the package and version from the launch line (`npx`, `bunx`, `npm exec`, `pnpm dlx`, `yarn dlx`, `bun x`, `uvx`, `uv tool run`, `pipx run`) and looks them up in a list that ships in the package. `vetLaunch` runs it, so a match is refused before anything starts. Nothing is fetched at run time.
  - **OpenSSF malicious-packages** (commit f8c4d3d, 2026-11-17): 224,098 npm and 12,034 PyPI packages. `KNOWN_MALICIOUS_PACKAGE`, critical, blocks: every version is listed, the pinned version is listed, or the launch pins none while every version from some release on is listed.
  - **Listed releases a launch may or may not get**: `KNOWN_MALICIOUS_VERSIONS`, advisory, "pin a version that is not listed". A record that names its bad releases and also claims every version blocks the named ones only. npm had replaced or removed all 40 packages we sampled with such records, and one such record covers an official server (`@browserbasehq/mcp` 2.1.1 removed, 3.0.0 served).
  - **OpenSourceMalware.com**, read from the Vulnetix advisory database (commit c337489), for 1,234 npm and 228 PyPI packages OpenSSF does not list: `REPORTED_MALICIOUS_PACKAGE`, advisory only. The registry still served 27 of 40 sampled npm and 11 of 20 sampled PyPI packages of that kind.
- **What it changes.** We ran the gate on the 14,933 npm and PyPI MCP server packages HISTOR knew on 2026-10-16. At the observed versions it blocks 3 (`@2oolkit/hyperliquid-cli` 0.2.7, `vulndify-mcp-server` 0.3.0, `agentic-awesome-skills` 19.7.0) and reports 3. Without a version pin it blocks none and reports 24. Among those 24 are `@postman/postman-mcp-server`, `@antv/mcp-server-chart` and `@mastra/mcp-docs-server`, which once shipped compromised releases. The files are in `docs/evidence/malware-list-2026-11-17/`.
- **Report.** The scan header says `malware list 2026-11-17`. The JSON and SARIF reports gain `malwareList` with the package count, the SHA-256 and the source commits. A list that is missing or altered is not used, and the header then says `malware list OFF`.
- **For library hosts.** The list is pinned by SHA-256 in the build, so the MOMUS build digest covers it. `Warden.create({ malwareList: null })` leaves the gate out. The new exports are `MalwareList`, `MalwareListGate`, `matchPackage`, `matchEntry`, `compareVersions` and `launchPackage`.
- **Also in this release.**
  - `StaticScanGate.evaluate()` returns the ruleset ref (suggested in [#14](https://github.com/alexar76/warden/issues/14)).
  - The GitHub Action's description is 120 characters, for a Marketplace listing.
  - Rulesets are unchanged (23).

Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list: `sha256:b656eb8a15d8b2d0ad9d54a4f02606f9fd28a460d90dbc8d91968ffc38b80526`, 237,594 package lines.

The package grows by the 2.4 MB compressed list.

Checks for this build:

| Check | Result |
|---|---|
| Tests | 1908 of 1908 |
| Red team, Claude Code profile | 0 of 28 attacks delivered; field regressions 0 of 4 |
| Doc version pins (`check-doc-versions --release`) | pass |
| MOMUS release gate | recorded in the monorepo evidence folder when the run passes |
