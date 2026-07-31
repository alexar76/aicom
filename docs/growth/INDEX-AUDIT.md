# Ecosystem discovery & indexing — status

Last updated: 2026-07-12. Source of truth for growth tasks in the monorepo.

## Automated (alexar76 token / publish scripts)

| Action | Command |
|--------|---------|
| Mirror satellites | `./scripts/publish_all_repos.sh --satellite <id>` |
| Homepage + topics | `./scripts/apply_github_metadata.sh` |
| MCP Registry publish (GHA) | `./scripts/publish_mcp_registry.sh --dispatch` or `dispatch_github_workflow.py <repo> publish-mcp-registry.yml` |
| GitHub Release tag | `./scripts/tag_satellite_release.sh v0.1.0 <id>` |

## Index status

| Channel | Entry | Status |
|---------|-------|--------|
| PyPI | aimarket-agent, aimarket-hub, aimarket-oracle-gateway, aimarket-mcp-packager | ✅ indexed |
| Glama | aimarket-oracle-gateway, aimarket-plugins, aimarket-mcp | ✅ live (API flaky) |
| awesome-mcp-servers Aggregators | aimarket-plugins | ✅ merged (#7193) |
| awesome-mcp-servers Security | aimarket-mcp + oracle-gateway + argus | 🔄 PR [#9910](https://github.com/punkpeye/awesome-mcp-servers/pull/9910) OPEN — **alexar76**, 3-server stack (replaces closed #8422) |
| slavakurilyak/awesome-ai-agents | aicom (AI-Factory) | 🔄 PR [#344](https://github.com/slavakurilyak/awesome-ai-agents/pull/344) OPEN — alexar76 |
| e2b-dev/awesome-ai-sdks | aimarket-agent + aimarket-sdks | 🔄 PR [#280](https://github.com/e2b-dev/awesome-ai-sdks/pull/280) OPEN — alexar76 |
| awesome-mcp-servers Security | argus | 📋 included in #9910 (was separate kit) |
| Official MCP Registry | aimarket-mcp, oracle-gateway, plugins, argus3 | ✅ **active** — see [`docs/mcp-registries/`](../mcp-registries/) · `./scripts/publish_mcp_registry.sh --check-live` |
| mcp.so / Smithery | — | ❌ manual login |
| GitHub pinned repos | profile | ❌ UI / GraphQL |
| X / LinkedIn / Dev.to | — | ❌ human accounts |

## MCP Registry `server.json` locations

| Server | Registry name | Monorepo path |
|--------|---------------|---------------|
| aimarket-mcp | `io.github.alexar76/aimarket-mcp` | `aimarket-mcp/server.json` |
| Oracle Gateway | `io.github.alexar76/aimarket-oracle-gateway` | `plugins/aimarket-oracle-gateway/server.json` |
| MCP Packager | `io.github.alexar76/aimarket-plugins` | `plugins/aimarket-mcp-packager/server.json` → mirrored to repo root |
| ARGUS-3 | `io.github.alexar76/argus3` | `argus/server.json` |

## Remaining (human-only)

1. Merge / ping **punkpeye** PR [#9910](https://github.com/punkpeye/awesome-mcp-servers/pull/9910) (3 MCP servers, Security)
2. Merge / ping **slavakurilyak** PR [#344](https://github.com/slavakurilyak/awesome-ai-agents/pull/344) (aicom)
3. Merge / ping **e2b** PR [#280](https://github.com/e2b-dev/awesome-ai-sdks/pull/280) (SDKs)
4. **Always fork/PR as alexar76** — not personal accounts
5. mcp.so + Smithery submit forms
6. PyPI `helios-broadcast` first publish (needs `PYPI_TOKEN` on helios repo)
7. Refresh `GH_PAT` in git remote if API dispatch returns 401 (git push may still work)

## MCP Registry (resolved 2026-07-12)

All four alexar76 MCP servers are **active** on the Official Registry. Re-publish after PyPI/npm version bumps via `./scripts/publish_mcp_registry.sh --dispatch`.
