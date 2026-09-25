# Установка для агентов — Hub MCP и WARDEN

> 🌐 [English](README.md) · **Русский** · [Español](README.es.md) · [Français](README.fr.md) · [中文](README.zh.md)

Два публичных скилла и один URL для вставки. Чтобы попробовать marketplace, клон этого монорепозитория **не нужен**.

| Точка входа | Назначение |
|------|------------|
| **Hub MCP** | `https://modelmarket.dev/mcp` — сначала `market_search`, затем `market_invoke`. Всегда передавайте `source_hub`. |
| **Скилл: aimarket-hub-mcp** | Подключает URL и объясняет вызов двух инструментов без 404 для федеративных результатов. |
| **Скилл: warden-mcp-firewall** | `npx -y @aimarket/warden` — проверяет выгрузку `tools/list`. Не проксирует другие серверы. |

Основная справка: [`hosted-mcp-endpoint.md`](../hosted-mcp-endpoint.md). Размер live-trial указан в `free_trial.max_invokes_per_visitor` в [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json).

## Канонические файлы

Это файлы, которые GitHub публикует для установки:

- [`agent-skills/skills/aimarket-hub-mcp/SKILL.md`](../../agent-skills/skills/aimarket-hub-mcp/SKILL.md)
- [`agent-skills/skills/warden-mcp-firewall/SKILL.md`](../../agent-skills/skills/warden-mcp-firewall/SKILL.md)
- Пакет плагина: [`agent-skills/`](../../agent-skills/) · marketplace: [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)

`.cursor/skills/` — отслеживаемая в репозитории Cursor-копия этих же двух файлов; третьего пути не создавайте.

Raw-файлы:

- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md
- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

## Cursor — скилл Hub MCP

Без клона, из любого проекта:

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Затем добавьте `https://modelmarket.dev/mcp` в `.cursor/mcp.json` (форма описана в скилле):

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

Если этот репозиторий уже является workspace, скилл находится в `.cursor/skills/aimarket-hub-mcp/`; остаётся добавить URL MCP.

## Claude Code — скилл Hub MCP

Без клона:

```bash
mkdir -p ~/.claude/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o ~/.claude/skills/aimarket-hub-mcp/SKILL.md
```

Тот же URL добавьте в настройках MCP Claude Desktop или Claude Code.

Либо из checkout AICOM установите плагин:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```

В Anysphere Cursor Marketplace этой записи нет.

## Скилл-файрвол WARDEN

То же скачивание `curl`, но с именем каталога `warden-mcp-firewall`:

https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

Настройка stdio из скилла:

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

WARDEN не запускает и не проксирует другие MCP-серверы: передайте ему `tools/list`.

## Без криптографии на первом экране

Скиллы и первый экран ведут с URL и двумя инструментами: trial, затем 402. Не начинайте с кошельков или токенов.
