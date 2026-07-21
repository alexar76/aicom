# Official MCP Registry — alexar76 MCP stack

Canonical upstream: [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io). Glama, PulseMCP and other directories ingest from here — **publish here first**.

Machine-readable index: [`official-registry-servers.json`](official-registry-servers.json).

## Live status (check anytime)

```bash
curl -fsSL "https://registry.modelcontextprotocol.io/v0.1/servers?search=alexar76" \
  | python3 -c "import json,sys; [print(s['server']['name'], s['server']['version'], s['_meta']['io.modelcontextprotocol.registry/official']['status']) for s in json.load(sys.stdin)['servers']]"
```

| Registry name | Monorepo `server.json` | GitHub repo |
|---------------|--------------------------|-------------|
| `io.github.alexar76/aimarket-mcp` | [`aimarket-mcp/server.json`](../../aimarket-mcp/server.json) | [alexar76/aimarket-mcp](https://github.com/alexar76/aimarket-mcp) |
| `io.github.alexar76/aimarket-oracle-gateway` | [`plugins/aimarket-oracle-gateway/server.json`](../../plugins/aimarket-oracle-gateway/server.json) | [alexar76/aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) |
| `io.github.alexar76/aimarket-plugins` | [`plugins/aimarket-mcp-packager/server.json`](../../plugins/aimarket-mcp-packager/server.json) | [alexar76/aimarket-plugins](https://github.com/alexar76/aimarket-plugins) |
| `io.github.alexar76/argus3` | [`argus/server.json`](../../argus/server.json) | [alexar76/argus](https://github.com/alexar76/argus) |

## Publisher CLI (`mcp-publisher`)

Install (macOS/Linux):

```bash
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" \
  | tar xz mcp-publisher
```

Or Homebrew: `brew install mcp-publisher`.

### Local validate (before publish)

From monorepo root:

```bash
./scripts/publish_mcp_registry.sh --validate-only
```

Or per satellite:

```bash
cd aimarket-mcp && ../path/to/mcp-publisher validate server.json
```

### Authenticate (human, once per machine)

```bash
mcp-publisher login github
```

Namespace must match GitHub user/org: `io.github.alexar76/*`.

### Publish

**CI (recommended):** each satellite has `.github/workflows/publish-mcp-registry.yml` — OIDC `github-oidc` login, runs on release or `workflow_dispatch`.

Dispatch all from monorepo (needs `GH_PAT` as **alexar76**):

```bash
./scripts/publish_mcp_registry.sh --dispatch
```

**Manual:**

```bash
cd aimarket-mcp
mcp-publisher login github
mcp-publisher publish server.json
```

## Ownership verification (required)

| Package type | Proof |
|--------------|--------|
| **PyPI** | `<!-- mcp-name: io.github.alexar76/… -->` in README (PyPI description) |
| **npm** | `"mcpName": "io.github.alexar76/…"` in `package.json` |

**PyPI package version in `server.json` must exist on PyPI** before publish succeeds.

## After registry publish

1. Glama — Sync Server (build steps for aimarket-mcp: see [`aimarket-mcp/docs/GLAMA.md`](../../aimarket-mcp/docs/GLAMA.md))
2. awesome-mcp-servers — PR [#9910](https://github.com/punkpeye/awesome-mcp-servers/pull/9910)
3. mcp.so / Smithery — forms (see [`docs/growth/seeding-playbook.md`](../growth/seeding-playbook.md))

PromoMaterials mirror: `../PromoMaterials/mcp-registries/` (sibling folder outside `aicom3`).
