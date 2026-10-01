# aimarket-agent-skills

> 🌐 [English](README.md) · **Русский** · [Español](README.es.md) · [Français](README.fr.md) · [中文](README.zh.md)

Публичный пакет плагина: **Hub MCP по URL** и **файрвол WARDEN**. Полная инструкция по установке: [`docs/agent-install/README.ru.md`](../docs/agent-install/README.ru.md).

Без клона для Cursor:

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Из checkout AICOM:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```
