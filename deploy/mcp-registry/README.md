# Official MCP registry entries under dev.modelmarket/*

The four free topic servers of the okx-a2mcp gateway (`okx-a2mcp/src/mcp/`), published to
registry.modelcontextprotocol.io with HTTP domain authentication for modelmarket.dev:
`https://modelmarket.dev/.well-known/mcp-registry-auth` holds the public half of an Ed25519 key that
lives only in `/opt/mcp-registry/key.pem` on the apex host (factory-vps), next to `mcp-publisher` v1.8.1.

Publish a new version (bump `version` first), on the apex host:

    cd /opt/mcp-registry
    PK=$(openssl pkey -in key.pem -noout -text | grep -A3 "priv:" | tail -n +2 | tr -d " :\n")
    HOME=/opt/mcp-registry ./mcp-publisher login http --domain modelmarket.dev --private-key "$PK"; unset PK
    HOME=/opt/mcp-registry ./mcp-publisher publish <dir>/server.json
