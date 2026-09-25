# Agent install — Hub MCP and WARDEN

> 🌐 **English** · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · [中文](README.zh.md)

Two public skills plus one paste-URL. You do not need to clone this monorepo to **try** the marketplace.

| Door | What it is |
|------|------------|
| **Hub MCP** | `https://modelmarket.dev/mcp` — `market_search` then `market_invoke`. Always pass `source_hub`. |
| **Skill: aimarket-hub-mcp** | How to add that URL and call the two tools without 404ing federated hits |
| **Skill: warden-mcp-firewall** | `npx -y @aimarket/warden` — vet a `tools/list` dump. Does not proxy other servers. |

Canonical docs: [`hosted-mcp-endpoint.md`](../hosted-mcp-endpoint.md). Live trial size: `free_trial.max_invokes_per_visitor` in [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json).

**Source of truth** (this is what GitHub already serves):

- [`agent-skills/skills/aimarket-hub-mcp/SKILL.md`](../../agent-skills/skills/aimarket-hub-mcp/SKILL.md)
- [`agent-skills/skills/warden-mcp-firewall/SKILL.md`](../../agent-skills/skills/warden-mcp-firewall/SKILL.md)
- Plugin pack: [`agent-skills/`](../../agent-skills/) · marketplace: [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)

`.cursor/skills/` is the Cursor in-repo copy of those two files (tracked, same bytes). Do not invent a third path.

Raw:

- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md
- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

## Cursor — Hub MCP skill (3 lines)

No clone. From any project:

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Then paste `https://modelmarket.dev/mcp` into `.cursor/mcp.json` (shape is in the skill):

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

If this repo is already the workspace, the skill is already at `.cursor/skills/aimarket-hub-mcp/`. Only the MCP URL is left.

## Claude Code — Hub MCP skill (3 lines)

No clone:

```bash
mkdir -p ~/.claude/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o ~/.claude/skills/aimarket-hub-mcp/SKILL.md
```

Same URL in Claude Desktop / Claude Code MCP settings.

Or, from an aicom checkout, install the plugin:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```

There is no Anysphere Cursor Marketplace listing. Do not invent one.

## WARDEN firewall skill

Same three-line curl, other directory name: `warden-mcp-firewall`. Raw:

https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

Stdio config from the skill:

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
