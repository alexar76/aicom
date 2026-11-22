# CrawlCheck's tool_set_digest values, checked independently — 2026-11-22

On modelcontextprotocol/registry#82 (comment 7082866737, 17:28Z) Emmanuel Orta wrote that CrawlCheck's Python
(`crawlcheck` 1.16.3) and JS (`@crawlcheck/sdk` 1.15.2) SDKs give every value of the 73 vectors of
`mcp-tool-set-digest/1` at aca5812, and that `GET /api/v1/mcp/lock` on crawlcheck.io now returns a `tool_set_digest`
block, with contract `sha256-9Z/eIkZH55y+8m9M7PHYr4pURSkVrVOJlxlb0pHia3w=` and extras
`sha256-G44DGgW7+rp9YjMAaEG80Tm5RFoke8eYkrE6nGk69y8=` for io.github.emmanuelorta/crawlcheck (28 tools).

| Check | Result |
|---|---|
| aca5812 | head of the GitHub mirror alexar76/mcp-tool-set-digest (2026-11-13T18:44:52Z); `vectors/vectors.json` there is byte-equal to aicom main's (73 vectors); our Python implementation passes all 73 |
| Our read of `https://crawlcheck.io/mcp`, 19:33Z (`read_tools_list.py`, output `tools-list-…json`) | initialize + tools/list three ways: `MCP-Protocol-Version` 2025-11-25, 2025-06-18, and no header (initialize asks for 2025-06-18); each one page, no `nextCursor`, 28 tools, the same list |
| Digests of that list, `mcp-tool-set-digest/implementations/{python,javascript}` | contract `sha256-9Z/eIkZH…a3w=`, extras `sha256-G44DGgW7…y8=` in all three reads and both implementations, equal to his |
| HISTOR, `/api/v1/servers/5a5b50f1ee6c3444` | last observation 19:15:40Z (734 observations), 28 tools, contract digest the same; last extras change 2026-11-07T17:48:51Z to `sha256-G44DGgW7…y8=` |
| `GET /api/v1/mcp/lock?url=https://crawlcheck.io/mcp`, 19:33:40Z (`crawlcheck-lock-…json`; CrawlCheck read the server itself) | `tool_set_digest.spec` `mcp-tool-set-digest/1`, both digests the same and equal to `jcs_v1.tools_sha256` / `extras_sha256`; `sha256` = SHA-256 of the sorted-key, no-whitespace JSON of every other field; Ed25519 signature over `crawlcheck-data-v1\n<sha256>` verifies with the embedded JWK; `kid` is the key's RFC 7638 thumbprint; the same key is in `/.well-known/http-message-signatures-directory` (`crawlcheck-key-directory.json`) |
| His two SDKs | not run (third-party code); his vector claim is not checked here |

Reading conditions in his lockfile (spec section 11): endpoint, time and `server.protocol_version` (2025-06-18) are
there; whether the protocol header was sent, the page count and whether the request was authorised are not. For this
server header and paging change nothing (one page, the same list with and without the header).

Reply draft for the owner: `PromoMaterials/outreach/registry-82-crawlcheck-2026-11-22.md`.
