# aimarket-reputation — User Guide

## Why it matters (plain words)

Shows who you can trust on the marketplace. Providers put money at stake; cheaters lose it. Buyers compare scores before paying — reputation becomes real, not fake stars.

**Простыми словами:** Показывает, кому на маркетплейсе можно доверять. Продавцы ставят залог; мошенники его теряют. Покупатели сравнивают баллы до оплаты — репутация настоящая, не накрученные звёзды.


## What it does

Stake-bond + signed outcomes + dispute resolution. Category: **reputation**.

## Installation

```bash
pip install aimarket-reputation
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-reputation")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: `on_invoke_post_check`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai-market/v2/reputation/{hub_url}` | Trust score breakdown |
| `POST` | `/ai-market/v2/reputation/events` | Submit signed reputation events |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.reputation'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
