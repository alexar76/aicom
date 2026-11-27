# WARDEN 0.40.0 — the stdio MCP server answers MCP 2026-07-28

```bash
npm install -g @aimarket/warden@0.40.0
```

MCP revision 2026-07-28 has no `initialize` handshake: a client states its protocol version and capabilities in
every request and asks `server/discover` what a server speaks. Until this release `warden-mcp` answered that with
`method not found`, and a 2026-07-28 client had to fall back to the handshake.

`warden-mcp` now answers both. A request that carries its protocol version in `params._meta`, or asks
`server/discover`, is answered on its own: `server/discover`, `tools/list`, `tools/call` and the empty lists, with
`resultType`, the server's name and version in `_meta`, and `ttlMs` / `cacheScope` on the lists. An unsupported
version gets `-32022` with the versions the server speaks. A client that opens with `initialize` is answered exactly
as before (2025-03-26), and the nine tools are the same in both.

Nothing else changed: the static scan ruleset (24), the malware list, the gateway and every verdict are those of
0.39.2. In the built package only `dist/mcp-rpc.js` differs.

The full text is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.40.0/CHANGELOG.md).
