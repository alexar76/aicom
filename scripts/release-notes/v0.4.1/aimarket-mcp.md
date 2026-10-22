# aimarket-mcp 0.4.1 — one MCP server for web fetch, search and Metis verification

Since 0.3.0 (August):

- **A prepaid key works everywhere.** `AIMARKET_API_KEY` pays priced calls from your balance; a short balance still gets the free trial; an unknown key is refused with the fix, not a payment wall. Clients that take a URL but no header can use `https://modelmarket.dev/mcp/k/<key>`.
- **Failures say what happened without leaking.** A failed Metis verification names the public host and the reason, never credentials, query strings or the upstream body. Tests lock the redaction in.
- **Correct versions.** Published wheels announced an old version, and the `mcp` ceiling let 2.x break FastMCP on import. Both fixed; the package, the registry manifest and the module now agree.
- **CI hardened.** Every action pinned, read-only default tokens; coverage 71% → 74%.

```bash
uvx aimarket-mcp
```

Listed in the [official MCP registry](https://registry.modelcontextprotocol.io/) and on [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp). Note: PyPI has 0.4.0 at the time of this release. 0.4.1 changes only error text, docs and version metadata.
