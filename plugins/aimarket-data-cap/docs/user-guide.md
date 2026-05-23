# aimarket-data-cap — User Guide

## Why it matters (plain words)

Monetize private documents: others pay per search query, you never hand over raw files. Law firms, labs, and enterprises turn knowledge into revenue safely.

**Простыми словами:** Монетизируете закрытые документы: другие платят за поиск, сырые файлы вы не отдаёте. Юрфирмы, лаборатории и компании превращают знания в доход безопасно.


## What it does

Private RAG corpus exposed as paid search capability. Category: **monetization**.

## Installation

```bash
pip install aimarket-data-cap
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-data-cap")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-data-cap/index` | Register private corpus |
| `POST` | `/ai-market/v2/p/aimarket-data-cap/search` | Paid semantic search |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.data-cap'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
