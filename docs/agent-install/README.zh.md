# Agent 安装 — Hub MCP 和 WARDEN

> 🌐 [English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · **中文**

两个公开技能加一个可直接粘贴的 URL。要**试用** marketplace，无需克隆此单体仓库。

| 入口 | 作用 |
|------|------------|
| **Hub MCP** | `https://modelmarket.dev/mcp` — 先用 `market_search`，再用 `market_invoke`。始终传入 `source_hub`。 |
| **技能：aimarket-hub-mcp** | 说明如何添加该 URL，并在调用两个工具时避免联邦结果出现 404。 |
| **技能：warden-mcp-firewall** | `npx -y @aimarket/warden` — 审查 `tools/list` 导出。它不会代理其他服务器。 |

规范文档：[`hosted-mcp-endpoint.md`](../hosted-mcp-endpoint.md)。live trial 的额度见 [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json) 中的 `free_trial.max_invokes_per_visitor`。

## 规范文件

GitHub 直接提供以下文件：

- [`agent-skills/skills/aimarket-hub-mcp/SKILL.md`](../../agent-skills/skills/aimarket-hub-mcp/SKILL.md)
- [`agent-skills/skills/warden-mcp-firewall/SKILL.md`](../../agent-skills/skills/warden-mcp-firewall/SKILL.md)
- 插件包：[`agent-skills/`](../../agent-skills/) · marketplace：[`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)

`.cursor/skills/` 是仓库中受跟踪的 Cursor 副本，内容与这两个文件相同；不要创建第三个路径。

Raw 文件：

- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md
- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

## Cursor — Hub MCP 技能

无需克隆，在任意项目中执行：

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

然后将 `https://modelmarket.dev/mcp` 写入 `.cursor/mcp.json`（结构见该技能）：

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

如果本仓库已经是 workspace，技能已位于 `.cursor/skills/aimarket-hub-mcp/`；只需添加 MCP URL。

## Claude Code — Hub MCP 技能

无需克隆：

```bash
mkdir -p ~/.claude/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o ~/.claude/skills/aimarket-hub-mcp/SKILL.md
```

在 Claude Desktop 或 Claude Code 的 MCP 设置中添加同一个 URL。

也可以从 AICOM checkout 安装插件：

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```

Anysphere Cursor Marketplace 中没有此条目。

## WARDEN 防火墙技能

使用相同的 `curl`，但目录改为 `warden-mcp-firewall`：

https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

技能中的 stdio 配置：

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

WARDEN 不会启动或代理其他 MCP 服务器；请把 `tools/list` 传给它。

## 首屏不谈加密货币

技能和首屏先展示 URL 与两个工具：trial，随后 402。不要以钱包或代币开场。
