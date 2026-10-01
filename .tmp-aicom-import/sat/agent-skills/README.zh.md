# aimarket-agent-skills

> 🌐 [English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · **中文**

公开插件包：通过 URL 使用 **Hub MCP**，以及 **WARDEN 防火墙**。完整指南：[docs/agent-install/README.zh.md](../docs/agent-install/README.zh.md)。

Cursor 无需克隆：

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

从 AICOM checkout 安装：

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```
