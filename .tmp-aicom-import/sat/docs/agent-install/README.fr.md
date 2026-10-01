# Installation pour agents — Hub MCP et WARDEN

> 🌐 [English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · **Français** · [中文](README.zh.md)

Deux skills publics et une URL à coller. Il n’est pas nécessaire de cloner ce monorepo pour **essayer** le marketplace.

| Point d’entrée | Rôle |
|------|------------|
| **Hub MCP** | `https://modelmarket.dev/mcp` — d’abord `market_search`, puis `market_invoke`. Transmettez toujours `source_hub`. |
| **Skill : aimarket-hub-mcp** | Explique comment ajouter cette URL et appeler les deux outils sans 404 sur les résultats fédérés. |
| **Skill : warden-mcp-firewall** | `npx -y @aimarket/warden` — contrôle un export `tools/list`. Ne sert pas de proxy aux autres serveurs. |

Documentation canonique : [`hosted-mcp-endpoint.md`](../hosted-mcp-endpoint.md). La taille du trial live est indiquée par `free_trial.max_invokes_per_visitor` dans [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json).

## Fichiers canoniques

GitHub sert directement ces fichiers :

- [`agent-skills/skills/aimarket-hub-mcp/SKILL.md`](../../agent-skills/skills/aimarket-hub-mcp/SKILL.md)
- [`agent-skills/skills/warden-mcp-firewall/SKILL.md`](../../agent-skills/skills/warden-mcp-firewall/SKILL.md)
- Pack de plugin : [`agent-skills/`](../../agent-skills/) · marketplace : [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)

`.cursor/skills/` est la copie Cursor, suivie dans le dépôt, de ces deux fichiers. Ne créez pas de troisième chemin.

Fichiers raw :

- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md
- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

## Cursor — skill Hub MCP

Sans clone, depuis n’importe quel projet :

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Ajoutez ensuite `https://modelmarket.dev/mcp` dans `.cursor/mcp.json` (la forme est décrite dans le skill) :

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

Si ce dépôt est déjà le workspace, le skill est présent dans `.cursor/skills/aimarket-hub-mcp/` ; il reste seulement à ajouter l’URL MCP.

## Claude Code — skill Hub MCP

Sans clone :

```bash
mkdir -p ~/.claude/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o ~/.claude/skills/aimarket-hub-mcp/SKILL.md
```

Ajoutez la même URL aux réglages MCP de Claude Desktop ou Claude Code.

Ou installez le plugin depuis un checkout AICOM :

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```

Il n’existe pas d’entrée Anysphere Cursor Marketplace.

## Skill pare-feu WARDEN

Utilisez le même `curl`, mais avec le répertoire `warden-mcp-firewall` :

https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

Configuration stdio du skill :

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

WARDEN ne démarre ni ne proxy d’autres serveurs MCP : transmettez-lui `tools/list`.

## Pas de crypto au premier écran

Les skills et le premier écran commencent par l’URL et les deux outils : trial, puis 402. Ne commencez pas par les portefeuilles ou les tokens.
