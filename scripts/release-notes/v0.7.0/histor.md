# HISTOR 0.7.0 — a witnessed, tiled log that reads robots.txt

```bash
pip install aimarket-histor          # NOT "histor" — that is a different project on PyPI
histor audit https://histor.modelmarket.dev      # verify the public log without trusting it
```

The last GitHub release was v0.4.1 (2026-10-25). PyPI has 0.5.0 through 0.7.0; 0.7.0 was published on 2026-11-08. What changed, from the [CHANGELOG](https://github.com/alexar76/histor/blob/v0.7.0/CHANGELOG.md):

- **0.7.0: MTL/1.2.** Every label names the revision of the rules that decided it, and says why a set has no digest. A package that an older revision declined runs once more. Cross-checks with other observers come from one list (`deploy/peers.json`).
- **0.6.2: the log is also a tiled log** ([c2sp.org/tlog-tiles](https://c2sp.org/tlog-tiles)).
- **0.6.0: the crawler follows robots.txt** (RFC 9309).
  - A remote endpoint's MCP server card is read as a declaration.
  - A 402 says why HISTOR did not read, for example `pay-per-crawl`.
  - The datasets page cites each snapshot by its own Zenodo version DOI.
- **0.5.3:**
  - Legacy MCP servers are read again.
  - `python -m histor.peer_xcheck` compares HISTOR with another public log.
  - `/api/v1/changes?after=<id>` reads from a cursor.
  - Webhooks connect to a checked public address.
- **0.5.2: C2SP checkpoints and witnesses** (`histor-tlog/2`): consistency-proof verification, dedicated witness keys and `witness-submit`.
- **0.5.1: `uvx aimarket-histor`** is an MCP server with three tools, `histor_changes`, `histor_check` and `histor_server`, that query a public instance.
- **0.5.0: a version on both sides of every change.** Each change carries the server's `serverInfo` version and the registry's version, before and after. The readers speak MCP 2026-07-28, and `histor upgrade-brief` turns changes into a retest checklist.

Not in 0.7.0: `GET /api/v1/check?endpoint=…`. It has been live on the public instance since 2026-11-09 and is in the next release.

Full list: [CHANGELOG.md](https://github.com/alexar76/histor/blob/v0.7.0/CHANGELOG.md).
