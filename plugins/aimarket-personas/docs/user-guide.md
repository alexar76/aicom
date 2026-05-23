# aimarket-personas — User Guide

## Why it matters (plain words)

Gives each capability a clear, buyer-friendly AI persona — so non-technical users understand what they're buying without reading API docs.

**Простыми словами:** У каждой возможности появляется понятный «персонаж» AI — нетехническим пользователям ясно, что они покупают, без чтения API-документации.


## What it does

Auto-generated AI agent personas for chat-native discovery. Category: **tooling**.

## Installation

```bash
pip install aimarket-personas
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-personas")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai-market/v2/p/aimarket-personas/personas` | List generated personas |
| `POST` | `/ai-market/v2/p/aimarket-personas/personas/generate` | Generate persona for niche |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.personas'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
