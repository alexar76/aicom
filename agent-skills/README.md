# aimarket-agent-skills

> 🌐 **English** · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · [中文](README.zh.md)

Public plugin pack: **Hub MCP by URL** and **WARDEN firewall**. Install notes: [`docs/agent-install/README.md`](../docs/agent-install/README.md).

No clone — Cursor:

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

From an aicom checkout:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```
