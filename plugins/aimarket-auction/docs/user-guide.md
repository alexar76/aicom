# aimarket-auction — User Guide

## Why it matters (plain words)

Scarce AI capacity goes to whoever values it most right now — like airline yield management. Providers earn more at peak; buyers save money off-peak.

**Простыми словами:** Редкая мощность AI достаётся тому, кому она сейчас важнее — как динамические цены у авиакомпаний. Продавцы зарабатывают в пик; покупатели экономят в спокойное время.


## What it does

Real-time spot bidding for capability slots. Category: **monetization**.

## Installation

```bash
pip install aimarket-auction
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-auction")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-auction/auction/bid` | Place bid on capability slot |
| `GET` | `/ai-market/v2/p/aimarket-auction/auction/{capability_id}` | Current auction state |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.auction'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
