# WARDEN 0.22.2 — strict `server_info`, an opt-in answer gate, egress regressions

```bash
npx -y @aimarket/warden@0.22.2 scan
```

The GitHub release before this one was v0.21.0; npm has carried 0.22.0, 0.22.1 and 0.22.2 since 2026-10-26/27. What changed, from the [CHANGELOG](https://github.com/alexar76/warden/blob/main/CHANGELOG.md):

- **0.22.2** — MCP status and approval calls reject unknown keys in `server_info`, matching the schema that already said `additionalProperties: false`. Calls without `server_info`, empty metadata and partial `name`/`version` objects behave as before. Invalid metadata is rejected before an approval is written; reviewed hashes, revision checks and operator opt-in are still required.
- **0.22.1** — ships the local source that npm 0.22.0 did not include: an opt-in, host-owned structured answer gate (`createAnswerGate`: host-frozen numeric/boolean rules, safe record references, complete eligible-set and optional ranking checks) and captured-fact repair feedback for numeric ranking and missing eligible sets. Frozen experiment snapshots keep their original results.
- **Reference-only egress checks (2026-10-26)** — 25 synthetic regressions for reference-only outbound payloads, observed intermediary results, new turns, operator labels, modes and exact one-use grants. Expected review/deny behaviour is documented apart from explicit policy exemptions; an exact grant does not certify that a payload is semantically public.
- **Ruleset v16 unchanged** since 0.20.0: 210 of 218 poisoned tools on the MCPTox held-out half, 0 of 45 clean servers.

New in the repository with this release: [`examples/scan-demo/`](https://github.com/alexar76/warden/tree/main/examples/scan-demo) — three stdio servers (benign, poisoned, broken) that reproduce the README's `scan` output with nothing installed; `warden-mcp --help` lists every subcommand; `CITATION.cff`.

Full list: [CHANGELOG.md](https://github.com/alexar76/warden/blob/main/CHANGELOG.md).
