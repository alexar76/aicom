# aimarket-agent-skills

> 🌐 [English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · **Français** · [中文](README.zh.md)

Pack public : **Hub MCP par URL** et **pare-feu WARDEN**. Guide complet : [`docs/agent-install/README.fr.md`](../docs/agent-install/README.fr.md).

Sans clone pour Cursor :

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Depuis un checkout AICOM :

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```
