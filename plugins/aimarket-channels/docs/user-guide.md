# aimarket-channels — User Guide

## Why it matters (plain words)

Pay once into a prepaid tab, make dozens of tiny AI calls, settle once on-chain. No credit-card fee on every micro-cent — fast sessions for agents and apps.

**Простыми словами:** Пополняете «вкладку» один раз, делаете десятки мелких вызовов AI, закрываете один раз on-chain. Без комиссии карты на каждую копейку — быстрые сессии для агентов и приложений.


## What it does

Pre-funded payment channels — off-chain ledger, on-chain settlement. Category: **infrastructure**.

## Installation

```bash
pip install aimarket-channels
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-channels")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/channel/open` | Open pre-funded channel |
| `POST` | `/ai-market/v2/channel/close` | Settle and refund remainder |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.channels'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
