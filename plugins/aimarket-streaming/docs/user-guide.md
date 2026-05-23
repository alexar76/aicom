# aimarket-streaming — User Guide

## Why it matters (plain words)

Streams long AI answers token by token and charges fairly for what you actually read — stop early, pay less. Better for chat UIs and long reports.

**Простыми словами:** Длинные ответы AI идут по токенам, платите за то, что реально получили — остановили раньше, заплатили меньше. Удобно для чата и длинных отчётов.


## What it does

SSE/WS streaming with per-chunk micro-billing. Category: **monetization**.

## Installation

```bash
pip install aimarket-streaming
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-streaming")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: `on_invoke_post_check`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai-market/v2/p/aimarket-streaming/stream/{capability_id}` | SSE token stream |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.streaming'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
