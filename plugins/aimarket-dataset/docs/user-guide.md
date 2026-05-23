# aimarket-dataset — User Guide

## Why it matters (plain words)

Weekly anonymized snapshot of what the marketplace searches and buys — open data for researchers and builders who want to know demand trends without spying on users.

**Простыми словами:** Еженедельный обезличенный снимок того, что ищут и покупают на маркетплейсе — открытые данные для исследователей и разработчиков без слежки за пользователями.


## What it does

Weekly anonymized invocation corpus (CC-BY 4.0). Category: **tooling**.

## Installation

```bash
pip install aimarket-dataset
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-dataset")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai-market/v2/p/aimarket-dataset/export/latest` | Latest anonymized corpus |
| `GET` | `/ai-market/v2/p/aimarket-dataset/export/{week}` | Corpus for ISO week |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.dataset'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
