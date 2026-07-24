# PR content: punkpeye/awesome-mcp-servers — ARGUS-3 (Security)

Fork `punkpeye/awesome-mcp-servers`, branch `add-argus3-mcp`, insert in `### 🔒 Security` alphabetically by `owner/repo` (after `alexar76/aimarket-oracle-gateway` if merged, before `alexfleetcommander/...`).

---

- [alexar76/argus](https://github.com/alexar76/argus) [![alexar76/argus MCP server](https://glama.ai/mcp/servers/alexar76/argus/badges/score.svg)](https://glama.ai/mcp/servers/alexar76/argus) 🎖️ 📇 🏠 ☁️ 🍎 🪟 🐧 - **ARGUS-3 as a stdio MCP server** (`argus mcp` → `argus_ask`, `argus_status`). **WARDEN** vets third-party MCP servers before any tool runs (LUMEN-scored firewall, tool-def pinning, drift sentinel). Distinct from `aimarket-oracle-gateway` (oracle tools) and `aimarket-plugins` (hub packager). npm `@alexar76/argus3` · [live](https://magic-ai-factory.com/argus/).

---

**PR title:** `Add alexar76/argus — WARDEN-hardened agent MCP server (Security)`

**PR body bullets:**

- MIT · Node ≥20 · stdio MCP (`argus mcp`)
- Security section: WARDEN blocks poisoned MCP servers before tools reach the model
- Not a duplicate of existing `alexar76/aimarket-plugins` (Aggregators) or pending `aimarket-oracle-gateway` (oracle pay-per-call)
- Glama: https://glama.ai/mcp/servers/alexar76/argus (after listing)
- Official MCP Registry: `io.github.alexar76/argus3`

**Open PR as:** **alexar76** fork only (do not use personal forks — closed #8422 was rejected for that reason).

```bash
gh repo fork punkpeye/awesome-mcp-servers --clone
cd awesome-mcp-servers
git checkout -b add-argus3-mcp
# edit README.md Security section
git commit -am "Add alexar76/argus WARDEN MCP server (Security)"
git push -u origin add-argus3-mcp
gh pr create --repo punkpeye/awesome-mcp-servers --title "Add alexar76/argus — WARDEN-hardened agent MCP server" --body-file ../docs/awesome-submissions/argus-punkpeye-security.md
```
