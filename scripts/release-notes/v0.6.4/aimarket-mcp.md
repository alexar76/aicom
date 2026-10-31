# aimarket-mcp 0.6.4 — keyless HTTP is refused even on loopback

```bash
uvx aimarket-mcp            # stdio, for Claude Code / Cursor / any MCP client
pip install aimarket-mcp
```

The last GitHub release was v0.3.0 (2026-08-12); PyPI has carried 0.4.x–0.6.4 since. The security line since 0.6.0 (2026-10-22), from the [CHANGELOG](https://github.com/alexar76/aimarket-mcp/blob/main/CHANGELOG.md):

- **0.6.4 (2026-10-28)** — keyless HTTP is now refused by default even for loopback sockets owned by the server's own user: an arbitrary same-user proxy or tunnel is indistinguishable from a direct client, so "this machine" can no longer be inferred from the socket. Set a bearer key for any networked use; **stdio is unchanged** and needs no key.
- **0.6.0–0.6.3** — the fixes from the October outside reviews (Vulnetix and our own audit of the same class): SSRF hardening of `web_fetch`, fail-closed configuration, and the same-host proxy check that 0.6.4 completes.

Six tools behind one endpoint: `market_search` and `market_invoke` (the hub's free trial tier, signed receipts, no wallet or key), `web_fetch`, `web_search`, `metis_verify` and `market_status`. Glama TDQS: 4.3/5.

Full list: [CHANGELOG.md](https://github.com/alexar76/aimarket-mcp/blob/main/CHANGELOG.md).
