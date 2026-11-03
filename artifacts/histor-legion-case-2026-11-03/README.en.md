# HISTOR and LEGION-tlog on one MCP server

[English](README.en.md) · [Русский](README.md) · [Español](README.es.md) · [Français](README.fr.md) · [简体中文](README.zh.md)

Can two independent transparency logs corroborate the tool definitions advertised by one MCP server at comparable times? We chose LEGION-tlog because it publishes an observation timestamp and a SHA-256 fingerprint for each tool. That lets us compare an earlier matching tool set and pinpoint the divergence from later observations of the same server, `com.aiapplyd/aiapplyd`.

| HISTOR observation (UTC) | Comparison with LEGION |
|---|---|
| 19 October 2026, 21:37:07 | All 23 fingerprints match the LEGION observation at 22:01:05 for `name`, `description` and `inputSchema`. |
| 24 October, 18:19:21 | All 23 names now start with `getmattered_` instead of `aiapplyd_`. Their suffixes match the earlier names. The archived LEGION response still shows the 19 October record. |
| 31 October, 12:45:49 | HISTOR records 40 tools with no names in common with the archived LEGION record. The 2 November snapshot contains this tool set. Its later read timestamp comes from snapshot metadata. |

## Offline verification

Run from the repository root with Node.js 22.

```sh
node artifacts/histor-legion-case-2026-11-03/replay.mjs
```

Compare the output with [result.json](result.json). The script verifies the Ed25519 signatures and inclusion proof for LEGION leaf 29030 under its signed tree head (STH) of 50,578 leaves. It then verifies the HISTOR STH of 1,564,894 leaves, the signatures and inclusion proofs for MTL/1 labels at leaves 762851, 988911 and 1324412, and the SHA-256 digest of each tool set bound to its signed label. It finally reruns the per-tool comparison.

The evidence covers these observations and these Merkle tree heads. Server safety, why LEGION did not record the later change in the saved response, consistency between heads and the Bitcoin anchor are outside the scope of the replay.

[Fixture provenance](README.md) · [HISTOR log documentation](../../histor/docs/log.md) · [LEGION specification](https://legion-api.com/tlog/docs/)
