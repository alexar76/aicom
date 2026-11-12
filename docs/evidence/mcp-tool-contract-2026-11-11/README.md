# MCP tool contract replay for Java SDK and Skillshare

This fixture gives [Java SDK #1272](https://github.com/modelcontextprotocol/java-sdk/issues/1272) and [Skillshare #789](https://github.com/runkids/skillshare/issues/789) the same before-and-after catalogues and expected results. Run it offline with Node 22. The runner reads the supplied JSON and exits nonzero on any mismatch.

```sh
node docs/evidence/mcp-tool-contract-2026-11-11/verify.mjs
```

## Real Chrome DevTools MCP observations

HISTOR recorded 32 tools on 16 October at 11:33:17 UTC (`serverInfo.version` 1.11.0) and 32 on 22 October 2026 at 18:59:22 UTC (`serverInfo.version` 1.12.0). Both observations report stdio with MCP `2025-06-18`. The archived records omit the resolved npm version, launcher arguments and authorization conditions for these two reads. The supplied arrays are the normalized tool definitions bound by the two signed labels. They contain `name`, `description` and `inputSchema`, with zero additions and removals across this change. This comparison concerns the advertised definitions. [Change 25495](https://histor.modelmarket.dev/api/v1/changes/25495) · [Server history](https://histor.modelmarket.dev/s/e50c44b0483a5e32)

| Tool | What the fixture checks |
| --- | --- |
| `list_console_messages` | Only the `pageIdx` and `serviceWorkerId` descriptions changed. |
| `list_network_requests` | `resourceTypes.items.enum` lost `websocket`. The `pageIdx` description also changed. |
| `wait_for` | The optional Boolean `visible` appeared with default `false`. The tool description also changed. |

`observed.before.json` and `observed.after.json` preserve the downloaded arrays. Their source URLs are the [before digest](https://histor.modelmarket.dev/api/v1/toolsets/sha256-8%2BlE4g0m%2F%2F4edWK0ysMX2r4RymStpy75SKP%2BdJHXb4o%3D) and [after digest](https://histor.modelmarket.dev/api/v1/toolsets/sha256-PYy2R08yoXf%2Fucl%2BUsPs5cX%2BavWYVb15qS2J0uXLg1Q%3D). The [Chrome DevTools MCP license](LICENSE.chrome-devtools-mcp.txt) accompanies the tool definitions. The other captured inputs came from the HISTOR API on 11 November around 13:54 UTC. Use the installed HISTOR development environment to reproduce the proof check.

```sh
histor/.venv/bin/python docs/evidence/mcp-tool-contract-2026-11-11/verify-evidence.py
```

The script binds both digests to their labels, checks the linked prior label, verifies both signatures against the pinned HISTOR issuer and validates inclusion of leaves 657251 and 862840 at signed tree size 2065020. It also confirms that increasing either label's tool count invalidates its signature and inclusion proof. The signatures establish what HISTOR recorded under that issuer key.

## Consumer tests

`vectors.json` has named `captures` and a list of `cases`. Each case points to its two captures by name. A capture with `file` loads the `tools` array from that file. The other captures embed their tool arrays and are marked synthetic in the cases. Java and Go tests can load the JSON directly and exercise their own implementation. `verify.mjs` gives a runnable reference for the nine supplied cases.

- **Java SDK.** Assert the expected additions, removals and changed triples per tool. Check `outputSchemaChanged` and `effectiveReadOnlyChanged` separately. The fixture uses `false` as the effective value when `readOnlyHint` is omitted. The synthetic cases cover output-only drift, the omitted-to-explicit-default transition, a change to the effective hint and an input parameter becoming required.
- **Skillshare.** Save the complete catalogue at approval. The stable case must pass when object keys and tool list order change. Compare a fresh catalogue on sync and show the three observed changes at field level. The fixture compares complete catalogues from the same target, transport, negotiated protocol, authorization scope and launch profile. The synthetic partial page and authorization mismatch require a distinct result before comparing digests.

The fixture's triple digest projects `name`, `description` and `inputSchema`. Its MTL/1 digest also projects `outputSchema` when present. Both serialize the projected tools as a name-sorted array of RFC 8785 JSON and retain order inside schema arrays. The triple projection is defined here for the tests. Use the selected pin specification's encoding when integrating it in a client. Store a scope identifier representing the authorization boundary and drain all pages before pinning. The archival comparison replays tool fields with unknown historical launch and authorization conditions. It is evidence for the diff implementation. The host decides how to act on each kind of change.

For a local WARDEN comparison, use the CLI entry point from the 0.26.0 release.

```sh
node docs/evidence/mcp-tool-contract-2026-11-11/warden-replay.mjs /path/to/warden/dist/mcp-server.js
```

That replay loads the three affected tools into a local fixture server. WARDEN recorded the first list, passed an unchanged read, reported `TOOL_DEF_DRIFT` for the three tools after the change, and preserved the original lock. [WARDEN replay result](warden-result.json)
