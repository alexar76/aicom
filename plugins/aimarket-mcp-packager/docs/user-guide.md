# aimarket-mcp-packager — User Guide

## Why it matters (plain words)

Turns any marketplace capability into an MCP tool for Claude Desktop / Cursor in one step — authors reach agent users without hand-writing MCP servers.

**Простыми словами:** Превращает возможность маркетплейса в MCP-инструмент для Claude Desktop / Cursor за один шаг — авторы доходят до пользователей агентов без ручного MCP-сервера.


## What it does

Package capabilities as MCP servers for Claude Desktop. Category: **tooling**.

## Installation

```bash
pip install aimarket-mcp-packager
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-mcp-packager")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-mcp-packager/package` | Build MCP manifest + Docker |
| `GET` | `/ai-market/v2/p/aimarket-mcp-packager/package/{id}` | Download package status |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.mcp-packager'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
