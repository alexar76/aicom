# Agent install — Hub MCP and WARDEN

Two public skills plus one paste-URL. You do not need to clone this monorepo to **try** the marketplace.

| Door | What it is |
|------|------------|
| **Hub MCP** | `https://modelmarket.dev/mcp` — `market_search` then `market_invoke`. Always pass `source_hub`. |
| **Skill: aimarket-hub-mcp** | How to add that URL and call the two tools without 404ing federated hits |
| **Skill: warden-mcp-firewall** | `npx -y @aimarket/warden` — vet a `tools/list` dump. Does not proxy other servers. |

Canonical docs: [`hosted-mcp-endpoint.md`](../hosted-mcp-endpoint.md). Live trial size: `free_trial.max_invokes_per_visitor` in [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json).

Skills live in this tree:

- Cursor: [`.cursor/skills/aimarket-hub-mcp/SKILL.md`](../../.cursor/skills/aimarket-hub-mcp/SKILL.md) · [`.cursor/skills/warden-mcp-firewall/SKILL.md`](../../.cursor/skills/warden-mcp-firewall/SKILL.md)
- Claude plugin: [`agent-skills/`](../../agent-skills/) (marketplace: [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json))

## Cursor — Hub MCP skill (3 lines)

From any project (needs an aicom checkout, or GitHub raw after this tree is mirrored):

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
cp /path/to/aicom/.cursor/skills/aimarket-hub-mcp/SKILL.md .cursor/skills/aimarket-hub-mcp/SKILL.md
# then paste https://modelmarket.dev/mcp into .cursor/mcp.json (shape is in the skill)
```

If this repo is already the workspace, the skill is already at `.cursor/skills/aimarket-hub-mcp/`. Add the MCP URL:

```json
{
  "mcpServers": {
    "aimarket": {
      "type": "streamable-http",
      "url": "https://modelmarket.dev/mcp"
    }
  }
}
```

## Claude Code — Hub MCP skill (3 lines)

Copy into the user skills dir:

```bash
mkdir -p ~/.claude/skills/aimarket-hub-mcp
cp /path/to/aicom/.cursor/skills/aimarket-hub-mcp/SKILL.md ~/.claude/skills/aimarket-hub-mcp/SKILL.md
# then add the same mcp.json URL in Claude Desktop / Claude Code MCP settings
```

Or, from an aicom checkout, install the plugin:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```

There is no Anysphere Cursor Marketplace listing. Do not invent one.

## WARDEN firewall skill

Same three-line copy, other directory name: `warden-mcp-firewall`. Stdio config from the skill:

```json
{
  "mcpServers": {
    "warden": {
      "command": "npx",
      "args": ["-y", "@aimarket/warden"]
    }
  }
}
```

WARDEN does not start or proxy other MCP servers. Pass `tools/list` in.

## Crypto off

Skills and first-screen copy lead with the URL and the two tools. Trial then 402. Do not lead with wallets or tokens.
