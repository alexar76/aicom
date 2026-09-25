# aimarket-agent-skills

> 🌐 [English](README.md) · [Русский](README.ru.md) · **Español** · [Français](README.fr.md) · [中文](README.zh.md)

Paquete público: **Hub MCP por URL** y **firewall WARDEN**. Guía completa: [`docs/agent-install/README.es.md`](../docs/agent-install/README.es.md).

Sin clonar para Cursor:

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Desde un checkout de AICOM:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```
