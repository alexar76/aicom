# HISTOR 0.5.0 — every change carries the server's version, and the registry's

```bash
pip install aimarket-histor          # NOT "histor" — that is a different project on PyPI
histor audit https://histor.modelmarket.dev      # verify the public log without trusting it
```

PyPI `aimarket-histor` 0.5.0 (2026-10-27). From the [CHANGELOG](https://github.com/alexar76/histor/blob/main/CHANGELOG.md):

- **A version on both sides of every change.** Each recorded change carries the server's own `serverInfo` version and the version the MCP registry listed, before and after (`from_/to_server_version`, `from_/to_registry_version`, migration 016), and every observation carries the registry version. Equal pairs mark a tool list that moved at an unchanged version — the question asked in the OWASP agent-control-standard discussion. Server versions are back-filled from recorded runs; registry versions start on 2026-10-28. In the API, the timeline and the weekly snapshot (`changes.jsonl.gz`, `package_observations.registryVersion`, manifest `changeVersions`). Live on histor.modelmarket.dev since 2026-10-28.
- **MCP 2026-07-28** in the remote reader, the package sandbox observer, the `tool-cost` stdio client and the local `histor mcp` server: discovery is probed before legacy initialization, with bounded fallback; recognised modern errors never downgrade, and interactive or incomplete results never become empty successful observations. Observed protocol versions stay in API timelines and dataset rows, with separate rows when the same list is read under another protocol.
- **`histor upgrade-brief`** (prototype, offline): a watchlist connects definition, schema and annotation changes to the workflows you chose, produces a retest checklist and records missing observations and changed launch/protocol context; `--lang ru|en|es|fr|zh`; a reproducible synthetic example in five languages. Real imports can declare unknown historical extras (`extrasCoverage: "unknown"`) instead of treating them as unchanged.
- Schema diffs keep JSON type differences (`const: true` → `const: 1` is visible).

Also in this release: `CITATION.cff` (the dataset's concept DOI is 10.5281/zenodo.23512759), and a README that finally says how to install the package.

Full list: [CHANGELOG.md](https://github.com/alexar76/histor/blob/main/CHANGELOG.md).
