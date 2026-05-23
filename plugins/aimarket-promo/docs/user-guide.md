# aimarket-promo — User Guide

## Why it matters (plain words)

Time-limited signed discounts fill idle AI capacity — like happy hour for GPU slots. Providers move spare compute; buyers catch real deals.

**Простыми словами:** Подписанные скидки на время заполняют простаивающую мощность AI — «happy hour» для GPU. Продавцы загружают простой; покупатели ловят настоящие акции.


## What it does

Signed time-locked discount offers (yield management). Category: **monetization**.

## Installation

```bash
pip install aimarket-promo
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-promo")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: `on_invoke_pre_check`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-promo/offer/create` | Create signed discount |
| `POST` | `/ai-market/v2/p/aimarket-promo/offer/redeem` | Redeem at invoke time |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.promo'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
