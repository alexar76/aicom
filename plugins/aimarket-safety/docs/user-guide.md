# aimarket-safety — User Guide

## Why it matters (plain words)

Stops dangerous or manipulative prompts before they reach any AI provider. If a call is blocked, you get a signed receipt and your money back — the marketplace stays safe for everyone.

**Простыми словами:** Останавливает опасные или манипулятивные промпты до того, как они дойдут до AI. При блокировке — подписанный чек и возврат денег. Маркетплейс остаётся безопасным для всех.


## What it does

Pre/post-invoke safety classifier with constitutional contracts. Category: **security**.

## Installation

```bash
pip install aimarket-safety
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-safety")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: `on_invoke_pre_check`, `on_invoke_post_check`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai-market/v2/p/aimarket-safety/safety/constitutional` | List constitutional contracts |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.safety'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
