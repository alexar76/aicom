# aimarket-orchestrator — User Guide

## Why it matters (plain words)

Describe a goal in plain language; the hub plans which AI capabilities to call in what order and estimates cost before spending — autopilot for multi-step tasks.

**Простыми словами:** Описываете цель простыми словами; хаб планирует, какие AI вызывать и в каком порядке, и оценивает стоимость до траты — автопилот для многошаговых задач.


## What it does

NL task planner — decomposes tasks into capability chains (1% fee). Category: **monetization**.

## Installation

```bash
pip install aimarket-orchestrator
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-orchestrator")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-orchestrator/orchestrator/plan` | Plan multi-step task |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.orchestrator'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
